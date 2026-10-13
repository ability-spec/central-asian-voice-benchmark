"""
Health-check endpoint.
"""

import time
import logging
import shutil

from fastapi import APIRouter

from product.backend.models import HealthResponse
from product.backend.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

_start_time = time.time()


@router.get("/health", response_model=HealthResponse)
async def health():
    """Simple health check — returns service status and provider configuration."""
    return HealthResponse(
        status="ok",
        version="0.1.0",
        mock_mode=settings.mock_mode,
        stt_provider=f"{settings.stt_provider}/{settings.stt_model}",
        llm_provider=f"{settings.llm_provider}/{settings.llm_model}",
        tts_provider=f"{settings.tts_provider}/{settings.tts_model}",
        uptime_seconds=time.time() - _start_time,
        audio_tools_ready=bool(shutil.which("ffmpeg") and shutil.which("ffprobe")),
        max_audio_duration_seconds=settings.max_audio_duration_seconds,
        max_audio_size_mb=settings.max_audio_size_mb,
        max_turns_per_session=settings.max_turns_per_session,
    )