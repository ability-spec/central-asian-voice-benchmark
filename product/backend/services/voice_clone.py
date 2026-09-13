"""
Optional ElevenLabs voice provider for BirOvoz (VC1).

Design constraints (agreed VC1 scope):
  * ElevenLabs is an OPTIONAL TTS provider. OpenAI stays the default; the
    active provider can be switched at runtime via POST /api/voice/provider
    (frontend chip) and is resolved per synthesis call in services/tts.py.
  * Zero new dependencies: the ElevenLabs HTTP API is called with urllib.
  * Enrollment (POST /api/voice/enroll) is consent-gated and intended ONLY
    for the user's own or explicitly authorized voice. Samples (1-5) are
    written to a system temp dir and ALWAYS deleted after processing; only
    the resulting voice_id is stored, in a JSON config OUTSIDE the repository
    (settings.voice_config_path, default ~/.birovoz_voice.json).
  * No voice marketplace, no public accounts, no research functionality.

Security note: the stored config contains a voice_id only — never the API
key (the key stays in the environment).
"""

import json
import logging
import shutil
import struct
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

VALID_PROVIDERS = ("openai", "elevenlabs")

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
    fallback when nothing has been enrolled (so enrollment is never a no-op
    while an env id happens to be set)."""
    enrolled = _load_stored().get("elevenlabs_voice_id", "")
    if enrolled:
        return enrolled
    return settings.elevenlabs_voice_id


def elevenlabs_configured() -> bool:
    return bool(settings.elevenlabs_api_key and effective_voice_id())


def active_provider() -> str:
    global _active_provider
    with _lock:
        if _active_provider is None:
            p = (settings.tts_provider or "openai").strip().lower()
            _active_provider = p if p in VALID_PROVIDERS else "openai"
        return _active_provider


def resolved_provider() -> str:
    """The provider a synthesis call would actually use right now.

    'elevenlabs' only when it is BOTH selected and fully configured — an
    unconfigured selection silently resolves to the OpenAI default so the
    pipeline never hard-fails on config drift."""
    if active_provider() == "elevenlabs" and elevenlabs_configured():
        return "elevenlabs"
    return "openai"


def set_provider(provider: str) -> None:
    p = (provider or "").strip().lower()
    if p not in VALID_PROVIDERS:
        raise ValueError("provider must be 'openai' or 'elevenlabs'.")
    if p == "elevenlabs" and not elevenlabs_configured():
        raise ValueError(
            "ElevenLabs is not configured: set ELEVENLABS_API_KEY and a voice id "
            "(ELEVENLABS_VOICE_ID or an enrolled voice)."
        )
    global _active_provider
    with _lock:
        _active_provider = p
    logger.info("Active TTS voice provider set to '%s'", p)


def active_model_name() -> str:
    if resolved_provider() == "elevenlabs":
        return settings.elevenlabs_tts_model
    return settings.tts_model


def tts_label(report: dict = None) -> str:
    """'provider/model' for provider_info — truthful to what actually ran.

    When a synthesis call filled `report`, that wins (it records the real
    provider incl. any OpenAI fallback after an ElevenLabs failure)."""
    if report and report.get("provider"):
        model = report.get("model") or active_model_name()
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
    """ElevenLabs TTS → WAV bytes. `language` is unused by the multilingual
    model but kept for symmetry with the OpenAI path."""
    pcm = _el_tts(text)
    if not pcm:
        raise RuntimeError("ElevenLabs returned empty audio")
    return _pcm_to_wav(pcm)


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


# ---------------------------------------------------------------------------
# Enrollment (consent-gated, own/authorized voice only)
# ---------------------------------------------------------------------------

def enroll(sample_files: list, consent: str, name: str = "My voice") -> dict:
    """Enroll a voice from 1-5 audio samples.

    Raises ValueError for user errors (consent, sample count, empty sample);
    RuntimeError when the provider is unavailable. Samples are ALWAYS deleted
    from the temp dir; only the resulting voice_id is stored, outside the repo.
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
