"""
Product API tests for the reference-scored POST /api/turn checkpoint.

Covers:
  - score.py unit behaviour (identical, substitution, empty reference)
  - normalisation fidelity vs the frozen Phase 3A implementation
  - parity with jiwer when jiwer is installed (else skipped)
  - /api/turn in mock mode: 200 + new fields, scored/unscored, 400, 413

Run from the repo root:  python -m pytest tests/test_product_api.py -v

No API key, no model inference, no network. ffmpeg is NOT required:
_to_wav is stubbed because mock STT ignores audio content anyway.
"""

import importlib.util
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent

# Force mock mode before the app module is imported.
os.environ.pop("OPENAI_API_KEY", None)

from product.backend.config import settings  # noqa: E402
from product.backend.main import app  # noqa: E402
from product.backend.routers import turn as turn_module  # noqa: E402
from product.backend.services import score as score_module  # noqa: E402
from product.backend.services.session import session_manager  # noqa: E402
from product.backend.services.stt import MOCK_TRANSCRIPTS  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_env(tmp_path, monkeypatch):
    """Isolated mock-mode environment: tmp dirs, fresh sessions, no ffmpeg."""
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")
    monkeypatch.setattr(settings, "log_dir", tmp_path / "logs")
    session_manager._sessions.clear()
    session_manager._created.clear()

    async def _fake_to_wav(src: Path, dst: Path) -> None:
        dst.write_bytes(src.read_bytes())

    monkeypatch.setattr(turn_module, "_to_wav", _fake_to_wav)
    assert settings.mock_mode
    return tmp_path


@pytest.fixture()
def client(mock_env):
    return TestClient(app)


def _wav_bytes(duration_s: float = 0.1) -> bytes:
    """Minimal fake WAV: 44-byte header + 16 kHz mono s16 payload.

    The router's WAV duration path is pure byte arithmetic
    ((len - 44) / 32000), so no real audio is needed.
    """
    return b"\x00" * 44 + b"\x00" * int(duration_s * 32000)


def _post_turn(client, audio_bytes, language="uz", conv="test-conv", **form):
    return client.post(
        "/api/turn",
        files={"audio": ("test.wav", audio_bytes, "audio/wav")},
        data={"conversation_id": conv, "language": language, **form},
    )


# ---------------------------------------------------------------------------
# score.py unit tests
# ---------------------------------------------------------------------------

def test_identical_reference_scores_zero():
    out = score_module.score("Salom dunyo", "Salom dunyo")
    assert out == {"wer": 0.0, "cer": 0.0, "scored": True}


def test_identical_after_normalisation_scores_zero():
    # Case, punctuation and whitespace differences vanish in normalisation.
    out = score_module.score("Salom,  DUNYO!", "salom dunyo")
    assert out == {"wer": 0.0, "cer": 0.0, "scored": True}


def test_known_substitution_wer():
    # One of three words substituted -> WER = 1/3.
    out = score_module.score("a b c", "a b d")
    assert out["scored"] is True
    assert out["wer"] == pytest.approx(1 / 3, abs=1e-6)
    # "a b c" vs "a b d": one char substitution in 5 chars -> CER = 0.2.
    assert out["cer"] == pytest.approx(0.2, abs=1e-6)


def test_known_substitution_single_word():
    out = score_module.score("abc", "abd")
    assert out["wer"] == 1.0
    assert out["cer"] == pytest.approx(1 / 3, abs=1e-6)


def test_empty_reference_is_unscored():
    for ref in ("", "   ", None):
        out = score_module.score(ref, "salom dunyo")
        assert out == {"wer": None, "cer": None, "scored": False}


def test_empty_hypothesis_scores_one():
    out = score_module.score("salom dunyo", "")
    assert out == {"wer": 1.0, "cer": 1.0, "scored": True}


def test_insertions_can_exceed_one():
    out = score_module.score("a", "a b c d")
    assert out["wer"] == 3.0


# ---------------------------------------------------------------------------
# Normalisation fidelity vs the frozen Phase 3A implementation
# ---------------------------------------------------------------------------

