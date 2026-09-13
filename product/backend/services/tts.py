"""
Text-to-Speech service.

OpenAI tts-1 — cheap, multilingual TTS output.
Converts AI response text to spoken audio.
"""

import base64
import io
import logging
import wave
from pathlib import Path
from typing import Optional

from openai import OpenAI, APIError

from product.backend.config import settings
from product.backend.services import voice_clone

logger = logging.getLogger(__name__)


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

def synthesize(text: str, language: str, report: Optional[dict] = None) -> bytes:
    """Convert text to speech audio bytes.

    VC1: dispatches through the ACTIVE voice provider — OpenAI by default,
    ElevenLabs when selected (env TTS_PROVIDER=elevenlabs, or switched at
    runtime via /api/voice/provider) AND fully configured. If ElevenLabs
    fails at runtime, falls back to the pre-VC1 OpenAI path (mock in mock
    mode) so the pipeline never hard-fails.

    Args:
        text: Text to speak.
        language: ISO code ('uz' or 'kk') — used for voice selection where
                 the provider is multilingual.
        report: Optional dict filled with the provider/model ACTUALLY used,
                so provider_info stays truthful across fallbacks.

    Returns:
        Raw WAV audio bytes.
    """
    if voice_clone.resolved_provider() == "elevenlabs":
        try:
            data = voice_clone.synthesize_elevenlabs(text, language)
            if report is not None:
                report.update(provider="elevenlabs",
                              model=voice_clone.active_model_name())
            return data
        except Exception as e:
            logger.warning("ElevenLabs TTS failed (%s) — falling back to OpenAI", e)

    if settings.mock_mode:
        if report is not None:
            report.update(provider="openai", model=settings.tts_model)
        return _mock_synthesize(text, language)

    if report is not None:
        report.update(provider="openai", model=settings.tts_model)
    return _openai_synthesize(text, language)


def synthesize_b64(text: str, language: str, report: Optional[dict] = None) -> str:
    """Convert text to speech and return base64-encoded WAV."""
    audio_bytes = synthesize(text, language, report=report)
    return base64.b64encode(audio_bytes).decode("ascii")


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