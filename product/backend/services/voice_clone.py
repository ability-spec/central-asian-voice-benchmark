"""
Optional ElevenLabs voice provider for BirOvoz (VC1)
+ CP5 local-clone provider (Sayro -> vendored Route B wrapper -> Seed-VC v2).

Design constraints (agreed scope):
  * Providers are OPTIONAL; OpenAI stays the default and the runtime
    fallback. The active provider can be switched at runtime via
    POST /api/voice/provider and is resolved per synthesis call in
    services/tts.py.
  * ElevenLabs: zero new deps; urllib HTTP API; samples written to a
    temp dir and always deleted; resulting voice_id stored OUTSIDE the
    repo at settings.voice_config_path (default ~/.birovoz_voice.json).
  * Local clone (CP5): invokes the VENDORED Route B wrapper under
    product/backend/services/routeb/b_sayro_then_seedvc.py (an absolute
    external path via SAYRO_SCRIPT is also supported for back-compat
    with the standalone voice-lab checkout during transition). The
    wrapper loads Sayro in its OWN Python process (SAYRO_PYTHON), then
    shells out to Seed-VC (cwd=SEEDVC_DIR; default third_party/seed-vc)
    using the persistent V2 batch worker with target-feature caching.
    BirOvoz never imports Sayro or Seed-VC directly. A module-level Lock
    serializes all local-clone calls so we never race two model loads on
    the same GPU. Kazakh is NOT supported in MVP — Route B is Uzbek-only.

Security: stored out-of-repo config contains a voice_id only — never API
keys (keys stay in environment). Reference WAV / model weights live
outside the repository; paths come from env.
"""

import json
import logging
import os
import re as _re
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import uuid
import atexit
import base64
import queue
import signal
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
# CP5: local clone — shells out to the vendored services/routeb wrapper.
# Path resolution order for every Route B artifact:
#   1. Explicit env var (absolute path) wins.
#   2. Conventional in-repo default, if it exists on disk:
#        - wrapper script: services/routeb/b_sayro_then_seedvc.py
#        - Seed-VC checkout: product/backend/third_party/seed-vc
#        - Seed-VC venv python: $SEEDVC_DIR/.venv-vc/...
#        - Sayro venv python: product/backend/.venv-routeb/...
#   3. Empty string -> feature gracefully disabled (OpenAI fallback).
# The wrapper runs Sayro in-process and Seed-VC as a persistent
# subprocess; BirOvoz never imports either model directly. A module-
# level Lock serializes calls to protect the GPU.
# ---------------------------------------------------------------------------

_BACKEND_DIR = Path(__file__).resolve().parent.parent  # product/backend
_VENDORED_WRAPPER = _BACKEND_DIR / "services" / "routeb" / "b_sayro_then_seedvc.py"
_DEFAULT_SEEDVC_DIR = _BACKEND_DIR / "third_party" / "seed-vc"
_DEFAULT_SAYRO_VENV = _BACKEND_DIR / ".venv-routeb"


def _which(path) -> bool:
    """Return True if `path` points at an existing executable file
    (absolute path) or resolves on PATH (bare command)."""
    if not path:
        return False
    p = Path(path)
    if not p.is_absolute():
        return shutil.which(str(p)) is not None
    return p.is_file()


def _candidate_python_exes(venv_dir: Path) -> list:
    """Return candidate python.exe paths inside a virtualenv (Windows or POSIX)."""
    return [venv_dir / "Scripts" / "python.exe",
            venv_dir / "bin" / "python"]


def _resolve_seedvc_dir() -> Path:
    """SEEDVC_DIR explicit, else conventional third_party/seed-vc if it exists."""
    if settings.seedvc_dir:
        return Path(settings.seedvc_dir)
    if _DEFAULT_SEEDVC_DIR.is_dir():
        return _DEFAULT_SEEDVC_DIR
    return None


def _resolve_seedvc_python(seedvc_dir: Path) -> str:
    if settings.seedvc_python:
        return settings.seedvc_python
    if seedvc_dir is not None:
        for cand in _candidate_python_exes(seedvc_dir / ".venv-vc"):
            if cand.is_file():
                return str(cand)
    return ""


def _resolve_sayro_script() -> Path:
    """Absolute path to the Route B wrapper script."""
    if settings.sayro_script:
        p = Path(settings.sayro_script)
        if p.is_absolute():
            return p
        if settings.sayro_voice_lab_dir:
            return Path(settings.sayro_voice_lab_dir) / p
        return p
    return _VENDORED_WRAPPER if _VENDORED_WRAPPER.is_file() else None


def _resolve_sayro_python(script_path: Path) -> str:
    if settings.sayro_python:
        return settings.sayro_python
    # Convention: .venv-routeb next to backend.
    for cand in _candidate_python_exes(_DEFAULT_SAYRO_VENV):
        if cand.is_file():
            return str(cand)
    return ""


def _resolve_wrapper_cwd(script_path: Path) -> Path:
    """cwd for the wrapper subprocess: the directory containing the script
    so `from common import …` (via sys.path.insert(0, dirname(__file__)))
    resolves regardless of where the backend was started from."""
    if settings.sayro_voice_lab_dir:
        return Path(settings.sayro_voice_lab_dir)
    return script_path.parent if script_path else None


def seedvc_configured() -> bool:
    """Seed-VC is usable iff SEEDVC_DIR resolves to an existing checkout,
    SEEDVC_PYTHON resolves to an existing python, and the reference WAV exists."""
    sd = _resolve_seedvc_dir()
    py = _resolve_seedvc_python(sd) if sd is not None else ""
    ref = settings.seedvc_reference_wav
    if not (sd and py and ref):
        return False
    return _which(py) and sd.is_dir() and Path(ref).is_file()