def _load_frozen_normalise():
    path = REPO_ROOT / "results" / "phase3a" / "run_phase3a_trackb.py"
    spec = importlib.util.spec_from_file_location("frozen_phase3a", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.normalise


FIDELITY_CASES = [
    "Salom, buzbekcha test ovoz.",
    "tayyor va arzon uy",
    "Сәлем, бұл қазақша тест дауыс.",
    "O'zbekiston 2024-yilda!",
    "o\u02bcta",          # U+02BC modifier letter apostrophe -> unified
    "so`z",               # backtick -> unified
    "o‘ta",               # U+2018 left quote -> deleted (frozen quirk)
    "o’ta",               # U+2019 right quote -> deleted (frozen quirk)
    "a  b\tc\nd",
    "MiXeD CaSe Шрифт",
    "keep_digits_123 and under_scores",
    "",
    "   ",
    None,
]


def test_normalise_matches_frozen_phase3a():
    frozen = _load_frozen_normalise()
    for text in FIDELITY_CASES:
        assert score_module.normalise(text) == frozen(text), repr(text)


def test_frozen_apostrophe_class_is_exact():
    # Locks the byte-faithful port: only U+0027, U+02BC, U+0060 unify.
    assert score_module.normalise("o\u02bcta") == "o'ta"
    assert score_module.normalise("so`z") == "so'z"
    assert score_module.normalise("o‘ta") == "o ta"   # U+2018 splits
    assert score_module.normalise("o’ta") == "o ta"   # U+2019 splits


# ---------------------------------------------------------------------------
# Parity with jiwer (when installed; skipped otherwise)
# ---------------------------------------------------------------------------

jiwer = pytest.importorskip("jiwer", reason="jiwer not installed (optional)")


@pytest.mark.parametrize("ref,hyp", [
    ("salom dunyo", "salom dunyo"),
    ("a b c", "a b d"),
    ("tayyor va arzon uy", "tayyor va arzon"),
    ("salom buzbekcha test ovoz", "salom buzbekcha test"),
    ("Сәлем бұл қазақша", "Сәлем қазақша"),
    ("a", "a b c d"),
    ("hello world", ""),
])
def test_parity_with_jiwer(ref, hyp):
    r = score_module.normalise(ref)
    h = score_module.normalise(hyp)
    assert score_module.wer(ref, hyp) == round(jiwer.wer(r, h), 6)
    assert score_module.cer(ref, hyp) == round(jiwer.cer(r, h), 6)


# ---------------------------------------------------------------------------
# /api/turn integration tests (mock mode, no ffmpeg)
# ---------------------------------------------------------------------------

def test_normal_mock_turn_has_new_fields(client):
    resp = _post_turn(client, _wav_bytes())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["transcript"] == MOCK_TRANSCRIPTS["uz"]
    assert body["response_text"]  # conversation behaviour intact
    assert body["turn_number"] == 1
    # Unscored without a reference...
    assert body["scored"] is False
    assert body["wer"] is None
    assert body["cer"] is None
    # ...but latency is always reported.
    for key in ("stt_ms", "llm_ms", "tts_ms", "total_ms"):
        assert isinstance(body[key], int), key
        assert body[key] >= 0, key
    assert body["total_ms"] == body["stt_ms"] + body["llm_ms"] + body["tts_ms"]


def test_mock_turn_with_matching_reference_scores_zero(client):
    resp = _post_turn(
        client, _wav_bytes(), reference_text=MOCK_TRANSCRIPTS["uz"]
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["scored"] is True
    assert body["wer"] == 0.0
    assert body["cer"] == 0.0


def test_mock_turn_with_substituted_reference(client):
    # Mock uz transcript normalises to 4 words: "salom buzbekcha test ovoz".
    ref = "XALOM, buzbekcha test ovoz."
    resp = _post_turn(client, _wav_bytes(), reference_text=ref)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["scored"] is True
    assert body["wer"] == pytest.approx(0.25, abs=1e-6)
    assert 0.0 < body["cer"] < 1.0


def test_mock_turn_with_empty_reference_is_unscored(client):
    resp = _post_turn(client, _wav_bytes(), reference_text="   ")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["scored"] is False
    assert body["wer"] is None
    assert body["cer"] is None


def test_invalid_language_returns_400(client):
    resp = _post_turn(client, _wav_bytes(), language="ru")
    assert resp.status_code == 400
    assert "Invalid language" in resp.json()["detail"]


def test_overlong_audio_returns_413(client):
    resp = _post_turn(client, _wav_bytes(duration_s=31))
    assert resp.status_code == 413
    assert "too long" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# /api/prompts + /api/leaderboard (CP2: read-only CSV passthrough)
# ---------------------------------------------------------------------------

def test_prompts_uz_returns_100_with_shape(client):
    resp = client.get("/api/prompts", params={"language": "uz"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["language"] == "uz"
    prompts = body["prompts"]
    assert len(prompts) == 100
    assert all(set(p) == {"id", "sentence", "duration_s"} for p in prompts)
    assert all(isinstance(p["sentence"], str) and p["sentence"].strip() for p in prompts)
    assert all(isinstance(p["duration_s"], float) and p["duration_s"] > 0 for p in prompts)
    assert len({p["id"] for p in prompts}) == 100  # unique ids


def test_prompts_kk_returns_100(client):
    resp = client.get("/api/prompts", params={"language": "kk"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["language"] == "kk"
    assert len(body["prompts"]) == 100


def test_prompts_match_committed_manifest(client):
    # Spot-check against research/phase3a_audio_manifest.csv (verbatim read).
    resp = client.get("/api/prompts", params={"language": "uz"})
    first = resp.json()["prompts"][0]
    assert first["id"] == "1187023182_2_34562_1"
    assert first["sentence"] == "tayyor va arzon uy"
    assert first["duration_s"] == pytest.approx(2.494)


def test_prompts_invalid_language_returns_400(client):
    resp = client.get("/api/prompts", params={"language": "ru"})
    assert resp.status_code == 400
    assert "Invalid language" in resp.json()["detail"]


def test_prompts_missing_language_returns_422(client):
    resp = client.get("/api/prompts")
    assert resp.status_code == 422


def test_leaderboard_returns_12_rows_with_shape(client):
    resp = client.get("/api/leaderboard")
    assert resp.status_code == 200, resp.text
    rows = resp.json()["rows"]
    assert len(rows) == 12
    for row in rows:
        assert isinstance(row["model"], str) and row["model"]
        assert row["language"] in ("uz", "kk")
        assert isinstance(row["wer"], float)
        assert isinstance(row["cer"], float)
        assert isinstance(row["p50_ms"], int)
        assert isinstance(row["p95_ms"], int)
        assert isinstance(row["n"], int) and row["n"] > 0


def test_leaderboard_match_committed_csv(client):
    # Spot-check against research/final_benchmark_results.csv (verbatim read).
    resp = client.get("/api/leaderboard")
    first = resp.json()["rows"][0]
    assert first["model"] == "gpt-4o-mini-transcribe"
    assert first["language"] == "kk"
    assert first["condition"] == "auto"
    assert first["n"] == 300
    assert first["wer"] == pytest.approx(0.4519)
    assert first["cer"] == pytest.approx(0.1698)
    assert first["p50_ms"] == 644
    assert first["prov_lid"] is None  # empty CSV cell -> null
