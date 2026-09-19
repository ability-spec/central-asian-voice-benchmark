"""
Text-to-Speech service.

OpenAI tts-1 — cheap, multilingual TTS output.
Converts AI response text to spoken audio.
"""

import base64
import io
import logging
import threading
import wave
from pathlib import Path
from typing import Optional

from openai import OpenAI, APIError

from product.backend.config import settings
from product.backend.services import voice_clone

logger = logging.getLogger(__name__)

# Thread-local slot for per-call reporting. Callers (routers/turn.py) can
# retrieve the report of the most recent synthesize() on THIS thread via
# _last_report() / _take_last_report() after synthesize_b64 returns. This
# preserves the legacy `synthesize_b64(text, lang) -> str` seam so existing
# monkeypatches in tests that use a 2-arg lambda keep working.
_thread_local = threading.local()


def _set_last_report(report: dict) -> None:
    _thread_local.last_report = dict(report) if report else {}


def take_last_report() -> dict:
    """Pop and return the report for the most recent synthesize() call on
    this thread; returns {} if none was recorded. Safe to call repeatedly;
    each call consumes the stored report."""
    rep = getattr(_thread_local, "last_report", None) or {}
    _thread_local.last_report = {}
    return rep


# ---------- Mock TTS ----------

def _mock_synthesize(text: str, language: str) -> bytes:
    """Generate a minimal valid WAV file as mock audio."""
    import struct
    import wave

    # Generate a short 1-second sine wave WAV as placeholder
    sample_rate = 16000
    duration = 1.0
    frequency = 440.0
    num_samples = int(sample_rate * duration)

    samples = []
    for i in range(num_samples):
        value = int(8000 * __import__("math").sin(2 * __import__("math").pi * frequency * i / sample_rate))
        # clamp to 16-bit
        value = max(-32768, min(32767, value))
        samples.append(struct.pack("<h", value))

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"".join(samples))

    return buf.getvalue()


# ---------- Real TTS (OpenAI) ----------

def _openai_synthesize(text: str, language: str) -> bytes:
    """Generate speech audio from text using OpenAI TTS API."""
    client = OpenAI(api_key=settings.openai_api_key, timeout=30.0)

    last_err = None
    for attempt in range(2):
        try:
            response = client.audio.speech.create(
                model=settings.tts_model,
                voice=settings.tts_voice,
                input=text,
                response_format="wav",
                timeout=30.0,
            )
            return response.content
        except APIError as e:
            last_err = e
            logger.warning("TTS attempt %d failed: %s", attempt + 1, e)
            if attempt == 1:
                raise last_err
    return b""  # unreachable


# ---------- Public API ----------

def _fill_report(report: Optional[dict], provider: str, model: str) -> None:
    if report is not None:
        report.update(provider=provider, model=model)


def synthesize(text: str, language: str, report: Optional[dict] = None) -> bytes:
    """Convert text to speech audio bytes.

    Dispatch goes through the ACTIVE voice provider:
      * OpenAI by default (mock in mock mode).
      * ElevenLabs when selected AND fully configured (VC1).
      * local-clone (Sayro -> Seed-VC) when selected AND fully configured (CP5).
    If the selected non-OpenAI provider fails at runtime, we fall back to
    the pre-VC1 OpenAI/mock path so the pipeline never hard-fails. The
    `report` dict is always filled with the provider/model ACTUALLY used,
    so result-card provider_info stays truthful across fallbacks.

    Args:
        text: Text to speak.
        language: ISO code ('uz' or 'kk').
        report: Optional dict filled with the provider/model ACTUALLY used.
                When omitted (default), the report is stored to thread-local
                storage retrievable via take_last_report() — this preserves
                the legacy `synthesize_b64(text, lang)` call seam.

    Returns:
        Raw WAV audio bytes.
    """
    own_report = report is None
    if own_report:
        report = {}
    rp = voice_clone.resolved_provider()

    if rp == "elevenlabs":
        try:
            data = voice_clone.synthesize_elevenlabs(text, language)
            _fill_report(report, "elevenlabs", settings.elevenlabs_tts_model)
            if own_report:
                _set_last_report(report)
            return data
        except Exception as e:
            logger.warning("ElevenLabs TTS failed (%s) — falling back to OpenAI", e)

    if rp == "local-clone" and voice_clone._local_clone_supported_language(language):
        try:
            data = voice_clone.synthesize_local_clone(text, language)
            _fill_report(report, "local-clone", "sayro-seedvc")
            if own_report:
                _set_last_report(report)
            return data
        except Exception as e:
            logger.error("FALLBACK local-clone -> %s: %s",
                         "mock" if settings.mock_mode else "openai", e)

    if settings.mock_mode:
        _fill_report(report, "openai", settings.tts_model)
        if own_report:
            _set_last_report(report)
        return _mock_synthesize(text, language)

    _fill_report(report, "openai", settings.tts_model)
    if own_report:
        _set_last_report(report)
    return _openai_synthesize(text, language)


