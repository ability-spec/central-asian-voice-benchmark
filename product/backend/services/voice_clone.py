"""
Optional ElevenLabs voice provider for BirOvoz (VC1)
+ CP5 local-clone provider (Sayro via voice-lab Route B -> Seed-VC V1).

Design constraints (agreed scope):
  * Providers are OPTIONAL; OpenAI stays the default and the runtime
    fallback. The active provider can be switched at runtime via
    POST /api/voice/provider and is resolved per synthesis call in
    services/tts.py.
  * ElevenLabs: zero new deps; urllib HTTP API; samples written to a
    temp dir and always deleted; resulting voice_id stored OUTSIDE the
    repo at settings.voice_config_path (default ~/.birovoz_voice.json).
  * Local clone (CP5): invokes the EXISTING Route B wrapper in voice-lab
    (b_sayro_then_seedvc.py). The wrapper loads Sayro (1.7B) in-process,
    optionally normalizes Uzbek via uzbek_normalizer.py, then shells out
    to Seed-VC V1 inference.py (cwd=SEEDVC_DIR). The BirOvoz product
    does NOT import Sayro or Seed-VC directly — it shells out to the
    wrapper in a per-request temp workspace and returns the converted
    WAV. A module-level Lock serializes all local-clone calls so we never
    race two Sayro model loads on the same GPU. Kazakh is NOT supported
    in MVP — Route B is Uzbek-only and those calls transparently stay
    on OpenAI; no Kazakh output is ever routed through Sayro.

Security note: stored out-of-repo config contains a voice_id only —
never API keys (keys stay in environment). Reference WAV / model files
live outside the repository; paths come from env.
"""

import io
import json
import logging
import os
import shlex
import shutil
import struct
import subprocess
import tempfile
import threading
import urllib.request
import uuid
from pathlib import Path

from product.backend.config import settings

logger = logging.getLogger(__name__)

EL_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
EL_ADD_VOICE_URL = "https://api.elevenlabs.io/v1/voices/add"
PCM_SAMPLE_RATE = 24000  # matches ElevenLabs pcm_24000 output format

VALID_PROVIDERS = ("openai", "elevenlabs", "local-clone")

_lock = threading.Lock()
_active_provider: str = None  # resolved lazily from settings on first use


# ---------------------------------------------------------------------------
# Runtime provider state
# ---------------------------------------------------------------------------

def _stored_config_path() -> Path:
    return Path(settings.voice_config_path)


