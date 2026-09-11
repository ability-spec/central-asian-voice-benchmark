"""
DUB1 tests — English → Uzbek/Kazakh AI dubbing on POST /api/turn.

Covers:
  - dub mode mock pipeline EN→uz and EN→kk (transcript, translation, audio)
  - benchmark/chat behaviour preserved when mode/source_language omitted
  - source_language='en' accepted in chat mode
  - request validation: bad mode / bad language / bad source_language /
    empty audio / overlong audio
  - session turn counting under dub mode
  - llm.translate() mock internals: phrase map, word fallback,
    punctuation-insensitivity, determinism

Run from the repo root:  python -m pytest tests/test_dub_api.py -v

No API key, no model inference, no network. ffmpeg is NOT required:
_to_wav is stubbed because mock STT ignores audio content anyway.
"""

import base64
import io
import os
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent

# Force mock mode before the app module is imported.
os.environ.pop("OPENAI_API_KEY", None)

from product.backend.config import settings  # noqa: E402
from product.backend.main import app  # noqa: E402
from product.backend.routers import turn as turn_module  # noqa: E402
from product.backend.services import llm as llm_module  # noqa: E402
from product.backend.services.session import session_manager  # noqa: E402
from product.backend.services.stt import MOCK_TRANSCRIPTS  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures / helpers
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
    """Minimal fake WAV: 44-byte header + 16 kHz mono s16 payload."""
    return b"\x00" * 44 + b"\x00" * int(duration_s * 32000)


def _post_turn(client, language="uz", conv="dub-conv", **form):
    form.setdefault("mode", "dub")
    return client.post(
        "/api/turn",
        files={"audio": ("test.wav", _wav_bytes(), "audio/wav")},
        data={"conversation_id": conv, "language": language, **form},
    )


# Expected deterministic mock dubbing output for the canned EN transcript.
EXPECTED_DUB_UZ = "Salom, bu inglizcha test ovozi."
EXPECTED_DUB_KK = "Сәлем, бұл ағылшынша тест дауысы."


# ---------------------------------------------------------------------------
# Dub mode — mock pipeline
# ---------------------------------------------------------------------------

def test_dub_en_to_uz_mock_pipeline(client):
    r = _post_turn(client, language="uz", source_language="en")
    assert r.status_code == 200, r.text
    d = r.json()
    # STT ran in English: user message is the English transcript...
    assert d["transcript"] == MOCK_TRANSCRIPTS["en"]
    # ...and the "AI" text is the Uzbek dub.
    assert d["response_text"] == EXPECTED_DUB_UZ
    assert d["language"] == "uz"
    assert d["provider_info"]["mode"] == "dub"
    assert d["provider_info"]["source_language"] == "en"
    assert d["turn_number"] == 1
    assert d["scored"] is False and d["wer"] is None


def test_dub_en_to_kk_mock_pipeline(client):
    r = _post_turn(client, language="kk", source_language="en", conv="dub-kk")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["transcript"] == MOCK_TRANSCRIPTS["en"]
    assert d["response_text"] == EXPECTED_DUB_KK
    assert d["provider_info"]["mode"] == "dub"


