"""
Speech-to-Text service.

OpenAI gpt-4o-transcribe — CONFIRMED working for both Uzbek and Kazakh
per benchmark research (Phase 1, gpt-4o-transcribe, CONFIRMED WORKING).

Since DUB1 it also accepts English ('en') as a source language for the
dubbing pipeline (English speech -> translated -> dubbed audio).
"""

import io
import logging
from pathlib import Path
from typing import Optional

from openai import OpenAI, APIError

from product.backend.config import settings

logger = logging.getLogger(__name__)


# ---------- Mock STT (no API key) ----------

MOCK_TRANSCRIPTS = {
    "uz": "Salom, buzbekcha test ovoz.",
    "kk": "Сәлем, бұл қазақша тест дауыс.",
    "en": "Hello, this is an English test voice.",
}


def _mock_transcribe(audio_path: Path, language: str, content_type: str = "audio/wav") -> str:
    logger.info("MOCK STT returning canned transcript for %s", language)
    return MOCK_TRANSCRIPTS.get(language, MOCK_TRANSCRIPTS["uz"])


# ---------- Real STT (OpenAI) ----------

def _openai_transcribe(audio_path: Path, language: str, content_type: str = "audio/wav") -> str:
    """Transcribe audio using OpenAI gpt-4o-transcribe.

    Uses prompt-based language hint per benchmark findings:
    - Uzbek: prompt="Uzbek" (ISO 'uz' rejected by API)
    - Kazakh: prompt="Kazakh"
    - English (DUB1 dubbing source): prompt="English"
    """
    language_prompt = {
        "uz": "Uzbek",
        "kk": "Kazakh",
        "en": "English",
    }
    last_err = None
    for attempt in range(2):
        try:
            client = OpenAI(api_key=settings.openai_api_key, timeout=30.0)
            with open(audio_path, "rb") as f:
                transcript = client.audio.transcriptions.create(
                    model=settings.stt_model,
                    file=(audio_path.name, f, content_type),
                    prompt=language_prompt.get(language, ""),
                    response_format="json",
                    timeout=30.0,
                )
            return transcript.text.strip()
        except APIError as e:
            last_err = e
            logger.warning("STT attempt %d failed: %s", attempt + 1, e)
            if attempt == 1:
                raise last_err
    return ""


# ---------- Public API ----------

def transcribe(audio_path: Path, language: str, content_type: str = "audio/wav") -> str:
    """Transcribe an audio file. Returns transcript text.

    Args:
        audio_path: Path to audio file.
        language: ISO code ('uz', 'kk', or 'en' for dubbing).
        content_type: Original MIME type of the uploaded audio file.

    Returns:
        Transcribed text string.
    """
    if settings.mock_mode:
        return _mock_transcribe(audio_path, language)

    return _openai_transcribe(audio_path, language, content_type)