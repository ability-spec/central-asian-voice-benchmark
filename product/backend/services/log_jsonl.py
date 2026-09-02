"""
Structured JSONL turn logging for latency and cost visibility.

Appends one record per successful pipeline turn to logs/turns.jsonl.
Write failures are logged as warnings but never surface to the caller.
"""

import json
import logging
import time

from product.backend.config import settings

logger = logging.getLogger(__name__)


def log_turn(
    *,
    request_id: str,
    conversation_id: str,
    language: str,
    turn_number: int,
    stt_ms: int,
    llm_ms: int,
    tts_ms: int,
    transcript_len: int,
    response_len: int,
    audio_bytes: int,
    mock_mode: bool,
) -> None:
    """Append one JSONL record to logs/turns.jsonl."""
    try:
        settings.log_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": round(time.time(), 3),
            "request_id": request_id,
            "conversation_id": conversation_id,
            "language": language,
            "turn_number": turn_number,
            "stt_ms": stt_ms,
            "llm_ms": llm_ms,
            "tts_ms": tts_ms,
            "total_ms": stt_ms + llm_ms + tts_ms,
            "transcript_len": transcript_len,
            "response_len": response_len,
            "audio_bytes": audio_bytes,
            "mock": mock_mode,
        }
        log_path = settings.log_dir / "turns.jsonl"
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("JSONL log write failed: %s", exc)