def test_dub_audio_is_playable_wav(client):
    r = _post_turn(client, language="uz")
    d = r.json()
    raw = base64.b64decode(d["audio"])
    assert raw[:4] == b"RIFF"
    with wave.open(io.BytesIO(raw), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getframerate() == 16000
        assert wf.getnframes() > 0


def test_dub_source_language_may_be_omitted_defaults_to_english(client):
    r1 = _post_turn(client, language="uz")            # no source_language
    r2 = _post_turn(client, language="uz", source_language="en")
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["response_text"] == r2.json()["response_text"]
    assert r1.json()["provider_info"]["source_language"] == "en"


def test_dub_mode_omitted_for_source_keeps_benchmark_behaviour(client):
    """No mode, no source_language → byte-identical old benchmark flow."""
    r = client.post(
        "/api/turn",
        files={"audio": ("test.wav", _wav_bytes(), "audio/wav")},
        data={"conversation_id": "legacy", "language": "uz"},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    # Legacy: STT ran in the TARGET language (uz), canned uz transcript.
    assert d["transcript"] == MOCK_TRANSCRIPTS["uz"]
    # Legacy chat mock reply (NOT the dub phrase).
    assert d["response_text"] == llm_module.MOCK_RESPONSES["uz"]
    assert d["provider_info"]["mode"] == "chat"
    assert d["provider_info"]["source_language"] == "uz"


def test_chat_mode_with_source_english_transcribes_in_english(client):
    r = client.post(
        "/api/turn",
        files={"audio": ("test.wav", _wav_bytes(), "audio/wav")},
        data={
            "conversation_id": "chat-en",
            "language": "uz",
            "source_language": "en",
        },
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["transcript"] == MOCK_TRANSCRIPTS["en"]
    # Chat semantics preserved: conversational uz reply, session recorded.
    assert d["response_text"] == llm_module.MOCK_RESPONSES["uz"]
    assert d["provider_info"]["mode"] == "chat"


def test_dub_turn_counting_and_history(client):
    for expect_turn in (1, 2):
        r = _post_turn(client, language="uz", conv="dub-count")
        assert r.status_code == 200
        assert r.json()["turn_number"] == expect_turn
    hist = session_manager.get_history("dub-count")
    assert len(hist) == 4  # user/assistant per dub turn
    assert [m["role"] for m in hist] == ["user", "assistant"] * 2
    assert hist[1]["content"] == EXPECTED_DUB_UZ


def test_dub_is_deterministic(client):
    a = _post_turn(client, language="kk", conv="det-a").json()
    b = _post_turn(client, language="kk", conv="det-b").json()
    assert a["response_text"] == b["response_text"]
    assert a["transcript"] == b["transcript"]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_dub_rejects_non_english_source(client):
    r = _post_turn(client, language="uz", source_language="kk")
    assert r.status_code == 400
    assert "English" in r.json()["detail"]


def test_invalid_mode_rejected(client):
    r = _post_turn(client, language="uz", mode="translate")
    assert r.status_code == 400
    assert "mode" in r.json()["detail"]


def test_dub_rejects_bad_language(client):
    r = _post_turn(client, language="ru")
    assert r.status_code == 400


def test_chat_rejects_bad_source_language(client):
    r = client.post(
        "/api/turn",
        files={"audio": ("test.wav", _wav_bytes(), "audio/wav")},
        data={"conversation_id": "x", "language": "uz", "source_language": "de"},
    )
    assert r.status_code == 400
    assert "source_language" in r.json()["detail"]


def test_dub_empty_audio_rejected(client):
    r = client.post(
        "/api/turn",
        files={"audio": ("test.wav", b"", "audio/wav")},
        data={"conversation_id": "x", "language": "uz", "mode": "dub"},
    )
    assert r.status_code == 400


def test_dub_overlong_audio_rejected(client):
    big = _wav_bytes(duration_s=31.0)
    r = client.post(
        "/api/turn",
        files={"audio": ("test.wav", big, "audio/wav")},
        data={"conversation_id": "x", "language": "uz", "mode": "dub"},
    )
    assert r.status_code == 413


# ---------------------------------------------------------------------------
# llm.translate() mock internals
# ---------------------------------------------------------------------------

def test_mock_translate_phrase_map():
    assert llm_module.translate("hello", "en", "uz") == "Salom."
    assert llm_module.translate("Hello!", "en", "kk") == "Сәлем."
    assert (
        llm_module.translate(
            "  Hello, this is an English test voice. ", "en", "uz"
        )
        == EXPECTED_DUB_UZ
    )


def test_mock_translate_punctuation_insensitive():
    a = llm_module.translate("How are you?", "en", "uz")
    b = llm_module.translate("how are you.", "en", "uz")
    assert a == b == "Qalaysiz?"


def test_mock_translate_word_fallback_deterministic():
    out1 = llm_module.translate("hello friend", "en", "uz")
    out2 = llm_module.translate("HELLO FRIEND", "en", "uz")
    assert out1 == out2 == "Salom do'st."
    assert llm_module.translate("good coffee", "en", "kk") == "Жақсы кофе."


def test_mock_translate_unknown_words_pass_through():
    out = llm_module.translate("the zebra dances", "en", "uz")
    assert "zebra" in out and "dances" in out
    assert out[0].isupper() and out.endswith(".")
