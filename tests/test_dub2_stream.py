"""
DUB2 tests — minimal NDJSON streaming transport for the DUB3 pipeline.

Proves the four required properties, deterministically and with no real
API calls:
  1. the first audio part is delivered before later parts complete;
  2. parts are delivered strictly in order, even when jobs finish out of
     order;
  3. cancellation drops pending (not-yet-started) sentence jobs — proven
     against the real DubJobRunner — and the generator wires
     cancel_pending() into its unwind paths;
  4. /api/turn legacy behaviour is unchanged; the stream's final audio is
     byte-identical to the legacy response for the same utterance.

Run: python -m pytest tests/test_dub2_stream.py -v
"""

import base64
import io
import json
import os
import threading
import time
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
from product.backend.services.session import session_manager  # noqa: E402


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


def _stream_events(client, conv="s", language="uz", transcript=None,
                   monkeypatch=None):
    """POST /api/turn/stream; return parsed NDJSON events with arrival times."""
    if transcript is not None:
        monkeypatch.setattr(turn_module, "transcribe",
                            lambda *a, **k: transcript)
    out = []
    with client.stream(
        "POST", "/api/turn/stream",
        files={"audio": ("t.wav", _wav_bytes(), "audio/wav")},
        data={"conversation_id": conv, "language": language, "mode": "dub"},
    ) as r:
        assert r.status_code == 200, r.read()
        t_start = time.perf_counter()
        for line in r.iter_lines():
            if not line.strip():
                continue
            ev = json.loads(line)
            ev["_t"] = time.perf_counter() - t_start
            out.append(ev)
    return out


# ---------------------------------------------------------------------------
# (1)+(2): shape, order, early first part
# ---------------------------------------------------------------------------

def test_stream_event_shape_and_order(client, monkeypatch):
    evs = _stream_events(client, conv="shape", monkeypatch=monkeypatch,
                         transcript="Hello. How are you? Goodbye.")
    assert [e["type"] for e in evs] == ["meta", "part", "part", "part", "done"]
    parts = [e for e in evs if e["type"] == "part"]
    assert [p["index"] for p in parts] == [0, 1, 2]
    assert [p["text"] for p in parts] == ["Salom.", "Qalaysiz?", "Xayr."]
    meta = evs[0]
    assert meta["transcript"] == "Hello. How are you? Goodbye."
    assert meta["mode"] == "dub" and meta["source_language"] == "en"
    done = evs[-1]
    assert done["response_text"] == "Salom. Qalaysiz? Xayr."
    assert done["provider_info"]["dub_sentences"] == 3
    assert done["scored"] is False and done["turn_number"] == 1
    for p in parts:  # every streamed part is a valid mono WAV
        with wave.open(io.BytesIO(base64.b64decode(p["audio"])), "rb") as wf:
            assert wf.getnchannels() == 1 and wf.getframerate() == 16000


def test_stream_first_part_early_while_later_still_working(client, monkeypatch):
    """Proof of (1): part 0 lands long before the deliberately slow tail."""
    calls = {"n": 0}

    def slow_translate(text, src, tgt):
        calls["n"] += 1
        if text in ("Echo.", "Foxtrot."):
            time.sleep(0.6)          # tail sentences deliberately slow
        return "T(" + text + ")"

    monkeypatch.setattr(turn_module, "translate", slow_translate)
    evs = _stream_events(client, conv="early", monkeypatch=monkeypatch,
                         transcript="Alpha. Bravo. Charlie. Delta. Echo. Foxtrot.")
    parts = [e for e in evs if e["type"] == "part"]
    assert len(parts) == 6
    # Server-side emission clock proves the generator put part 0 on the wire
    # while the tail jobs were still sleeping (TestClient buffers client-side
    # timing, so at_ms is the deterministic measure; a live uvicorn check in
    # the DUB2 report confirms wire-level delivery).
    assert parts[0]["at_ms"] < 350, f"first part emitted late: {parts[0]['at_ms']}ms"
    assert parts[-1]["at_ms"] >= 550, "tail jobs must still gate the last part"
    assert parts[0]["at_ms"] < parts[-1]["at_ms"] - 200
    # ordered and complete despite out-of-order job availability
    assert [p["text"] for p in parts] == [
        "T(Alpha.)", "T(Bravo.)", "T(Charlie.)", "T(Delta.)",
        "T(Echo.)", "T(Foxtrot.)",
    ]
    assert calls["n"] == 6


def test_parts_ordered_even_when_completed_out_of_order(client, monkeypatch):
    """Reverse delays: last sentence finishes first, delivery order stays 0..5."""
    def reverse_translate(text, src, tgt):
        time.sleep({"Alpha.": 0.5, "Bravo.": 0.4, "Charlie.": 0.3,
                    "Delta.": 0.2, "Echo.": 0.1, "Foxtrot.": 0.0}[text])
        return "T(" + text + ")"

    monkeypatch.setattr(turn_module, "translate", reverse_translate)
    evs = _stream_events(client, conv="order", monkeypatch=monkeypatch,
                         transcript="Alpha. Bravo. Charlie. Delta. Echo. Foxtrot.")
    parts = [e for e in evs if e["type"] == "part"]
    assert [p["index"] for p in parts] == [0, 1, 2, 3, 4, 5]