def sayro_configured() -> bool:
    """The Route B wrapper is usable iff SAYRO_PYTHON + the wrapper script
    resolve AND Seed-VC is configured (the wrapper shells out to Seed-VC
    internally)."""
    script = _resolve_sayro_script()
    if script is None or not script.is_file():
        return False
    py = _resolve_sayro_python(script)
    if not _which(py):
        return False
    return seedvc_configured()


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
            "Local clone is not configured: set SEEDVC_REFERENCE_WAV to your "
            "reference WAV and ensure the vendored wrapper at "
            "services/routeb/b_sayro_then_seedvc.py plus a Seed-VC checkout "
            "(third_party/seed-vc or SEEDVC_DIR) with a working .venv-vc are "
            "available. You can also point SAYRO_PYTHON / SAYRO_SCRIPT / "
            "SAYRO_VOICE_LAB_DIR at an external voice-lab checkout for dev."
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
    s = {
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
            "languages": ["uz"],
            "busy": _local_clone_busy,
            "model": "sayro-seedvc",
            "seedvc_version": settings.seedvc_version,
            "diffusion_steps": settings.route_b_diffusion_steps,
            "wrapper_script": str(_resolve_sayro_script()) if _resolve_sayro_script() else None,
            "seedvc_dir": str(_resolve_seedvc_dir()) if _resolve_seedvc_dir() else None,
            "daemon": {
                "enabled": (not _daemon_disabled),
                "running": False,
                "disable_env": bool(_daemon_disabled),
                "pid": None,
            },
        },
        "fallback": "openai",
    }
    try:
        d = _routeb_daemon
        if d is not None:
            s["local_clone"]["daemon"].update({
                "running": d.is_alive(),
                "pid": d.pid,
            })
    except Exception:
        pass
    return s


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

# Regexes matching the timing/progress markers emitted by the real
# b_sayro_then_seedvc.py wrapper on stdout (verified against Windows E2E
# logs). All output is free-form and markers may move between wrapper
# versions; missing markers are tolerated — timing fields stay None and
# we fall back to directory scanning.
_R_LOADED = _re.compile(r"\[B\]\s+loaded\s+in\s+([0-9.]+)s")
_R_SAYRO_OUT = _re.compile(r"\[B\]\s+(t\d+)\s+->\s+(\S+)")
_R_PEAK_GPU = _re.compile(r"\[B\]\s+peak GPU memory:\s*(\S+)")
_R_VC_OUT = _re.compile(r"\[B\]\[vc\]\s+(\S+)\s+->\s+(\S+)")
_R_SAYRO_DONE = _re.compile(r"\[B\]\s+Sayro stage done")
_R_CONVERT_DONE = _re.compile(r"\[B\]\s+convert stage done")

# Child-process environment overrides. These are intentionally SAFE,
# quality-neutral, and additive — they do not change numerics, sampling,
# or model selection; they only prevent thread oversubscription and
# force I/O flushing so tail logs are available on failure.
_CHILD_ENV_HARDEN = {
    # Unbuffered stdout/stderr so [B] stage markers flush immediately;
    # also makes tail-log capture on crash/timeout reliable on Windows
    # where Python defaults to block buffering when not on a TTY.
    "PYTHONUNBUFFERED": "1",
    # Force UTF-8 for stdin/stdout/stderr. On Windows a pipe-attached
    # stdin defaults to the system ANSI codepage (cp1252), which
    # silently mangles Uzbek diacritics (Oʻ, Gʻ, ʻ) into ?/U+FFFD.
    # PYTHONIOENCODING is honored by the reconfigure() calls we added
    # in the daemon's run_daemon() as a fallback — see P1-2 in the
    # production audit.
    "PYTHONIOENCODING": "utf-8",
    # Force libgomp / MKL / OpenBLAS to single-threaded BLAS ops. The
    # wrapper already runs its GPU work in one process; extra CPU threads
    # thrash a laptop 6-core CPU during tensor prep / audio I/O and can
    # SLOW DOWN overall latency from contention. This does not touch
    # CUDA kernel parallelism — only CPU-side BLAS threads.
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
    # CuDNN benchmark + V8 API: picks fastest cuDNN conv algorithm for
    # the current input size on the first run; safe, quality-neutral,
    # and matches what Seed-VC already sets internally in many configs.
    "TORCH_CUDNN_V8_API_ENABLED": "1",
}


def _build_child_env() -> dict:
    """Build the environment dict for the Route B subprocess.

    Inherits os.environ (GPU drivers, CUDA_PATH, PATH, SYSTEMROOT, etc.
    must reach the child on Windows) and applies latency-safe overrides
    that do not change model numerics.
    """
    env = os.environ.copy()
    env.update(_CHILD_ENV_HARDEN)
    return env


def _parse_wrapper_markers(line: str, timings: dict, markers: dict) -> None:
    """Parse one line of wrapper stdout, updating timings/markers in place.

    We record wall-clock deltas from subprocess start for each stage:
      - wrapper_start_t   (implicit; set by caller)
      - sayro_load_s      (from "[B] loaded in Xs" — Sayro model load)
      - sayro_out         (from "[B] t01 -> <path>" — Sayro wrote TTS wav)
      - sayro_done_t      (from "[B] Sayro stage done" — Sayro fully done)
      - vc_out            (from "[B][vc] t01.wav -> <path>" — Seed-VC wrote
                          converted wav; <path> is relative to --out dir)
      - convert_done_t    (from "[B] convert stage done" — wrapper exiting)
    """
    m = _R_LOADED.search(line)
    if m and "sayro_load_s" not in timings:
        try:
            timings["sayro_load_s"] = float(m.group(1))
        except ValueError:
            pass
        return
    m = _R_SAYRO_OUT.search(line)
    if m and "sayro_out" not in markers:
        markers["sayro_out"] = m.group(2)
        timings.setdefault("sayro_t_done_s", time.monotonic() - timings.get("_t0", 0.0))
        return
    if _R_SAYRO_DONE.search(line):
        timings["sayro_done_s"] = round(
            time.monotonic() - timings.get("_t0", 0.0), 3
        )
        return
    m = _R_VC_OUT.search(line)
    if m:
        # Last matching vc output wins if multiple lines appear.
        markers["vc_out"] = m.group(2)
        timings["vc_t_done_s"] = round(
            time.monotonic() - timings.get("_t0", 0.0), 3
        )
        return
    if _R_CONVERT_DONE.search(line):
        timings["convert_done_s"] = round(
            time.monotonic() - timings.get("_t0", 0.0), 3
        )
        return
    m = _R_PEAK_GPU.search(line)
    if m:
        markers["peak_gpu_mem"] = m.group(1)


