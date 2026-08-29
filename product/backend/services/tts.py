"""
Text-to-Speech service.

OpenAI tts-1 — cheap, multilingual TTS output.
Converts AI response text to spoken audio.
"""

import base64
import io
import logging
from pathlib import Path
from typing import Optional

from openai import OpenAI, APIError

from product.backend.config import settings

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

def synthesize(text: str, language: str) -> bytes:
    """Convert text to speech audio bytes.

    Args:
        text: Text to speak.
        language: ISO code ('uz' or 'kk') — currently used for voice selection
                 (OpenAI voices are multilingual).

    Returns:
        Raw WAV audio bytes.
    """
    if settings.mock_mode:
        return _mock_synthesize(text, language)

    return _openai_synthesize(text, language)


def synthesize_b64(text: str, language: str) -> str:
    """Convert text to speech and return base64-encoded WAV."""
    audio_bytes = synthesize(text, language)
    return base64.b64encode(audio_bytes).decode("ascii")