"""
Central Asian Voice AI — Backend Server (FastAPI).

Entry point: uvicorn product.backend.main:app
"""

import logging
import sys
from pathlib import Path

# --- Load .env BEFORE any settings-dependent imports ---
from dotenv import load_dotenv
dotenv_path = Path(__file__).resolve().parent / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)
    loaded_msg = f"Loaded .env from {dotenv_path}"
else:
    loaded_msg = f"No .env at {dotenv_path} — using environment variables"

# --- Settings and app imports (now see loaded env vars) ---
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from product.backend.config import settings
from product.backend.routers import health, turn, data

# --- Logging ---
# Reconfigure stdout to UTF-8 so Cyrillic/Unicode in log messages doesn't
# crash on Windows (default cp1252 can't encode e.g. Қ, Ə, Ү).
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)
logger.info(loaded_msg)


# --- App ---
app = FastAPI(
    title="Central Asian Voice AI",
    description="Voice AI pipeline for Uzbek and Kazakh languages: "
                "STT → LLM → TTS. DUB1 adds English→uz/kk dubbing mode.",
    version="0.1.0",
)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routers ---
app.include_router(health.router)
app.include_router(turn.router)
app.include_router(data.router)

# --- Static frontend ---
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
    logger.info("Frontend mounted from %s", frontend_dir)
else:
    logger.warning("Frontend directory not found at %s — serving API only", frontend_dir)


# --- Startup ---
@app.on_event("startup")
async def startup():
    # Ensure directories exist
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.audio_output_dir.mkdir(parents=True, exist_ok=True)

    if settings.mock_mode:
        logger.info(
            "RUNNING IN MOCK MODE — no OPENAI_API_KEY set. "
            "All pipeline stages return canned responses."
        )
    else:
        logger.info(
            "Running with live API keys: "
            "STT=%s/%s LLM=%s/%s TTS=%s/%s",
            settings.stt_provider, settings.stt_model,
            settings.llm_provider, settings.llm_model,
            settings.tts_provider, settings.tts_model,
        )


# --- Main ---
def main():
    logger.info("Starting server on %s:%s", settings.host, settings.port)
    uvicorn.run(
        "product.backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()