def _run_subprocess(cmd: list, timeout: int, cwd: str = None) -> dict:
    """Run `cmd` (argv list); raise RuntimeError on non-zero / timeout /
    missing executable. Streams stdout line-by-line to parse wrapper
    timing markers and keep a tail ring buffer for failure diagnostics.

    Returns a dict with keys:
        stdout_tail:  last 5 stdout lines (post-marker parse)
        stderr_tail:  last 5 stderr lines
        timings:      parsed per-stage timing dict (see _parse_wrapper_markers)
        markers:      parsed marker dict (vc_out path, sayro_out path, peak gpu)
        total_s:      wall-clock seconds inside subprocess
    """
    logger.debug("local-clone subprocess: cwd=%s argv=%s",
                 cwd or os.getcwd(),
                 " ".join(shlex.quote(c) for c in cmd))
    t0 = time.monotonic()
    timings = {"_t0": t0}
    markers: dict = {}
    out_tail: list[str] = []
    err_tail: list[str] = []
    proc = None
    try:
        popen_kwargs = dict(
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            env=_build_child_env(),
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,  # line-buffered for real-time parsing
        )
        # On POSIX, put the child in its own process group so
        # os.killpg() can terminate the entire tree (wrapper + Seed-VC
        # grandchild) on timeout. On Windows CREATE_NEW_PROCESS_GROUP
        # does NOT help us (taskkill /T /F is what actually works), so
        # we leave it off.
        if os.name != "nt":
            popen_kwargs["start_new_session"] = True
        proc = subprocess.Popen(cmd, **popen_kwargs)
    except FileNotFoundError as e:
        raise RuntimeError(f"local-clone executable not found: {cmd[0]}") from e

    # Drain BOTH stdout and stderr in daemon threads. Reading stdout
    # synchronously in the main thread would block forever when the
    # child is alive but silent (e.g. during a long GPU inference with
    # no output), preventing proc.wait() from ever being reached and
    # making the timeout unreachable. Using threads lets the main loop
    # poll for exit OR timeout while lines are streamed in real time.
    out_chunks: list[str] = []
    err_chunks: list[str] = []
    def _drain(pipe, tail, chunks, is_stdout: bool) -> None:
        try:
            for raw in pipe:
                line = raw.rstrip("\r\n")
                if line:
                    tail.append(line)
                    while len(tail) > 5:
                        tail.pop(0)
                    chunks.append(line)
                    if is_stdout:
                        logger.debug("route-b: %s", line)
                        _parse_wrapper_markers(line, timings, markers)
        except Exception:
            pass
    assert proc.stdout is not None and proc.stderr is not None
    out_thread = threading.Thread(
        target=_drain, args=(proc.stdout, out_tail, out_chunks, True),
        daemon=True,
    )
    err_thread = threading.Thread(
        target=_drain, args=(proc.stderr, err_tail, err_chunks, False),
        daemon=True,
    )
    out_thread.start()
    err_thread.start()

    deadline = t0 + timeout
    killed = False
    try:
        # Poll until the process exits or we exceed the deadline. The
        # drain threads keep streaming lines into timings/markers
        # concurrently; nothing blocks on pipe I/O in the main loop.
        while True:
            if proc.poll() is not None:
                break
            if time.monotonic() >= deadline:
                killed = True
                # Kill the whole process tree on timeout. On Windows
                # terminate() kills only the parent; taskkill /T /F is
                # the reliable way to kill the child python.exe and its
                # Seed-VC grandchild. On POSIX start_new_session=True
                # puts the child in its own process group so os.killpg
                # terminates everything (e.g. Seed-VC grandchildren).
                try:
                    if os.name == "nt":
                        subprocess.run(
                            ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                            capture_output=True, timeout=5,
                        )
                    else:
                        try:
                            os.killpg(os.getpgid(proc.pid), 9)
                        except Exception:
                            proc.kill()
                except Exception:
                    pass
                break
            time.sleep(0.05)
        # Wait for drain threads to flush final lines after exit/kill.
        out_thread.join(timeout=3.0)
        err_thread.join(timeout=3.0)
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
    except BaseException:
        # On any unexpected exception, make sure the child does not
        # outlive us.
        try:
            if proc.poll() is None:
                try:
                    if os.name != "nt":
                        os.killpg(os.getpgid(proc.pid), 9)
                    else:
                        proc.kill()
                except Exception:
                    proc.kill()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    pass
        except Exception:
            pass
        raise

    if killed:
        raise RuntimeError(
            f"local-clone subprocess timed out after {timeout}s: {cmd[0]}"
        )

    total_s = time.monotonic() - t0
    timings["total_s"] = round(total_s, 3)
    timings.pop("_t0", None)

    if proc.returncode != 0:
        tail_src = err_tail if err_tail else out_tail
        tail = " | ".join(tail_src[-5:])
        raise RuntimeError(
            f"local-clone subprocess failed ({cmd[0]}, exit={proc.returncode}): {tail}"
        )

    logger.info(
        "local-clone Route B timings (s): total=%.2f sayro_load=%s sayro_done=%s "
        "vc_done=%s peak_gpu=%s",
        total_s,
        timings.get("sayro_load_s"),
        timings.get("sayro_done_s"),
        timings.get("vc_t_done_s"),
        markers.get("peak_gpu_mem"),
    )
    return {
        "stdout_tail": out_tail,
        "stderr_tail": err_tail,
        "timings": timings,
        "markers": markers,
        "total_s": total_s,
    }


