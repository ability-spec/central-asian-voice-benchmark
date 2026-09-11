"""
Central Asian Voice AI — Pydantic models for request/response.
"""

from pydantic import BaseModel, Field
from typing import Optional


# --- Request models ---

class TurnRequest(BaseModel):
    """Request body for POST /api/turn (multipart form)."""
    conversation_id: str = Field(
        ..., description="Unique conversation/session identifier"
    )
    language: str = Field(
        ..., pattern="^(uz|kk)$",
        description="Target language: 'uz' for Uzbek, 'kk' for Kazakh",
    )


# --- Response models ---

class TurnResponse(BaseModel):
    """Response from POST /api/turn."""
    conversation_id: str
    turn_number: int
    transcript: str
    response_text: str
    audio: str  # base64-encoded WAV audio bytes
    # DUB3: per-sentence base64 WAV parts for queue playback (dub mode only).
    # `audio` stays the full concatenated dub, so older consumers are
    # unaffected; None whenever parts do not apply.
    audio_parts: Optional[list] = Field(
        default=None,
        description="Per-sentence base64 WAV parts (dub mode, >1 sentence)",
    )
    language: str
    provider_info: dict = Field(
        default_factory=dict,
        description="Which provider/model handled each pipeline stage",
    )
    error: Optional[str] = None
    # Reference-based scoring (MVP benchmark mode). Null/False when the
    # request carried no usable reference_text.
    wer: Optional[float] = Field(
        default=None,
        description="Word error rate vs reference_text; null when unscored",
    )
    cer: Optional[float] = Field(
        default=None,
        description="Character error rate vs reference_text; null when unscored",
    )
    scored: bool = Field(
        default=False,
        description="True when reference_text was provided and scoring ran",
    )
    stt_ms: int = Field(default=0, description="STT stage latency in ms")
    llm_ms: int = Field(default=0, description="LLM stage latency in ms")
    tts_ms: int = Field(default=0, description="TTS stage latency in ms")
    total_ms: int = Field(
        default=0, description="Pipeline total (stt_ms + llm_ms + tts_ms)"
    )


# --- Health models ---

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    mock_mode: bool = False
    stt_provider: str = ""
    llm_provider: str = ""
    tts_provider: str = ""
    uptime_seconds: float = 0.0