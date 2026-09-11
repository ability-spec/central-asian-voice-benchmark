"""
DUB3 tests — sentence-level translation, parallel TTS parts, playback queue.

Covers:
  - llm.split_sentences determinism and edge cases (decimals, whitespace)
  - llm.translate_multi mock determinism + single-sentence DUB1 parity
  - /api/turn dub mode: multi-sentence -> ordered valid audio_parts,
    concatenated backward-compatible audio, dub_sentences count
  - single-sentence dub regression: audio_parts absent, byte-identical DUB1
  - tts.concat_wav_b64: valid join, frame-count math, fallback on garbage
  - frontend playbackPlan (node) + queue/barge wiring (structural)

Run: python -m pytest tests/test_dub3.py -v
"""

import base64
import io
import os
import re
import shutil
import subprocess
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = REPO_ROOT / "product" / "frontend" / "index.html"

os.environ.pop("OPENAI_API_KEY", None)

from product.backend.config import settings  # noqa: E402
from product.backend.main import app  # noqa: E402
from product.backend.routers import turn as turn_module  # noqa: E402
from product.backend.services import llm as llm_module  # noqa: E402
from product.backend.services import tts as tts_module  # noqa: E402
from product.backend.services.session import session_manager  # noqa: E402

requires_node = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not available"
)


@pytest.fixture()
def mock_env(tmp_path, monkeypatch):
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
    return b"\x00" * 44 + b"\x00" * int(duration_s * 32000)


def _post(client, language="uz", conv="d3", **extra):
    form = {"conversation_id": conv, "language": language, "mode": "dub",
            **extra}
    return client.post("/api/turn",
                       files={"audio": ("t.wav", _wav_bytes(), "audio/wav")},
                       data=form)


# ---------------------------------------------------------------------------
# split_sentences
# ---------------------------------------------------------------------------

def test_split_sentences_basic_and_deterministic():
    s = llm_module.split_sentences("Hello there. How are you? Fine!")
    assert s == ["Hello there.", "How are you?", "Fine!"]
    assert llm_module.split_sentences("Hello there. How are you? Fine!") == s


def test_split_sentences_edges():
    assert llm_module.split_sentences("") == []
    assert llm_module.split_sentences("   \n  ") == []
    assert llm_module.split_sentences("one sentence") == ["one sentence"]
    # decimals must not split (no whitespace after the dot)
    assert llm_module.split_sentences("It costs 3.5 dollars") == \
        ["It costs 3.5 dollars"]
    # messy whitespace collapses deterministically
    assert llm_module.split_sentences(" A .\t  B ? ") == ["A.", "B?"]


# ---------------------------------------------------------------------------
# translate_multi (mock path)
# ---------------------------------------------------------------------------

def test_translate_multi_mock_order_and_determinism():
    a = llm_module.translate_multi("Hello. Thank you.", "en", "uz")
    b = llm_module.translate_multi("Hello. Thank you.", "en", "uz")
    assert a == ["Salom.", "Rahmat."] and a == b
    assert llm_module.translate_multi("Hello. Thank you.", "en", "kk") == \
        ["Сәлем.", "Рахмет."]


def test_translate_multi_single_sentence_equals_dub1_translate():
    for tgt in ("uz", "kk"):
        one = llm_module.translate_multi("hello", "en", tgt)
        assert one == [llm_module.translate("hello", "en", tgt)]
    assert llm_module.translate_multi("", "en", "uz") == []


# ---------------------------------------------------------------------------
# concat_wav_b64
# ---------------------------------------------------------------------------

def _mk_wav_b64(fr: int, secs: float) -> str:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(fr)
        wf.writeframes(b"\x00" * int(secs * fr * 2))
    return base64.b64encode(buf.getvalue()).decode("ascii")


def test_concat_wav_frames_sum_and_valid():
    p1, p2, p3 = (_mk_wav_b64(16000, 0.5), _mk_wav_b64(16000, 0.25),
                  _mk_wav_b64(16000, 1.0))
    joined = tts_module.concat_wav_b64([p1, p2, p3])
    with wave.open(io.BytesIO(base64.b64decode(joined)), "rb") as wf:
        assert wf.getframerate() == 16000
        assert wf.getnframes() == int((0.5 + 0.25 + 1.0) * 16000)


def test_concat_wav_falls_back_on_inconsistent_or_garbage():
    mismatched = tts_module.concat_wav_b64(
        [_mk_wav_b64(22050, 0.5), _mk_wav_b64(16000, 0.5)])
    assert mismatched == _mk_wav_b64(22050, 0.5)  # first part, valid audio
    garbage = base64.b64encode(b"not-a-wav").decode()
    assert tts_module.concat_wav_b64([garbage, garbage]) == garbage
    assert tts_module.concat_wav_b64([]) == ""


# ---------------------------------------------------------------------------
# /api/turn — multi-sentence dub parts
# ---------------------------------------------------------------------------