def _load_stored() -> dict:
    """Read the out-of-repo voice config; {} when absent/unreadable."""
    try:
        return json.loads(_stored_config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _store(data: dict) -> None:
    path = _stored_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def effective_voice_id() -> str:
    """The most recently ENROLLED voice wins; ELEVENLABS_VOICE_ID is the
    fallback when nothing has been enrolled."""
    enrolled = _load_stored().get("elevenlabs_voice_id", "")
    if enrolled:
        return enrolled
    return settings.elevenlabs_voice_id


def elevenlabs_configured() -> bool:
    return bool(settings.elevenlabs_api_key and effective_voice_id())


# ---------------------------------------------------------------------------
# CP5: local clone — invokes existing voice-lab/b_sayro_then_seedvc.py.
# The wrapper handles Sayro in-process (speaker="sayro", instruct="Neutral",
# optional Uzbek normalization) then runs Seed-VC as a subprocess with
# cwd=SEEDVC_DIR using V1 flags. The product shells out to the wrapper in
# a per-request temp workspace with a single module-level Lock so we never
# launch two Sayro model loads concurrently on the same GPU.
# ---------------------------------------------------------------------------

def _which(path: str) -> bool:
    """Return True if `path` points at an existing file (absolute path)
    or resolves on PATH (bare command)."""
    if not path:
        return False
    p = Path(path)
    if p.is_absolute():
        return p.exists()
    return shutil.which(path) is not None


def _resolve_under(root: str, rel: str) -> Path:
    p = Path(rel)
    if p.is_absolute() or not root:
        return p
    return Path(root) / rel


def seedvc_configured() -> bool:
    """Seed-VC is usable iff SEEDVC_PYTHON resolves and SEEDVC_DIR exists
    and the reference WAV exists. The wrapper picks inference.py and all
    V1 flags internally."""
    py = settings.seedvc_python
    sd = settings.seedvc_dir
    ref = settings.seedvc_reference_wav
    if not (py and sd and ref):
        return False
    ref_path = Path(ref)
    return _which(py) and Path(sd).is_dir() and ref_path.is_file()


def sayro_configured() -> bool:
    """The Route B wrapper is usable iff SAYRO_PYTHON + the wrapper script
    resolve AND Seed-VC is configured (the wrapper shells out to Seed-VC
    internally)."""
    py = settings.sayro_python
    script = settings.sayro_script
    if not (py and script):
        return False
    script_path = _resolve_under(settings.sayro_voice_lab_dir, script)
    return _which(py) and script_path.is_file() and seedvc_configured()


def local_clone_configured() -> bool:
    return sayro_configured()


# Module-level serialization: wraps every local-clone synthesis so we never
# run two wrapper invocations at once (Sayro model + Seed-VC cannot share
# the 4060 GPU).
_local_clone_lock = threading.Lock()
_local_clone_busy: bool = False


def active_provider() -> str:
    global _active_provider
    with _lock:
        if _active_provider is None:
            p = (settings.tts_provider or "openai").strip().lower()
            _active_provider = p if p in VALID_PROVIDERS else "openai"
        return _active_provider


def resolved_provider() -> str:
    """The provider a synthesis call would actually use right now.

    A non-OpenAI provider is returned ONLY when it is BOTH selected and
    fully configured AND (for local-clone) the request's language is
    supported. Otherwise the OpenAI default is used silently — the
    pipeline never hard-fails on config drift. Per-call language gating
    for local-clone happens in tts.synthesize (we don't have a `language`
    argument here).
    """
    selected = active_provider()
    if selected == "elevenlabs" and elevenlabs_configured():
        return "elevenlabs"
    if selected == "local-clone" and local_clone_configured():
        return "local-clone"
    return "openai"


def set_provider(provider: str) -> None:
    p = (provider or "").strip().lower()
    if p not in VALID_PROVIDERS:
        raise ValueError(
            "provider must be 'openai', 'elevenlabs', or 'local-clone'."
        )
    if p == "elevenlabs" and not elevenlabs_configured():
        raise ValueError(
            "ElevenLabs is not configured: set ELEVENLABS_API_KEY and a voice id "
            "(ELEVENLABS_VOICE_ID or an enrolled voice)."
        )
    if p == "local-clone" and not local_clone_configured():
        raise ValueError(
            "Local clone is not configured: point SAYRO_PYTHON / SAYRO_SCRIPT / "
            "SAYRO_VOICE_LAB_DIR at the out-of-repo voice-lab Route B wrapper "
            "and SEEDVC_PYTHON / SEEDVC_DIR / SEEDVC_REFERENCE_WAV at Seed-VC."
        )
    global _active_provider
    with _lock:
        _active_provider = p
    logger.info("Active TTS voice provider set to '%s'", p)


def active_model_name() -> str:
    rp = resolved_provider()
    if rp == "elevenlabs":
        return settings.elevenlabs_tts_model
    if rp == "local-clone":
        return "sayro-seedvc"
    return settings.tts_model


def _local_clone_supported_language(language: str) -> bool:
    """CP5 MVP: voice-lab Route B wrapper is explicitly Uzbek
    (speaker='sayro', uzbek_normalizer). Kazakh stays on OpenAI."""
    return language == "uz"


def tts_label(report: dict = None) -> str:
    """'provider/model' for provider_info — truthful to what actually ran.

    When a synthesis call filled `report`, that wins (it records the real
    provider incl. any OpenAI fallback after a clone failure)."""
    if report and report.get("provider"):
        model = report.get("model")
        if not model:
            if report["provider"] == "elevenlabs":
                model = settings.elevenlabs_tts_model
            elif report["provider"] == "local-clone":
                model = "sayro-seedvc"
            else:
                model = settings.tts_model
        return f"{report['provider']}/{model}"
    return f"{resolved_provider()}/{active_model_name()}"


def status() -> dict:
    return {
        "tts_provider_env": settings.tts_provider,
        "active_provider": active_provider(),
        "resolved_provider": resolved_provider(),
        "elevenlabs": {
            "configured": elevenlabs_configured(),
            "api_key_set": bool(settings.elevenlabs_api_key),
            "voice_id_set": bool(effective_voice_id()),
            "model": settings.elevenlabs_tts_model,
        },
        "local_clone": {
            "configured": local_clone_configured(),
            "sayro_ready": sayro_configured(),
            "seedvc_ready": seedvc_configured(),
            "reference_set": bool(settings.seedvc_reference_wav),
            "languages": ["uz"],  # MVP: Uzbek only
            "busy": _local_clone_busy,
            "model": "sayro-seedvc",
        },
        "fallback": "openai",
    }


# ---------------------------------------------------------------------------
# ElevenLabs HTTP seams (tests monkeypatch _el_tts / _el_add_voice)
# ---------------------------------------------------------------------------

def _el_tts(text: str) -> bytes:
    """Call ElevenLabs text-to-speech; return raw PCM s16le mono bytes."""
    url = EL_TTS_URL.format(voice_id=effective_voice_id()) + "?output_format=pcm_24000"
    body = json.dumps({
        "text": text,
        "model_id": settings.elevenlabs_tts_model,
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={
            "xi-api-key": settings.elevenlabs_api_key,
            "Content-Type": "application/json",
            "Accept": "audio/*",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def _pcm_to_wav(pcm: bytes, rate: int = PCM_SAMPLE_RATE) -> bytes:
    """Wrap headerless PCM s16le mono in a WAV container (frontend expects WAV)."""
    return (
        b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE"
        + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
        + b"data" + struct.pack("<I", len(pcm)) + pcm
    )


def synthesize_elevenlabs(text: str, language: str) -> bytes:
    """ElevenLabs TTS -> WAV bytes."""
    pcm = _el_tts(text)
    if not pcm:
        raise RuntimeError("ElevenLabs returned empty audio")
    return _pcm_to_wav(pcm)


# ---------------------------------------------------------------------------
# CP5: Route B wrapper invocation (tests monkeypatch _run_subprocess and
# _find_converted_output; no GPU / no real Sayro/Seed-VC env ever runs in
# unit tests).
# ---------------------------------------------------------------------------

def _run_subprocess(cmd: list, timeout: int, cwd: str = None) -> None:
    """Run `cmd` (argv list), raise RuntimeError on non-zero / timeout /
    missing executable. stdout/stderr captured for logging."""
    logger.debug("local-clone subprocess: cwd=%s argv=%s",
                 cwd or os.getcwd(),
                 " ".join(shlex.quote(c) for c in cmd))
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd,
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            f"local-clone subprocess timed out after {timeout}s: {cmd[0]}"
        ) from e
    except FileNotFoundError as e:
        raise RuntimeError(f"local-clone executable not found: {cmd[0]}") from e
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-5:]
        raise RuntimeError(
            f"local-clone subprocess failed ({cmd[0]}, exit={proc.returncode}): "
            + " | ".join(tail)
        )


def _find_converted_output(out_dir: Path, source_stem: str) -> Path:
    """Route B wrapper delegates to Seed-VC V1 inference.py, which writes
    one WAV per source file into --output. We return the newest WAV under
    out_dir (robust to V1 writing <source_stem>.wav vs V2 adding suffixes)."""
    candidates = sorted(
        [p for p in out_dir.rglob("*.wav") if p.is_file()],
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    if candidates:
        return candidates[0]
    raise RuntimeError(
        f"Route B produced no converted WAV under {out_dir} "
        f"(source_stem={source_stem})"
    )


def _split_extra(extra: str) -> list:
    extra = (extra or "").strip()
    return shlex.split(extra) if extra else []


def _build_route_b_cmd(text: str, sentences_path: Path, out_dir: Path) -> list:
    """Build the argv list for the real voice-lab Route B wrapper CLI.

    The wrapper expects:
      --stage all        run Sayro TTS then Seed-VC end-to-end
      --sentences <dir>  directory containing numbered sentence files;
                         file 001.txt (or 1.txt) holds utterance #1
      --only 1           only process utterance #1 (one per request)
      --out <dir>        output directory for converted WAV(s)
      --target <ref.wav> Seed-VC reference voice target
      --seedvc-python <py>  Python exe in the Seed-VC venv
      --seedvc-dir <dir>    Seed-VC checkout (wrapper uses as cwd)
      --seedvc-version v1   Use Seed-VC V1 inference.py

    We write exactly one numbered sentence file into a temp sentences
    directory per request, then run --stage all --only 1 against it.
    Any extra operator tokens from ROUTE_B_EXTRA_ARGS are appended
    verbatim (shlex-split) so wrapper-side flag additions don't require
    code changes in BirOvoz.
    """
    script_path = _resolve_under(settings.sayro_voice_lab_dir,
                                 settings.sayro_script)
    ref_path = Path(settings.seedvc_reference_wav)

    cmd = [
        settings.sayro_python,
        str(script_path),
        "--stage", "all",
        "--sentences", str(sentences_path),
        "--only", "1",
        "--out", str(out_dir),
        "--target", str(ref_path),
        "--seedvc-python", settings.seedvc_python,
        "--seedvc-dir", settings.seedvc_dir,
        "--seedvc-version", "v1",
    ]
    cmd += _split_extra(settings.route_b_extra_args)
    return cmd


def synthesize_local_clone(text: str, language: str) -> bytes:
    """CP5: invoke the voice-lab Route B wrapper (Sayro -> Seed-VC) for a
    single utterance, return converted WAV bytes.

    Per request we create a temp workspace containing a sentences
    subdirectory with one numbered sentence file (`001.txt` — or `1.txt`,
    the wrapper accepts both conventions) and an output directory. The
    wrapper is invoked with the real CLI (`--stage all --sentences <dir>
    --only 1 --out <dir> --target … --seedvc-python … --seedvc-dir …
    --seedvc-version v1`) with cwd = SAYRO_VOICE_LAB_DIR.

    Serialized process-wide by _local_clone_lock so concurrent DUB3
    sentences can never load Sayro simultaneously and OOM the GPU.
    Raises RuntimeError on any failure so tts.synthesize falls back to
    OpenAI with a truthful report.

    Pre-conditions:
      * local_clone_configured() is True (checked by caller).
      * language == 'uz' (Kazakh stays on OpenAI at the tts.synthesize layer).
    """
    import wave as _wave
    if not text or not text.strip():
        raise RuntimeError("local-clone: empty text")
    if not _local_clone_supported_language(language):
        raise RuntimeError(
            f"local-clone: language {language!r} not supported in MVP "
            f"(Uzbek only)"
        )

    tmp_dir = Path(tempfile.mkdtemp(prefix="birovoz_localclone_"))
    sentences_dir = tmp_dir / "sentences"
    sentences_dir.mkdir(parents=True, exist_ok=True)
    # Write the single utterance as sentence #1. Use a "001.txt" naming
    # convention (zero-padded) which is the common batch-TTS layout; the
    # --only 1 flag guarantees we process exactly that utterance.
    sentence_file = sentences_dir / "001.txt"
    sentence_file.write_text(text.strip(), encoding="utf-8")
    out_dir = tmp_dir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        global _local_clone_busy
        with _local_clone_lock:
            _local_clone_busy = True
            try:
                cmd = _build_route_b_cmd(text, sentences_dir, out_dir)
                cwd = settings.sayro_voice_lab_dir or None
                _run_subprocess(cmd,
                                timeout=settings.local_clone_timeout_s,
                                cwd=cwd)
            finally:
                _local_clone_busy = False

        converted = _find_converted_output(out_dir, "001")
        data = converted.read_bytes()
        if not data:
            raise RuntimeError("Route B produced an empty converted WAV")
        # Validate WAV before returning.
        try:
            with _wave.open(io.BytesIO(data), "rb") as wf:
                if wf.getnframes() == 0:
                    raise RuntimeError("Converted WAV has zero frames")
        except Exception as e:
            raise RuntimeError(f"Converted audio is not a valid WAV: {e}") from e
        return data
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Enrollment (ElevenLabs only; consent-gated, own/authorized voice)
# ---------------------------------------------------------------------------

def _el_add_voice(name: str, sample_paths: list) -> str:
    """Create an ElevenLabs voice from sample files; return its voice_id."""
    boundary = "----birovoz" + uuid.uuid4().hex
    parts = []
    parts.append((
        f"--{boundary}\r\n".encode("ascii"),
        b'Content-Disposition: form-data; name="name"\r\n\r\n' + name.encode("utf-8"),
    ))
    for path in sample_paths:
        header = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="files"; filename="{Path(path).name}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8")
        parts.append((header, Path(path).read_bytes()))
    body = b"".join(h + d + b"\r\n" for h, d in parts)
    body += f"--{boundary}--\r\n".encode("ascii")
    req = urllib.request.Request(
        EL_ADD_VOICE_URL, data=body, method="POST",
        headers={
            "xi-api-key": settings.elevenlabs_api_key,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    voice_id = payload.get("voice_id")
    if not voice_id:
        raise RuntimeError("ElevenLabs enrollment returned no voice_id")
    return voice_id


def enroll(sample_files: list, consent: str, name: str = "My voice") -> dict:
    """Enroll a voice from 1-5 audio samples (ElevenLabs only).

    The local-clone path uses the pre-existing reference WAV via
    SEEDVC_REFERENCE_WAV — it does not expose enrollment.
    """
    if (consent or "").strip().lower() not in ("yes", "true", "1"):
        raise ValueError(
            "Voice enrollment is consent-gated: pass consent='yes' to confirm "
            "you are enrolling your own or an explicitly authorized voice."
        )
    if not settings.elevenlabs_api_key:
        raise RuntimeError("ElevenLabs API key is not configured.")
    samples = list(sample_files)
    if not 1 <= len(samples) <= 5:
        raise ValueError("Enrollment accepts 1-5 audio samples.")

    tmp_dir = Path(tempfile.mkdtemp(prefix="birovoz_enroll_"))
    try:
        paths = []
        for i, sample in enumerate(samples, 1):
            data = sample.file.read()
            if not data:
                raise ValueError(f"Sample {i} is empty.")
            p = tmp_dir / f"sample_{i:02d}.wav"
            p.write_bytes(data)
            paths.append(p)
        voice_id = _el_add_voice(name or "My voice", paths)
        _store({"elevenlabs_voice_id": voice_id, "enrolled": True})
        logger.info(
            "Voice enrolled (voice_id=%s…, samples=%d) — temp samples deleted",
            voice_id[:6], len(paths),
        )
        return {
            "voice_id": voice_id,
            "provider": "elevenlabs",
            "model": settings.elevenlabs_tts_model,
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