def synthesize_b64(text: str, language: str, report: Optional[dict] = None) -> str:
    """Convert text to speech and return base64-encoded WAV.

    `report` is optional for backward compatibility with tests/monkeypatches
    that only pass (text, language). When `report` is omitted, the report
    dict is recorded on thread-local storage; callers in concurrent
    contexts retrieve it via take_last_report() after the call returns.
    """
    audio_bytes = synthesize(text, language, report=report)
    return base64.b64encode(audio_bytes).decode("ascii")


def _merge_part_reports(part_reports: list) -> dict:
    """Reduce a list of per-part report dicts into a single effective report.

    DUB3 aggregates concurrent per-sentence TTS calls. If ANY sentence fell
    back to OpenAI (e.g. because ElevenLabs / local-clone failed for that
    part) we surface "openai" as the effective provider — conservative but
    truthful; the result card and provider_info never claim a clone ran
    when part of the audio did not. When all parts share the same non-
    OpenAI provider/model we report that. Returns {} when no reports were
    produced (defensive)."""
    reports = [r for r in (part_reports or []) if r and isinstance(r, dict)]
    if not reports:
        return {}
    providers = {r.get("provider") for r in reports}
    if providers == {"elevenlabs"}:
        return {"provider": "elevenlabs", "model": settings.elevenlabs_tts_model}
    if providers == {"local-clone"}:
        return {"provider": "local-clone", "model": "sayro-seedvc"}
    # Mixed, or at least one openai fallback -> report openai (truthful).
    return {"provider": "openai", "model": settings.tts_model}


def concat_wav_b64(parts_b64: list) -> str:
    """DUB3: join base64 WAV parts into one valid base64 WAV.

    Used to keep the legacy single-`audio` field correct (full dub) while
    `audio_parts` carries the per-sentence queue. Falls back to the first
    part if any input is not a parseable/consistent WAV, so the backward
    compatible field is never worse than a valid clip.
    """
    if not parts_b64:
        return ""
    if len(parts_b64) == 1:
        return parts_b64[0]
    frames = []
    params = None
    try:
        for blob_b64 in parts_b64:
            with wave.open(io.BytesIO(base64.b64decode(blob_b64)), "rb") as wf:
                p = wf.getparams()
                if params is None:
                    params = (p.nchannels, p.sampwidth, p.framerate)
                elif (p.nchannels, p.sampwidth, p.framerate) != params:
                    logger.warning("concat_wav_b64: inconsistent WAV params; "
                                   "falling back to first part")
                    return parts_b64[0]
                frames.append(wf.readframes(wf.getnframes()))
    except Exception as e:  # undecodable part etc. — keep something valid
        logger.warning("concat_wav_b64: %s; falling back to first part", e)
        return parts_b64[0]
    out = io.BytesIO()
    with wave.open(out, "wb") as wf:
        wf.setnchannels(params[0])
        wf.setsampwidth(params[1])
        wf.setframerate(params[2])
        wf.writeframes(b"".join(frames))
    return base64.b64encode(out.getvalue()).decode("ascii")