def _find_converted_output(out_dir: Path, source_stem: str) -> Path:
    """Route B wrapper delegates to Seed-VC V1 inference.py, which writes
    one WAV per source file into --output. The wrapper emits Sayro's raw
    TTS WAV under a directory like out/<stage>/<stem>.wav and the final
    Seed-VC-converted WAV under out/<stage>_vc/<stem>.wav (per the real
    b_sayro_then_seedvc.py output layout observed on Windows:
    out/b_sayro/t01.wav -> out/b_sayro_vc/t01.wav). We prefer WAVs whose
    immediate parent directory name ends with '_vc' (the Seed-VC
    conversion stage); ties fall back to newest-by-mtime. This prevents
    picking up Sayro-raw WAVs or intermediate artifacts when Seed-VC
    output is present."""
    candidates = [p for p in out_dir.rglob("*.wav") if p.is_file()]
    if not candidates:
        raise RuntimeError(
            f"Route B produced no converted WAV under {out_dir} "
            f"(source_stem={source_stem})"
        )
    def _score(p: Path):
        parent_name = p.parent.name
        is_vc_output = parent_name.endswith("_vc")
        # Score tuple (higher picked first): prefer _vc dir, then newest
        # mtime. Newest-only is unsafe when filesystem timestamp
        # granularity (e.g. FAT/network shares ~10 ms) makes the Sayro
        # intermediate and Seed-VC output appear to share an mtime.
        return (1 if is_vc_output else 0, p.stat().st_mtime)
    candidates.sort(key=_score, reverse=True)
    return candidates[0]


def _split_extra(extra: str) -> list:
    extra = (extra or "").strip()
    return shlex.split(extra) if extra else []


def _format_numbered_sentence(num: int, text: str) -> str:
    """Format one utterance as a line that the voice-lab `parse_numbered()`
    will accept. `parse_numbered()` splits on r\"^(\\d+)[.)]\\s*(.+)$\", so
    the canonical line is \"<num>. <text>\". One utterance per file; we
    always use num=1 to match --only 1.
    """
    # Collapse internal newlines to spaces — parse_numbered() splits on
    # splitlines() and would treat multi-line input as multiple entries.
    safe = " ".join((text or "").strip().splitlines()).strip()
    return f"{num}. {safe}"


def _build_route_b_cmd(sentences_file: Path, out_dir: Path) -> list:
    """Build the argv list for the Route B wrapper CLI.

    The wrapper (vendored at services/routeb/b_sayro_then_seedvc.py) expects:
      --stage all          run Sayro TTS then Seed-VC end-to-end
      --sentences <file>   numbered-sentences FILE (parse_numbered format)
      --only <N>           select numeric ids (we always pass "1")
      --out <dir>          output directory for converted WAV(s)
      --target <ref.wav>   Seed-VC reference voice target
      --seedvc-python <py> Python exe in the Seed-VC venv
      --seedvc-dir <dir>   Seed-VC checkout (wrapper uses as cwd for Seed-VC)
      --seedvc-version v2  Use Seed-VC V2 persistent batch inference
      --diffusion-steps N  Quality knob (default 15)
      --intelligibility / --similarity (default 0.8 each — matching the
        74.86s/5-sentence production benchmark)

    We write exactly one numbered sentence into a per-request temp
    sentences file, run --stage all --only 1 against it. Any extra
    operator tokens from ROUTE_B_EXTRA_ARGS are appended verbatim
    (shlex-split) so wrapper-side flag additions don't require code
    changes in BirOvoz.
    """
    script_path = _resolve_sayro_script()
    seedvc_dir = _resolve_seedvc_dir()
    seedvc_py = _resolve_seedvc_python(seedvc_dir)
    sayro_py = _resolve_sayro_python(script_path)
    ref_path = Path(settings.seedvc_reference_wav)

    version = (settings.seedvc_version or "v2").strip().lower()
    cmd = [
        sayro_py,
        str(script_path),
        "--stage", "all",
        "--sentences", str(sentences_file),
        "--only", "1",
        "--out", str(out_dir),
        "--target", str(ref_path),
        "--seedvc-python", seedvc_py,
        "--seedvc-dir", str(seedvc_dir),
        "--seedvc-version", version,
        "--diffusion-steps", str(settings.route_b_diffusion_steps),
        "--length-adjust", str(getattr(settings, "route_b_length_adjust", 1.0)),
        "--intelligibility", str(settings.route_b_intelligibility),
        "--similarity", str(settings.route_b_similarity),
    ]
    # V1-only flags (the V2 path ignores them; we only add them for V1 so
    # V2 CLI warnings don't drift into stderr if the wrapper tightens arg
    # parsing in future).
    if version == "v1":
        cmd += ["--inference-cfg", "0.8", "--auto-f0", "False", "--fp16", "True"]
    cmd += _split_extra(settings.route_b_extra_args)
    return cmd


def _route_b_cwd() -> Path:
    """cwd for the wrapper subprocess (see _resolve_wrapper_cwd)."""
    script = _resolve_sayro_script()
    return _resolve_wrapper_cwd(script)


# WAVE format tags we accept for the local-clone return path. The stdlib
# wave module only understands PCM integer (format 1); Seed-VC V1 on
# Windows emits 32-bit IEEE float PCM (format 3, pcm_f32le) at 22050 Hz
# mono, which is a perfectly playable WAV in every browser we support.
_WAVE_FORMAT_PCM = 1
_WAVE_FORMAT_IEEE_FLOAT = 3


