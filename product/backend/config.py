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

    # CP5: local voice clone via the VENDORED Route B wrapper under
    # services/routeb/b_sayro_then_seedvc.py. The wrapper loads Sayro in its
    # own Python process and shells out to Seed-VC (cwd=SEEDVC_DIR). All
    # heavy model code (Sayro, Seed-VC) lives OUTSIDE this repo; only the
    # orchestration wrapper is vendored so the demo does not depend on an
    # unmanaged external voice-lab directory.
    #
    # Resolution order (each field can be absolute or relative; the
    # _resolve_* helpers in services/voice_clone.py implement this):
    #   1. Explicit env var (absolute path used verbatim).
    #   2. Conventional in-repo default when it exists on disk:
    #        SAYRO_SCRIPT    -> product/backend/services/routeb/b_sayro_then_seedvc.py
    #        SEEDVC_DIR      -> product/backend/third_party/seed-vc
    #        SEEDVC_PYTHON   -> SEEDVC_DIR/.venv-vc/Scripts/python.exe (Windows)
    #                           or SEEDVC_DIR/.venv-vc/bin/python (POSIX)
    #        SAYRO_PYTHON    -> product/backend/.venv-routeb/...
    #   3. Otherwise empty -> feature gracefully disabled (OpenAI fallback).
    #
    # Reference WAV (SEEDVC_REFERENCE_WAV) has NO default — it must point at
    # the user's enrolled voice and lives outside the repo.
    sayro_voice_lab_dir: str = field(
        default_factory=lambda: os.environ.get("SAYRO_VOICE_LAB_DIR", "")
    )
    sayro_script: str = field(
        default_factory=lambda: os.environ.get("SAYRO_SCRIPT", "")
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
    # Seed-VC version + quality knobs. Defaults match the 74.86s / 5-sentence
    # production benchmark (v2 persistent worker + target-cache, 15 steps,
    # intelligibility/similarity 0.8). Override via env only when benchmarking.
    seedvc_version: str = field(
        default_factory=lambda: os.environ.get("SEEDVC_VERSION", "v2")
    )
    route_b_diffusion_steps: int = field(
        default_factory=lambda: int(os.environ.get("ROUTE_B_DIFFUSION_STEPS", "15"))
    )
    route_b_intelligibility: float = field(
        default_factory=lambda: float(os.environ.get("ROUTE_B_INTELLIGIBILITY", "0.8"))
    )
    route_b_similarity: float = field(
        default_factory=lambda: float(os.environ.get("ROUTE_B_SIMILARITY", "0.8"))
    )
    # Optional extra argv tokens appended verbatim (shlex-split), so any
    # wrapper flag we don't yet know about is reachable without code changes.
    route_b_extra_args: str = field(
        default_factory=lambda: os.environ.get("ROUTE_B_EXTRA_ARGS", "")
    )
    local_clone_timeout_s: int = field(
        default_factory=lambda: int(os.environ.get("LOCAL_CLONE_TIMEOUT_S", "300"))
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