"""
Central Asian Voice AI — Backend Configuration

All secrets loaded from environment variables.
Supports mock mode when API keys are absent.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    # OpenAI
    openai_api_key: str = field(
        default_factory=lambda: os.environ.get("OPENAI_API_KEY", "")
    )

    # ElevenLabs (optional fallback for TTS)
    elevenlabs_api_key: str = field(
        default_factory=lambda: os.environ.get("ELEVENLABS_API_KEY", "")
    )

    # Server
    host: str = field(default_factory=lambda: os.environ.get("HOST", "0.0.0.0"))
    port: int = field(
        default_factory=lambda: int(os.environ.get("PORT", "8000"))
    )
    cors_origins: list[str] = field(
        default_factory=lambda: os.environ.get("CORS_ORIGINS", "*").split(",")
    )

    # Limits
    max_audio_duration_seconds: int = 30
    max_turns_per_session: int = 20
    max_audio_size_mb: int = 10

    # Directories
    upload_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get("UPLOAD_DIR", str(Path.cwd() / "uploads"))
        )
    )
    audio_output_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get("AUDIO_OUTPUT_DIR", str(Path.cwd() / "audio_output"))
        )
    )
    log_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get("LOG_DIR", str(Path.cwd() / "logs"))
        )
    )

    # Provider selection
    stt_provider: str = field(
        default_factory=lambda: os.environ.get("STT_PROVIDER", "openai")
    )
    llm_provider: str = field(
        default_factory=lambda: os.environ.get("LLM_PROVIDER", "openai")
    )
    tts_provider: str = field(
        default_factory=lambda: os.environ.get("TTS_PROVIDER", "openai")
    )

    # OpenAI model overrides
    stt_model: str = field(
        default_factory=lambda: os.environ.get("STT_MODEL", "gpt-4o-transcribe")
    )
    llm_model: str = field(
        default_factory=lambda: os.environ.get("LLM_MODEL", "gpt-4o-mini")
    )
    tts_model: str = field(
        default_factory=lambda: os.environ.get("TTS_MODEL", "tts-1")
    )
    tts_voice: str = field(
        default_factory=lambda: os.environ.get("TTS_VOICE", "alloy")
    )

    @property
    def mock_mode(self) -> bool:
        """Return True when OpenAI key is not set — use mock responses."""
        return not self.openai_api_key


settings = Settings()