def test_dub_multi_parts_ordered_valid_and_backward_compat(client, monkeypatch):
    monkeypatch.setattr(turn_module, "transcribe",
                        lambda *a, **k: "Hello. How are you? Goodbye.")
    r = client.post(
        "/api/turn",
        files={"audio": ("t.wav", _wav_bytes(), "audio/wav")},
        data={"conversation_id": "multi", "language": "uz", "mode": "dub"},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["transcript"] == "Hello. How are you? Goodbye."
    assert d["response_text"] == "Salom. Qalaysiz? Xayr."
    parts = d["audio_parts"]
    assert isinstance(parts, list) and len(parts) == 3
    # every part is a valid mono 16 kHz WAV
    frames_each = []
    for p in parts:
        with wave.open(io.BytesIO(base64.b64decode(p)), "rb") as wf:
            assert wf.getnchannels() == 1 and wf.getframerate() == 16000
            frames_each.append(wf.getnframes())
    # legacy `audio` = full concatenated dub (frames = sum of parts)
    with wave.open(io.BytesIO(base64.b64decode(d["audio"])), "rb") as wf:
        assert wf.getnframes() == sum(frames_each)
    assert d["provider_info"]["dub_sentences"] == 3
    assert d["provider_info"]["mode"] == "dub"


def test_dub_parts_order_matches_sentences(client, monkeypatch):
    """parts[i] is exactly the synth of translated sentence i, in order.

    Identity-patched synthesize_b64 makes each returned part equal its input
    sentence, so the assertion pins the full ordering: transcript sentence ->
    translation -> part index.
    """
    monkeypatch.setattr(turn_module, "transcribe",
                        lambda *a, **k: "hello. thank you. goodbye.")
    monkeypatch.setattr(turn_module, "synthesize_b64",
                        lambda text, lang: text)
    r = client.post(
        "/api/turn",
        files={"audio": ("t.wav", _wav_bytes(), "audio/wav")},
        data={"conversation_id": "order", "language": "uz", "mode": "dub"},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["response_text"] == "Salom. Rahmat. Xayr."
    assert d["audio_parts"] == ["Salom.", "Rahmat.", "Xayr."]
    # non-WAV identity parts -> concat must fall back to the first part
    assert d["audio"] == "Salom."
    assert d["provider_info"]["dub_sentences"] == 3


def test_dub_single_sentence_regression_dub1_identical(client):
    """Single-sentence EN dub: NO audio_parts, audio == DUB1 output exactly."""
    r = _post(client, language="uz", conv="reg")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["audio_parts"] is None
    assert d["transcript"] == "Hello, this is an English test voice."
    assert d["response_text"] == "Salom, bu inglizcha test ovozi."
    assert d["provider_info"]["dub_sentences"] == 1
    with wave.open(io.BytesIO(base64.b64decode(d["audio"])), "rb") as wf:
        assert wf.getnframes() > 0


def test_chat_mode_has_no_parts(client, monkeypatch):
    monkeypatch.setattr(turn_module, "transcribe",
                        lambda *a, **k: "hello. thank you.")
    r = client.post(
        "/api/turn",
        files={"audio": ("t.wav", _wav_bytes(), "audio/wav")},
        data={"conversation_id": "chatd3", "language": "uz"},
    )
    d = r.json()
    assert d["audio_parts"] is None
    assert d["provider_info"]["dub_sentences"] == 0
    assert d["provider_info"]["mode"] == "chat"


# ---------------------------------------------------------------------------
# Frontend: playbackPlan (pure, node) + queue wiring (structural)
# ---------------------------------------------------------------------------

DUB3_BLOCK_RE = re.compile(
    r"/\* == DUB3-CORE-START == \*/(.*?)/\* == DUB3-CORE-END == \*/", re.S
)


def _dub3_core():
    html = INDEX_HTML.read_text(encoding="utf-8")
    m = DUB3_BLOCK_RE.search(html)
    assert m, "DUB3-CORE block not found in index.html"
    return m.group(1)


@requires_node
def test_playback_plan_node():
    js = _dub3_core() + """
let p = playbackPlan({audio: 'FULL', audio_parts: ['A','B','C']});
if (JSON.stringify(p) !== '["A","B","C"]') throw new Error('parts not used');
if (JSON.stringify(playbackPlan({audio: 'FULL', audio_parts: ['A']})) !== '["FULL"]')
  throw new Error('single part must fall back to audio');
if (JSON.stringify(playbackPlan({audio: 'FULL'})) !== '["FULL"]')
  throw new Error('legacy shape broken');
if (JSON.stringify(playbackPlan({})) !== '[]') throw new Error('empty must be []');
const data = {audio: 'F', audio_parts: ['A','B']};
playbackPlan(data)[0] = 'MUT';
if (data.audio_parts[0] !== 'A') throw new Error('plan must be a copy');
console.log('OK');
"""
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True,
                         timeout=30)
    assert out.returncode == 0, out.stderr[:800]
    assert out.stdout.strip() == "OK"


def test_queue_wiring_structural():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "function playQueueNext()" in html
    assert "dubQueue = {parts: plan, idx: 0, btn: btn, active: true};" in html
    # barge-in cancels the queue (DUB2 moved tap/voice paths through
    # cancelStream(), which deactivates the queue and aborts the fetch)
    assert html.count("dubQueue.active = false;") >= 3
    assert "function cancelStream()" in html
    # single/legacy path preserved
    assert "playAudio(plan[0], btn);" in html
    # DUB1 contract still intact
    assert "formData.append('mode', 'dub');" in html
    assert "formData.append('source_language', 'en');" in html
