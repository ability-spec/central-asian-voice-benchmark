"""
Optional voice-provider endpoints (VC1).

  GET  /api/voice/status    — what TTS provider is active / configured
  POST /api/voice/provider  — switch active TTS provider (openai | elevenlabs)
  POST /api/voice/enroll    — consent-gated enrollment of the user's OWN or
                              explicitly authorized voice (1-5 samples)

No secrets are returned or stored here; the enrolled voice_id lives in the
out-of-repo config (settings.voice_config_path).
"""

import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from product.backend.config import settings
from product.backend.services import voice_clone

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice", tags=["voice"])


class VoiceProviderRequest(BaseModel):
    provider: str


@router.get("/status")
async def voice_status():
    """Report the active + configured voice providers (no secrets)."""
    return voice_clone.status()


@router.post("/provider")
async def set_voice_provider(req: VoiceProviderRequest):
    try:
        voice_clone.set_provider(req.provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return voice_clone.status()


@router.post("/enroll")
async def enroll_voice(
    audio: list[UploadFile] = File(...),
    consent: str = Form(""),
    name: str = Form("My voice"),
):
    """Enroll a cloned voice. Consent-gated; 1-5 samples; samples are deleted
    after processing; only the voice_id is stored (outside the repository)."""
    if not settings.elevenlabs_api_key:
        raise HTTPException(
            status_code=503,
            detail="Voice enrollment unavailable: ELEVENLABS_API_KEY is not configured.",
        )
    try:
        result = voice_clone.enroll(audio, consent=consent, name=name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Voice enrollment failed: %s", e)
        raise HTTPException(
            status_code=502,
            detail="Voice enrollment failed at the provider. Please try again.",
        )
    return {
        "enrolled": True,
        "voice_id": result["voice_id"],
        "status": voice_clone.status(),
    }