# ---------------------------------------------------------------------------
# (4): legacy /api/turn parity
# ---------------------------------------------------------------------------

def test_stream_done_audio_matches_legacy_turn_byte_identical(client):
    r = client.post(
        "/api/turn",
        files={"audio": ("t.wav", _wav_bytes(), "audio/wav")},
        data={"conversation_id": "par1", "language": "uz", "mode": "dub"},
    )
    legacy = r.json()
    evs = _stream_events(client, conv="par2")   # default mock EN transcript
    meta, done = evs[0], evs[-1]
    assert meta["transcript"] == legacy["transcript"]
    assert done["audio"] == legacy["audio"]
    assert done["response_text"] == legacy["response_text"]


def test_legacy_turn_single_sentence_stream_too(client):
    """Single sentence through the stream: one part, done.audio == legacy.audio."""
    r = client.post(
        "/api/turn",
        files={"audio": ("t.wav", _wav_bytes(), "audio/wav")},
        data={"conversation_id": "par3", "language": "kk", "mode": "dub"},
    )
    legacy = r.json()
    evs = _stream_events(client, conv="par4", language="kk")
    assert [e["type"] for e in evs] == ["meta", "part", "done"]
    done = evs[-1]
    assert done["audio"] == legacy["audio"]
    assert done["response_text"] == legacy["response_text"] == "Сәлем, бұл ағылшынша тест дауысы."


def test_stream_validation_before_streaming(client):
    r = client.post(
        "/api/turn/stream",
        files={"audio": ("t.wav", _wav_bytes(), "audio/wav")},
        data={"conversation_id": "v", "language": "ru", "mode": "dub"},
    )
    assert r.status_code == 400
    r = client.post(
        "/api/turn/stream",
        files={"audio": ("t.wav", b"", "audio/wav")},
        data={"conversation_id": "v", "language": "uz", "mode": "dub"},
    )
    assert r.status_code == 400


def test_stream_chat_mode_single_part(client):
    with client.stream(
        "POST", "/api/turn/stream",
        files={"audio": ("t.wav", _wav_bytes(), "audio/wav")},
        data={"conversation_id": "chat-s", "language": "uz", "mode": "chat"},
    ) as r:
        assert r.status_code == 200
        evs = [json.loads(l) for l in r.iter_lines() if l.strip()]
    assert [e["type"] for e in evs] == ["meta", "part", "done"]
    assert evs[1]["index"] == 0
    assert evs[2]["provider_info"]["mode"] == "chat"


# ---------------------------------------------------------------------------
# (3): cancellation drops pending work
# ---------------------------------------------------------------------------

def test_job_runner_cancels_pending_before_they_start():
    started = []
    lock = threading.Lock()

    def job(i):
        with lock:
            started.append(i)
        time.sleep(0.2)

    runner = turn_module.DubJobRunner(list(range(6)), job, max_workers=2)
    # Wait until BOTH workers are busy, so exactly jobs 2..5 are queued.
    deadline = time.time() + 2.0
    while time.time() < deadline:
        with lock:
            n = len(started)
        if n >= 2:
            break
        time.sleep(0.005)
    assert n == 2
    cancelled = runner.cancel_pending()
    assert cancelled == 4, f"expected 4 queued jobs cancellable, got {cancelled}"
    runner.shutdown()
    time.sleep(0.45)   # let the two in-flight jobs finish
    with lock:
        assert len(started) == 2, "cancelled jobs must never execute"


def test_stream_cancellation_wired_server_side():
    src = (REPO_ROOT / "product" / "backend" / "routers" / "turn.py").read_text(
        encoding="utf-8"
    )
    assert "except (asyncio.CancelledError, GeneratorExit):" in src
    # both the inner (per-part loop) and outer (client gone) unwind paths
    # cancel pending work
    assert src.count("runner.cancel_pending()") >= 2
    tail = src[src.index("def _job(sent)") : src.index('response_text = " ".join(texts)')]
    assert "runner.cancel_pending()" in tail


def test_frontend_stream_wiring():
    html = INDEX_HTML.read_text(encoding="utf-8")
    for needle in (
        "API_BASE + '/api/turn/stream'",
        "signal:ctrl.signal",
        "err.name === 'AbortError'",
        "function cancelStream()",
        "function pumpQueue()",
        "dubQueue = {parts: parts, idx: 0, btn: null, active: true, streaming: true, closed: false}",
        "if (dubQueue.streaming && !dubQueue.closed) return;",
        "cancelStream();  // DUB2: abort in-flight stream + drop queued parts",
        "cancelStream();  // DUB2: a session end also aborts an in-flight stream",
        "cancelStream();  // DUB3+DUB2: cancel the whole queue AND the pending stream",
    ):
        assert needle in html, f"missing: {needle!r}"
    # the app now streams by default (legacy endpoint stays server-side only)
    assert "API_BASE + '/api/turn'" not in html
