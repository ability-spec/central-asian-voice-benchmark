"""
POST /api/turn — the main pipeline endpoint.

Takes audio + conversation_id + language, returns transcript + AI response + audio.
"""

import io
import logging
import asyncio
import subprocess
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse

from product.backend.config import settings
from product.backend.models import TurnRequest, TurnResponse
from product.backend.services.stt import transcribe
from product.backend.services.llm import respond
from product.backend.services.tts import synthesize_b64
from product.backend.services.session import session_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["turn"])

# Allowed audio MIME types
ALLOWED_AUDIO_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/ogg",
    "audio/webm",
    "audio/webm;codecs=opus",
    "audio/x-m4a",
    "audio/mp4",
}


async def _to_wav(src_path: Path, dst_path: Path) -> None:
    """Normalize any browser audio to 16 kHz mono 16-bit PCM WAV via ffmpeg."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(src_path),
        "-ar", "16000",
        "-ac", "1",
        "-sample_fmt", "s16",
        "-f", "wav",
        str(dst_path),
    ]
    proc = await asyncio.get_running_loop().run_in_executor(
        None, lambda: subprocess.run(cmd, capture_output=True, text=True)
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr.strip()}")
    if not dst_path.exists() or dst_path.stat().st_size == 0:
        raise RuntimeError("ffmpeg produced empty output WAV")


def _get_audio_duration_seconds(file_bytes: bytes, content_type: str) -> float:
    """Estimate audio duration via ffprobe for accuracy."""
    import tempfile, os
    if "wav" not in content_type:
        with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", tmp_path],
                capture_output=True, text=True, timeout=5
            )
            val = result.stdout.strip()
            return float(val) if val else 0.0
        except Exception:
            return 0.0
        finally:
            try: os.unlink(tmp_path)
            except Exception: pass
    data_bytes = max(0, len(file_bytes) - 44)
    return data_bytes / 32000.0


@router.post("/turn")
async def handle_turn(
    audio: UploadFile = File(...),
    conversation_id: str = Form(...),
    language: str = Form(...),
):
    """Process one turn of the voice conversation pipeline.

    Pipeline: Audio Upload → STT → LLM → TTS → Response
    """
    request_id = uuid.uuid4().hex[:8]
    logger.info("[%s] Turn start | conv=%s lang=%s", request_id, conversation_id, language)

    # --- 1. Validate language ---
    if language not in ("uz", "kk"):
        raise HTTPException(status_code=400, detail=f"Invalid language '{language}'. Must be 'uz' or 'kk'.")

    # --- 2. Validate content type ---
    if audio.content_type and audio.content_type not in ALLOWED_AUDIO_TYPES:
        logger.warning("[%s] Unusual content-type: %s", request_id, audio.content_type)
        # Don't block — let the provider handle unknown types

    # --- 3. Read and validate audio ---
    audio_bytes = await audio.read()
    if len(audio_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty audio file.")

    if len(audio_bytes) > settings.max_audio_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"Audio too large. Max {settings.max_audio_size_mb} MB.",
        )

    # Rough duration check
    estimated_duration = _get_audio_duration_seconds(audio_bytes, audio.content_type or "audio/wav")
    if estimated_duration > settings.max_audio_duration_seconds:
        raise HTTPException(
            status_code=413,
            detail=f"Audio too long ({estimated_duration:.1f}s). Max {settings.max_audio_duration_seconds}s.",
        )
    logger.info("[%s] Audio received: %d bytes (est. %.1fs)", request_id, len(audio_bytes), estimated_duration)

    # --- 4. Check session limits ---
    if session_manager.is_max_turns_reached(conversation_id):
        raise HTTPException(
            status_code=429,
            detail=f"Session '{conversation_id}' has reached the maximum of {settings.max_turns_per_session} turns.",
        )

    # --- 5. Save uploaded audio ---
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    ext = "webm" if audio.content_type and "webm" in audio.content_type else "wav"
    safe_filename = f"{request_id}_{conversation_id}_{language}_raw.{ext}"
    raw_path = settings.upload_dir / safe_filename
    wav_path = settings.upload_dir / f"{request_id}_{conversation_id}_{language}_norm.wav"
    with open(raw_path, "wb") as f:
        f.write(audio_bytes)
    logger.info("[%s] Audio saved to %s (%s, %d bytes)", request_id, raw_path, audio.content_type, len(audio_bytes))

    # Normalize to 16 kHz mono 16-bit PCM WAV for STT
    try:
        await _to_wav(raw_path, wav_path)
    except Exception as e:
        logger.error("[%s] Audio conversion failed: %s", request_id, str(e))
        raise HTTPException(status_code=422, detail=f"Audio conversion failed: {str(e)}")

    # --- 6. STT ---
    t0 = time.time()
    try:
        transcript = transcribe(wav_path, language, "audio/wav")
    except Exception as e:
        logger.error("[%s] STT failed: %s", request_id, str(e))
        raise HTTPException(status_code=502, detail=f"STT failed: {str(e)}")
    stt_time = time.time() - t0
    logger.info("[%s] STT (%s): %.2fs | transcript=%r", request_id, language, stt_time, transcript[:80])

    # --- 7. LLM ---
    t0 = time.time()
    try:
        response_text = respond(conversation_id, transcript, language)
    except Exception as e:
        logger.error("[%s] LLM failed: %s", request_id, str(e))
        raise HTTPException(status_code=502, detail=f"LLM failed: {str(e)}")
    llm_time = time.time() - t0
    logger.info("[%s] LLM (%s): %.2fs | response=%r", request_id, language, llm_time, response_text[:80])

    # --- 8. TTS ---
    t0 = time.time()
    try:
        audio_b64 = synthesize_b64(response_text, language)
    except Exception as e:
        logger.error("[%s] TTS failed: %s", request_id, str(e))
        raise HTTPException(status_code=502, detail=f"TTS failed: {str(e)}")
    tts_time = time.time() - t0
    logger.info("[%s] TTS: %.2fs | audio size=%d bytes", request_id, tts_time, len(audio_b64))

    # --- 9. Build response ---
    turn_number = session_manager.get_turn_count(conversation_id)

    response = TurnResponse(
        conversation_id=conversation_id,
        turn_number=turn_number,
        transcript=transcript,
        response_text=response_text,
        audio=audio_b64,
        language=language,
        provider_info={
            "stt": f"{settings.stt_provider}/{settings.stt_model}",
            "llm": f"{settings.llm_provider}/{settings.llm_model}",
            "tts": f"{settings.tts_provider}/{settings.tts_model}",
            "mock_mode": settings.mock_mode,
        },
    )

    logger.info(
        "[%s] Done | turn=%d | stt=%.2fs llm=%.2fs tts=%.2fs total=%.2fs",
        request_id, turn_number,
        stt_time, llm_time, tts_time,
        stt_time + llm_time + tts_time,
    )

    return response