def _validate_wav_bytes(data: bytes) -> None:
    """Validate a RIFF/WAVE container enough to ensure the browser can
    play it. Accepts PCM integer (format 1) and IEEE float (format 3);
    rejects truncated files, missing fmt/data chunks, zero-length audio,
    or non-WAVE containers. Raises RuntimeError with a diagnostic
    message on failure.

    We intentionally do NOT resample or coerce the bit depth here — the
    <audio> element decodes pcm_s16le and pcm_f32le at any standard rate
    natively.
    """
    if len(data) < 44:
        raise RuntimeError(
            f"Converted WAV is too small ({len(data)} bytes) to be a valid WAV"
        )
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise RuntimeError(
            "Converted audio is not a RIFF/WAVE file (bad header magic)"
        )
    # Walk RIFF chunks after the 12-byte master header.
    pos = 12
    end = len(data)
    fmt_found = False
    data_size = 0
    while pos + 8 <= end:
        cid = data[pos:pos + 4]
        try:
            (csize,) = struct.unpack("<I", data[pos + 4:pos + 8])
        except struct.error:
            break
        body_start = pos + 8
        body_end = body_start + csize
        if body_end > end:
            break
        if cid == b"fmt ":
            if csize < 14:
                raise RuntimeError("Converted WAV has a truncated fmt chunk")
            try:
                format_tag, channels, sample_rate, byte_rate, block_align, \
                    bits_per_sample = struct.unpack(
                        "<HHIIHH", data[body_start:body_start + 16]
                    )
            except struct.error as e:
                raise RuntimeError(f"Converted WAV fmt chunk is unreadable: {e}") from e
            if format_tag not in (_WAVE_FORMAT_PCM, _WAVE_FORMAT_IEEE_FLOAT):
                raise RuntimeError(
                    f"Converted WAV uses unsupported WAVE format tag {format_tag} "
                    f"(expected {_WAVE_FORMAT_PCM}=PCM int or "
                    f"{_WAVE_FORMAT_IEEE_FLOAT}=IEEE float)"
                )
            if channels < 1 or channels > 2:
                raise RuntimeError(
                    f"Converted WAV has unsupported channel count {channels}"
                )
            if sample_rate < 8000 or sample_rate > 192000:
                raise RuntimeError(
                    f"Converted WAV has implausible sample rate {sample_rate}"
                )
            if bits_per_sample not in (8, 16, 24, 32):
                raise RuntimeError(
                    f"Converted WAV has unsupported bits-per-sample {bits_per_sample}"
                )
            fmt_found = True
        elif cid == b"data":
            data_size = csize
        pos = body_end + (csize & 1)  # chunks are padded to 2-byte boundary
    if not fmt_found:
        raise RuntimeError("Converted WAV is missing a fmt chunk")
    if data_size <= 0:
        raise RuntimeError("Converted WAV has an empty data chunk (zero frames)")


# ---------------------------------------------------------------------------
# Route B persistent-daemon client (warm-TTS speed path).
#
# On first use we spawn a single long-lived `b_sayro_then_seedvc.py --daemon`
# process and keep it around for the lifetime of the backend. Jobs are
# submitted one at a time as one-line JSON on the daemon's stdin; results
# come back as one-line JSON on stdout containing a base64-encoded WAV.
# Sayro + Seed-VC models stay resident on the GPU across utterances, which
# eliminates the ~15-20s per-call Python/torch startup cost observed when
# the wrapper was respawned for every request.
#
# Fail-closed policy: if the daemon is dead / crashes mid-job / returns an
# error / times out, we (a) discard the bad handle, (b) respawn once and
# retry the single in-flight job, and (c) if the retry also fails, fall
# through to the legacy one-shot subprocess path _run_subprocess so the
# utterance still succeeds (just slower) and the caller never sees a hard
# failure from a transient daemon bug.
# ---------------------------------------------------------------------------

