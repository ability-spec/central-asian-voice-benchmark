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
    elevenlabs_voice_id: str = field(
        default_factory=lambda: os.environ.get("ELEVENLABS_VOICE_ID", "")
    )
    elevenlabs_tts_model: str = field(
        default_factory=lambda: os.environ.get(
            "ELEVENLABS_TTS_MODEL", "eleven_multilingual_v2"
        )
    )
    # VC1: enrolled voice config is stored OUTSIDE the repository by design
    # (never commit voice ids/secrets). Default: ~/.birovoz_voice.json
    voice_config_path: Path = field(
        default_factory=lambda: Path(
            os.environ.get(
                "BIROVOZ_VOICE_CONFIG",
                str(Path.home() / ".birovoz_voice.json"),
            )
        )
    )

    # CP5: local voice clone invokes the EXISTING Route B wrapper in voice-lab
    # (b_sayro_then_seedvc.py). No Sayro CLI is invented; no voice-lab or
    # seed-vc code is copied into the product. All paths live OUTSIDE the
    # repository; nothing is copied into the product tree. Every value is
    # env-driven and defaults to empty -> feature gracefully unavailable,
    # Standard/OpenAI voice remains the fallback.
    #
    # Wrapper CLI (as implemented by b_sayro_then_seedvc.py):
    #   <SAYRO_PYTHON> <SAYRO_SCRIPT> --stage all --sentences <dir> --only 1
    #     --out <dir> --target <ref.wav> --seedvc-python <py>
    #     --seedvc-dir <dir> --seedvc-version v1
    # The wrapper handles Sayro load / Uzbek normalization / model teardown
    # / Seed-VC subprocess internally with the known-good V1 flags
    # (diffusion-steps=25, cfg-rate=0.8, f0 off, fp16, cwd=SEEDVC_DIR).
    sayro_voice_lab_dir: str = field(
        default_factory=lambda: os.environ.get("SAYRO_VOICE_LAB_DIR", "")
    )
    sayro_script: str = field(
        default_factory=lambda: os.environ.get(
            "SAYRO_SCRIPT", "b_sayro_then_seedvc.py"
        )
    )
    sayro_python: str = field(
        default_factory=lambda: os.environ.get("SAYRO_PYTHON", "")
    )
    # Seed-VC environment for the wrapper to shell into.
    seedvc_python: str = field(
        default_factory=lambda: os.environ.get("SEEDVC_PYTHON", "")
    )
    seedvc_dir: str = field(
        default_factory=lambda: os.environ.get("SEEDVC_DIR", "")
    )
    seedvc_reference_wav: str = field(
        default_factory=lambda: os.environ.get("SEEDVC_REFERENCE_WAV", "")
    )
    # Optional extra argv tokens appended verbatim (shlex-split), so any
    # wrapper flag we don't yet know about is reachable without code changes.
    route_b_extra_args: str = field(
        default_factory=lambda: os.environ.get("ROUTE_B_EXTRA_ARGS", "")
    )
    local_clone_timeout_s: int = field(
        default_factory=lambda: int(os.environ.get("LOCAL_CLONE_TIMEOUT_S", "180"))
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