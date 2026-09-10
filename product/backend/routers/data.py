"""
Read-only benchmark data endpoints.

Serves already-committed research CSVs verbatim (type coercion only).
Zero recomputation: no scoring, no aggregation, no model calls.
"""

import csv
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["data"])

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
PROMPTS_CSV = REPO_ROOT / "research" / "phase3a_audio_manifest.csv"
LEADERBOARD_CSV = REPO_ROOT / "research" / "final_benchmark_results.csv"


def _coerce(value: str):
    """Coerce a CSV cell to int/float/None, else keep the string."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _read_csv(path: Path) -> list[dict]:
    """Read a tracked CSV; sanitised 500 if it is missing/unreadable."""
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))
    except (FileNotFoundError, OSError) as exc:
        logger.error("Benchmark data unreadable %s: %s", path, exc)
        raise HTTPException(status_code=500, detail="Benchmark data unavailable.")


@router.get("/prompts")
def get_prompts(language: str = Query(...)):
    """Reference sentences for prompted benchmark mode (manifest order)."""
    if language not in ("uz", "kk"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid language '{language}'. Must be 'uz' or 'kk'.",
        )
    rows = _read_csv(PROMPTS_CSV)
    prompts = [
        {
            "id": row["utterance_id"],
            "sentence": row["reference_transcript"],
            "duration_s": float(row["duration_seconds"]),
        }
        for row in rows
        if row.get("language") == language
    ]
    return {"language": language, "prompts": prompts}


@router.get("/leaderboard")
def get_leaderboard():
    """Frozen aggregate benchmark results, served verbatim."""
    rows = _read_csv(LEADERBOARD_CSV)
    return {"rows": [{key: _coerce(val) for key, val in row.items()} for row in rows]}