class RouteBDaemonClient:
    """Thread-safe client for one long-lived `b_sayro_then_seedvc.py --daemon`.

    Design:
      * Stdout/stderr are drained by dedicated daemon threads into a
        response queue (stdout) and a tail ring buffer (stderr). This
        avoids Windows pipe-buffering deadlocks -- we never block the
        main thread waiting for data while the child is blocked writing
        to a full pipe.
      * The outer _local_clone_lock serializes synthesize() calls so
        only one JSON job is ever in flight at a time.
      * On any sign of death (exit code / broken pipe / bad JSON /
        timeout) we kill the whole process tree (taskkill /T /F on
        Windows to reap the Seed-VC grandchild) and respawn once.
    """

    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self._call_lock = threading.Lock()
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._responses: "queue.Queue[dict]" = queue.Queue()
        self._stderr_tail: list[str] = []
        self._respawns: int = 0
        self._max_respawns: int = 4
        self._pid: int | None = None

    def _spawn(self) -> None:
        if self._proc is not None:
            self._shutdown_locked()
        script_path = _resolve_sayro_script()
        seedvc_dir = _resolve_seedvc_dir()
        seedvc_py = _resolve_seedvc_python(seedvc_dir)
        sayro_py = _resolve_sayro_python(script_path)
        if not (script_path and sayro_py and seedvc_dir and seedvc_py):
            raise RuntimeError("local-clone daemon: config incomplete")

        ref_path = Path(settings.seedvc_reference_wav)
        cmd = [
            sayro_py, str(script_path), "--daemon",
            "--target", str(ref_path),
            "--seedvc-python", seedvc_py,
            "--seedvc-dir", str(seedvc_dir),
            "--seedvc-version",
            (settings.seedvc_version or "v2").strip().lower(),
            "--diffusion-steps", str(settings.route_b_diffusion_steps),
            "--length-adjust",
            str(getattr(settings, "route_b_length_adjust", 1.0)),
            "--intelligibility", str(settings.route_b_intelligibility),
            "--similarity", str(settings.route_b_similarity),
        ]
        cmd += _split_extra(settings.route_b_extra_args)

        cwd = str(_resolve_wrapper_cwd(script_path))
        logger.info(
            "local-clone daemon spawning: cwd=%s argv=%s",
            cwd, " ".join(shlex.quote(c) for c in cmd),
        )
        popen_kwargs = dict(
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_build_child_env(),
            bufsize=0,
        )
        if os.name != "nt":
            popen_kwargs["start_new_session"] = True
        proc = subprocess.Popen(cmd, **popen_kwargs)
        responses: "queue.Queue[dict]" = queue.Queue()
        stderr_tail: list[str] = []
        self._proc = proc
        self._pid = proc.pid
        self._responses = responses
        self._stderr_tail = stderr_tail
        self._stderr_thread = threading.Thread(
            target=self._drain_stderr,
            args=(proc, proc.stderr, stderr_tail),
            daemon=True,
            name="routeb-daemon-stderr",
        )
        self._stdout_thread = threading.Thread(
            target=self._drain_stdout,
            args=(proc, proc.stdout, responses),
            daemon=True,
            name="routeb-daemon-stdout",
        )
        self._stderr_thread.start()
        self._stdout_thread.start()

        # Wait for the ready line. The daemon prints ready immediately
        # (models lazy-load on the first job), so this is just Python
        # startup + argparse (< 10s on warm disk, generous 60s for
        # cold AV-scanned Windows disks).
        ready = False
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                tail = " | ".join(self._stderr_tail[-5:])
                rc = self._proc.returncode
                self._shutdown_locked()
                raise RuntimeError(
                    f"local-clone daemon exited on startup "
                    f"(rc={rc}): {tail}"
                )
            try:
                msg = self._responses.get(timeout=0.2)
            except queue.Empty:
                continue
            if msg.get("type") == "ready":
                ready = True
                break
        if not ready:
            self._shutdown_locked()
            raise RuntimeError(
                "local-clone daemon: did not report ready within 60s"
            )
        logger.info("local-clone daemon ready (pid=%s)", self._pid)

    def _drain_stderr(self, proc, stderr, stderr_tail) -> None:
        """Drain one specific daemon stderr pipe.

        The Popen and pipe are passed at thread creation. Never use
        self._proc/self._stderr_tail here because restart can replace both
        while the old reader is still unwinding.
        """
        try:
            for raw in iter(stderr.readline, b""):
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                if not line:
                    continue
                logger.debug("route-b-daemon (stderr): %s", line)
                stderr_tail.append(line)
                while len(stderr_tail) > 100:
                    stderr_tail.pop(0)
        except (ValueError, OSError):
            pass
        finally:
            try:
                stderr.close()
            except Exception:
                pass

    def _drain_stdout(self, proc, stdout, responses) -> None:
        """Drain one specific daemon stdout pipe into one queue."""
        try:
            buf = b""
            while True:
                ch = stdout.read(1)
                if not ch:
                    break
                if ch == b"\n":
                    line_bytes = buf
                    buf = b""
                    line = line_bytes.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    if "ready" in line and "daemon" in line:
                        responses.put({"type": "ready"})
                        continue
                    if not line.startswith("{"):
                        logger.debug("route-b-daemon: %s", line[:300])
                        continue
                    try:
                        responses.put(
                            {"type": "result", "data": json.loads(line)}
                        )
                    except Exception as e:
                        logger.warning(
                            "route-b-daemon: bad JSON line: %s: %s",
                            e, line[:200],
                        )
                else:
                    buf += ch
                    if len(buf) > 10_000_000:
                        buf = b""
        except (ValueError, OSError):
            pass
        finally:
            try:
                stdout.close()
            except Exception:
                pass

    def _kill_tree(self) -> None:
        """Kill the daemon tree, close all pipe handles, and join readers.

        The operation is safe to repeat. Reader threads own the exact
        Popen/pipe objects from their spawn, so clearing self._proc cannot
        redirect an old reader into a replacement process.
        """
        proc = self._proc
        stdout_thread = self._stdout_thread
        stderr_thread = self._stderr_thread
        if proc is not None:
            pid = proc.pid
            try:
                try:
                    if proc.stdin:
                        proc.stdin.close()
                except Exception:
                    pass
                if proc.poll() is None:
                    if os.name == "nt":
                        try:
                            subprocess.run(
                                ["taskkill", "/T", "/F", "/PID", str(pid)],
                                capture_output=True, timeout=5,
                            )
                        except Exception:
                            try:
                                proc.kill()
                            except Exception:
                                pass
                    else:
                        try:
                            os.killpg(os.getpgid(pid), signal.SIGKILL)
                        except Exception:
                            try:
                                proc.kill()
                            except Exception:
                                pass
                try:
                    proc.wait(timeout=8)
                except Exception:
                    pass
            except Exception:
                pass
            # Close the parent-side handles even when the child had already
            # exited. This unblocks readers on Windows and prevents handle
            # accumulation across respawns.
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                try:
                    if stream is not None:
                        stream.close()
                except Exception:
                    pass

        join_deadline = time.monotonic() + 2.0
        for thread in (stdout_thread, stderr_thread):
            if thread is None or thread is threading.current_thread():
                continue
            remaining = max(0.0, join_deadline - time.monotonic())
            thread.join(timeout=remaining)
            if thread.is_alive():
                logger.warning(
                    "local-clone daemon reader thread did not terminate "
                    "within shutdown deadline: %s", thread.name,
                )
        self._proc = None
        self._pid = None
        self._stdout_thread = None
        self._stderr_thread = None

    def _shutdown_locked(self) -> None:
        self._kill_tree()

    def shutdown(self) -> None:
        with self._call_lock:
            self._shutdown_locked()

    def _ensure_alive(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return
        if self._respawns >= self._max_respawns:
            raise RuntimeError(
                "local-clone daemon: exceeded respawn budget "
                f"({self._max_respawns}); falling back to one-shot"
            )
        self._respawns += 1
        self._spawn()

    @staticmethod
    def _is_retryable_daemon_error(error: str) -> bool:
        """Return True only for a Seed-VC child death/broken-pipe result.

        Generic daemon errors, CUDA OOMs, malformed responses, and timeouts
        are deliberately not retried here; they continue to the existing
        one-shot fallback path. This keeps the retry bounded and avoids
        changing the timeout or OOM policy in this pass.
        """
        text = str(error or "").lower()
        return (
            "seed-vc daemon died" in text
            or "seed-vc daemon broken pipe" in text
        )

    def synthesize(self, text: str, work_dir: Path, timeout: float) -> bytes:
        job_id = uuid.uuid4().hex[:10]
        job = {
            "id": job_id,
            "text": text,
            "target": str(Path(settings.seedvc_reference_wav)),
            "work_dir": str(work_dir),
        }
        with self._call_lock:
            self._ensure_alive()
            t_job = time.monotonic()
            attempt = 0
            try:
                payload = (json.dumps(job, ensure_ascii=False) + "\n").encode("utf-8")
                while True:
                    # The first _ensure_alive() above covers the normal
                    # path. A retry after wrapper death arrives here with
                    # self._proc cleared, so respawn exactly once.
                    if self._proc is None or self._proc.poll() is not None:
                        if attempt >= 1:
                            raise RuntimeError(
                                "local-clone daemon died during retry"
                            )
                        self._shutdown_locked()
                        self._ensure_alive()
                        attempt += 1

                    try:
                        assert self._proc and self._proc.stdin
                        self._proc.stdin.write(payload)
                        self._proc.stdin.flush()
                    except (BrokenPipeError, OSError, ValueError) as e:
                        if attempt >= 1:
                            raise RuntimeError(
                                f"local-clone daemon retry write failed: {e}"
                            ) from e
                        logger.warning(
                            "local-clone daemon write failed (%s); respawning "
                            "and retrying same job",
                            e,
                        )
                        self._shutdown_locked()
                        self._ensure_alive()
                        attempt += 1
                        continue

                    # Preserve the existing per-write timeout behavior: the
                    # response window begins only after this attempt's job
                    # payload has been accepted by the wrapper.
                    deadline = time.monotonic() + timeout
                    resp: dict | None = None
                    retry_after_death = False
                    while time.monotonic() < deadline:
                        proc = self._proc
                        if proc is not None and proc.poll() is not None:
                            if attempt >= 1:
                                raise RuntimeError(
                                    "local-clone daemon died during retry "
                                    f"(rc={proc.returncode})"
                                )
                            logger.warning(
                                "local-clone daemon died mid-job; respawning "
                                "and retrying same job",
                            )
                            self._shutdown_locked()
                            self._ensure_alive()
                            attempt += 1
                            retry_after_death = True
                            break
                        remaining = deadline - time.monotonic()
                        try:
                            msg = self._responses.get(
                                timeout=min(0.5, max(0.01, remaining))
                            )
                        except queue.Empty:
                            continue
                        if msg.get("type") != "result":
                            continue
                        candidate = msg["data"]
                        if candidate.get("id") == job_id:
                            resp = candidate
                            break
                        logger.warning(
                            "local-clone daemon: stale id %s (want %s); skipping",
                            candidate.get("id"), job_id,
                        )

                    if retry_after_death:
                        continue
                    if resp is None:
                        self._shutdown_locked()
                        raise RuntimeError(
                            f"local-clone daemon timed out after {timeout:.0f}s"
                        )
                    if not resp.get("ok"):
                        err = resp.get("error") or "unknown daemon error"
                        dead = self._proc is None or self._proc.poll() is not None
                        if attempt == 0 and self._is_retryable_daemon_error(err):
                            logger.warning(
                                "local-clone Seed-VC daemon failed after job "
                                "acceptance; retrying same job once: %s", err,
                            )
                            if dead:
                                self._shutdown_locked()
                                self._ensure_alive()
                            attempt += 1
                            continue
                        if dead or ("CUDA out of memory" in err
                                    or "killed" in err.lower()):
                            self._shutdown_locked()
                        raise RuntimeError(f"local-clone daemon error: {err}")
                    wav_b64 = resp.get("wav_b64")
                    if not wav_b64:
                        raise RuntimeError(
                            "local-clone daemon response missing wav_b64"
                        )
                    try:
                        wav_bytes = base64.b64decode(wav_b64)
                    except Exception as e:
                        raise RuntimeError(
                            f"local-clone daemon wav_b64 decode failed: {e}"
                        ) from e
                    dt = resp.get("timings") or {}
                    if dt:
                        logger.info(
                            "local-clone daemon timings (s): total=%.2f",
                            dt.get("total_s", time.monotonic() - t_job),
                        )
                    self._respawns = max(0, self._respawns - 1)
                    return wav_bytes
            except Exception:
                if self._proc is not None and self._proc.poll() is not None:
                    self._shutdown_locked()
                raise

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def pid(self) -> int | None:
        return self._pid if self.is_alive() else None


# Module-level singleton.
_routeb_daemon: RouteBDaemonClient | None = None
_daemon_disabled: bool = bool(os.environ.get("BIROVOZ_DISABLE_ROUTEB_DAEMON", "").strip())


def _get_daemon() -> RouteBDaemonClient | None:
    """Return the singleton daemon client, or None if daemon mode is
    disabled (BIROVOZ_DISABLE_ROUTEB_DAEMON=1) or config is unusable."""
    global _routeb_daemon, _daemon_disabled
    if _daemon_disabled:
        return None
    # Don't even try the daemon if the wrapper doesn't support --daemon:
    # the flag was added alongside this client in the vendored wrapper;
    # older/external checkouts may not have it. The check is a simple
    # substring sniff of the wrapper source so we don't spawn a child
    # just to discover it exits with "unrecognized arguments".
    try:
        script = _resolve_sayro_script()
        if script is None:
            return None
        src = script.read_text(encoding="utf-8", errors="replace")
        if "--daemon" not in src:
            logger.info("local-clone wrapper lacks --daemon support; using one-shot path")
            _daemon_disabled = True
            return None
    except OSError:
        return None
    if _routeb_daemon is None:
        _routeb_daemon = RouteBDaemonClient()
    return _routeb_daemon


# Compatibility alias for main.py shutdown hook (pre-7cd)
close_route_b_worker = _shutdown_daemon

@atexit.register
def _shutdown_daemon() -> None:
    global _routeb_daemon
    if _routeb_daemon is not None:
        try:
            _routeb_daemon.shutdown()
        except Exception:
            pass
        _routeb_daemon = None


def _synthesize_via_daemon(text: str, work_dir: Path, timeout: float) -> bytes:
    """Attempt synthesis via the persistent daemon. Returns WAV bytes on
    success, raises RuntimeError on any failure (caller falls back)."""
    d = _get_daemon()
    if d is None:
        raise RuntimeError("daemon unavailable")
    return d.synthesize(text, work_dir, timeout)


def synthesize_local_clone(text: str, language: str) -> bytes:
    """CP5: invoke the vendored Route B wrapper (Sayro -> Seed-VC v2) for a
    single utterance, return converted WAV bytes.

    Per request we create a temp workspace with a numbered-sentences file
    (one line "1. <text>" matching parse_numbered()) and an output
    directory, then shell out to the wrapper with:
      --stage all --sentences <tmp>/sentences.txt --only 1
      --out <tmp>/out --target … --seedvc-python … --seedvc-dir …
      --seedvc-version v2 --diffusion-steps <N> --intelligibility 0.8
      --similarity 0.8
    with cwd = the directory containing the wrapper script (so its
    `from common import …` resolves to services/routeb/common.py).

    Serialized process-wide by _local_clone_lock so concurrent calls can
    never load Sayro simultaneously and OOM the GPU. Raises RuntimeError
    on any failure so tts.synthesize falls back to OpenAI with a truthful
    report.

    Pre-conditions:
      * local_clone_configured() is True (checked by caller).
      * language == 'uz' (Kazakh stays on OpenAI at the tts.synthesize layer).
    """
    if not text or not text.strip():
        raise RuntimeError("local-clone: empty text")
    if not _local_clone_supported_language(language):
        raise RuntimeError(
            f"local-clone: language {language!r} not supported in MVP "
            f"(Uzbek only)"
        )

    tmp_dir = Path(tempfile.mkdtemp(prefix="birovoz_localclone_"))
    out_dir = tmp_dir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    # Write the single utterance as a numbered-sentences FILE that
    # parse_numbered() will accept: one line "1. <text>" (UTF-8). Used
    # only by the one-shot fallback path; the daemon accepts text inline.
    sentences_file = tmp_dir / "sentences.txt"
    sentences_file.write_text(
        _format_numbered_sentence(1, text) + "\n",
        encoding="utf-8",
    )
    lock_wait_t0: float = 0.0
    try:
        global _local_clone_busy
        # Time how long we spent waiting for the lock (queueing behind
        # another in-flight clone) — useful to separate lock contention
        # from real model/inference time in logs.
        lock_wait_t0 = time.monotonic()
        with _local_clone_lock:
            lock_wait_s = round(time.monotonic() - lock_wait_t0, 3)
            _local_clone_busy = True
            data: bytes | None = None
            mode: str = "daemon"
            daemon_err: str | None = None
            try:
                # --- Fast path: persistent daemon (warm TTS) ---------
                # Skip the sentences file + fresh subprocess entirely;
                # send text over stdin JSONL and get the WAV back as
                # base64. On daemon-path failure we fall through to the
                # legacy one-shot subprocess so the utterance still
                # completes (just slower) — no hard failure for the
                # caller.
                try:
                    t0 = time.monotonic()
                    data = _synthesize_via_daemon(
                        text, out_dir,
                        timeout=settings.local_clone_timeout_s,
                    )
                    total_s = round(time.monotonic() - t0, 3)
                    logger.info(
                        "local-clone (daemon) produced %d byte WAV | "
                        "lock_wait=%.2fs total=%.2fs",
                        len(data), lock_wait_s, total_s,
                    )
                except Exception as de:
                    daemon_err = str(de)
                    logger.warning(
                        "local-clone daemon path failed (%s); "
                        "falling back to one-shot subprocess", daemon_err,
                    )
                    mode = "oneshot"

                # --- Slow path: one-shot subprocess (fallback) -------
                if data is None:
                    cmd = _build_route_b_cmd(sentences_file, out_dir)
                    cwd = str(_route_b_cwd()) if _route_b_cwd() else None
                    raw = _run_subprocess(
                        cmd,
                        timeout=settings.local_clone_timeout_s,
                        cwd=cwd,
                    )
                    if not isinstance(raw, dict):
                        raw = {"timings": {}, "markers": {}, "total_s": 0.0}
                    result = raw
                    # Resolve the converted WAV. Prefer the exact
                    # relative path the wrapper printed in "[B][vc]
                    # t01.wav -> <relpath>" (relative to --out dir);
                    # fall back to directory scanning if the marker was
                    # missing (older wrapper / log format drift).
                    vc_rel = result.get("markers", {}).get("vc_out")
                    converted = None
                    if vc_rel:
                        candidate = out_dir / vc_rel
                        if candidate.is_file():
                            converted = candidate
                    if converted is None:
                        converted = _find_converted_output(out_dir, "1")
                    data = converted.read_bytes()
                    timings = result.get("timings", {})
                    timings["lock_wait_s"] = lock_wait_s
                    logger.info(
                        "local-clone (one-shot) produced %d byte WAV from %s | "
                        "lock_wait=%.2fs total=%.2fs sayro_load=%s "
                        "sayro_done=%s vc_done=%s peak_gpu=%s daemon_err=%s",
                        len(data), converted,
                        lock_wait_s, result.get("total_s", 0.0),
                        timings.get("sayro_load_s"), timings.get("sayro_done_s"),
                        timings.get("vc_t_done_s"),
                        result.get("markers", {}).get("peak_gpu_mem"),
                        daemon_err,
                    )
            finally:
                _local_clone_busy = False

        if not data:
            raise RuntimeError("Route B produced no audio data")
        # Validate the RIFF/WAVE container (accepts PCM int AND IEEE float,
        # since Seed-VC V1 / V2 emit both variants depending on platform;
        # browsers play both natively).
        try:
            _validate_wav_bytes(data)
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
