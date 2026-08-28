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
    language: str
    provider_info: dict = Field(
        default_factory=dict,
        description="Which provider/model handled each pipeline stage",
    )
    error: Optional[str] = None


# --- Health models ---

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    mock_mode: bool = False
    stt_provider: str = ""
    llm_provider: str = ""
    tts_provider: str = ""
    uptime_seconds: float = 0.0