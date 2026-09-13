"""
VC1 voice-provider tests — optional ElevenLabs TTS provider.

Covers (no network, no real keys):
  - provider state: default resolution, switching, unconfigured rejection
  - pcm→WAV wrapping (frontend plays audio/wav blobs)
  - tts.synthesize dispatch: ElevenLabs path, runtime-failure fallback to the
    pre-VC1 OpenAI/mock path, truthful `report` dicts
  - provider_info.tts on a full /api/turn (mock mode): unchanged for OpenAI,
    'elevenlabs/<model>' when the clone is active
  - enrollment: consent gate, 1-5 sample limit, temp-sample deletion,
    out-of-repo voice_id storage, missing API key
  - /api/voice/status + /provider + /enroll endpoints
  - frontend: refreshVoiceStatus/setVoiceProvider present + node --check

Run: python -m pytest tests/test_voice_clone.py -v
"""

import io
import re
import shutil
import struct
import subprocess
import tempfile
import wave
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = REPO_ROOT / "product" / "frontend" / "index.html"

# Force mock mode before the app module is imported (same pattern as
# tests/test_product_api.py).
import os

os.environ.pop("OPENAI_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from product.backend.config import settings  # noqa: E402
from product.backend.main import app  # noqa: E402
from product.backend.routers import turn as turn_module  # noqa: E402
from product.backend.services import voice_clone  # noqa: E402
from product.backend.services import tts as tts_module  # noqa: E402
from product.backend.services.session import session_manager  # noqa: E402

client = TestClient(app)

requires_node = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not available"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class FakeSample:
    """Just enough of UploadFile for voice_clone.enroll (uses .file.read())."""

    def __init__(self, data: bytes):
        self.file = io.BytesIO(data)


@pytest.fixture()
def voice_env(tmp_path, monkeypatch):
    """Isolated voice state: fresh provider, no keys, out-of-repo config in tmp."""
    monkeypatch.setattr(settings, "elevenlabs_api_key", "")
    monkeypatch.setattr(settings, "elevenlabs_voice_id", "")
    monkeypatch.setattr(settings, "elevenlabs_tts_model", "eleven_multilingual_v2")
    monkeypatch.setattr(settings, "voice_config_path", tmp_path / "voice.json")
    monkeypatch.setattr(voice_clone, "_active_provider", None)
    return tmp_path


@pytest.fixture()
def el_configured(voice_env, monkeypatch):
    """ElevenLabs fully configured (fake key + env voice id)."""
    monkeypatch.setattr(settings, "elevenlabs_api_key", "test-key")
    monkeypatch.setattr(settings, "elevenlabs_voice_id", "env-voice-id")
    return voice_env


@pytest.fixture()
def mock_turn_env(tmp_path, monkeypatch):
    """Mock-mode /api/turn environment (pattern from test_product_api.py)."""
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


def _fake_wav_bytes(seconds: float = 0.05, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x01" * int(rate * seconds))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Provider state
# ---------------------------------------------------------------------------

def test_default_provider_resolves_to_openai(voice_env):
    assert voice_clone.active_provider() == "openai"
    assert voice_clone.resolved_provider() == "openai"
    assert voice_clone.tts_label() == "openai/tts-1"


def test_env_elevenlabs_unconfigured_resolves_to_openai(voice_env, monkeypatch):
    monkeypatch.setattr(settings, "tts_provider", "elevenlabs")
    monkeypatch.setattr(voice_clone, "_active_provider", None)
    # selected but not configured -> silently resolves to the OpenAI default
    assert voice_clone.resolved_provider() == "openai"


def test_set_provider_rejects_unknown(voice_env):
    with pytest.raises(ValueError):
        voice_clone.set_provider("azure")


def test_set_provider_elevenlabs_requires_config(voice_env):
    with pytest.raises(ValueError, match="not configured"):
        voice_clone.set_provider("elevenlabs")


def test_provider_roundtrip_when_configured(el_configured):
    voice_clone.set_provider("elevenlabs")
    assert voice_clone.resolved_provider() == "elevenlabs"
    assert voice_clone.tts_label() == "elevenlabs/eleven_multilingual_v2"
    st = voice_clone.status()
    assert st["resolved_provider"] == "elevenlabs"
    assert st["elevenlabs"]["configured"] is True
    assert st["elevenlabs"]["voice_id_set"] is True
    voice_clone.set_provider("openai")
    assert voice_clone.resolved_provider() == "openai"


# ---------------------------------------------------------------------------
# Audio plumbing
# ---------------------------------------------------------------------------

def test_pcm_to_wap_header_is_valid_wav():
    pcm = struct.pack("<h", 100) * 2400  # 0.1 s of something
    wav = voice_clone._pcm_to_wav(pcm, rate=24000)
    with wave.open(io.BytesIO(wav)) as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 24000
        assert wf.getnframes() == 2400


def test_status_leaks_no_secrets(el_configured):
    st = voice_clone.status()
    assert "test-key" not in str(st) and "env-voice-id" not in str(st)


# ---------------------------------------------------------------------------
# tts.synthesize dispatch
# ---------------------------------------------------------------------------

def test_synthesize_uses_elevenlabs_when_active(el_configured, monkeypatch):
    sent = {}

    def fake_el(text, language):
        sent["text"] = text
        return _fake_wav_bytes(rate=24000)

    monkeypatch.setattr(voice_clone, "synthesize_elevenlabs", fake_el)
    voice_clone.set_provider("elevenlabs")
    report = {}
    out = tts_module.synthesize("salom", "uz", report=report)
    with wave.open(io.BytesIO(out)) as wf:
        assert wf.getframerate() == 24000
    assert sent["text"] == "salom"
    assert report == {"provider": "elevenlabs", "model": "eleven_multilingual_v2"}


def test_elevenlabs_failure_falls_back_to_mock(voice_env, monkeypatch):
    """Mock mode + ElevenLabs runtime failure -> pre-VC1 mock path + honest report."""
    monkeypatch.setattr(settings, "elevenlabs_api_key", "k")
    monkeypatch.setattr(settings, "elevenlabs_voice_id", "vid")

    def boom(text, language):
        raise RuntimeError("provider down")

    monkeypatch.setattr(voice_clone, "synthesize_elevenlabs", boom)
    voice_clone.set_provider("elevenlabs")
    report = {}
    out = tts_module.synthesize("salom", "uz", report=report)
    with wave.open(io.BytesIO(out)) as wf:  # valid mock WAV still returned
        assert wf.getnframes() > 0
    assert report["provider"] == "openai"
    assert report["model"] == settings.tts_model


def test_elevenlabs_failure_falls_back_to_openai(el_configured, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "sk-fake")
    monkeypatch.setattr(voice_clone, "synthesize_elevenlabs",
                        lambda t, l: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.setattr(tts_module, "_openai_synthesize",
                        lambda t, l: b"OPENAI-WAV")
    voice_clone.set_provider("elevenlabs")
    report = {}
    out = tts_module.synthesize("salom", "uz", report=report)
    assert out == b"OPENAI-WAV"
    assert report["provider"] == "openai"


# ---------------------------------------------------------------------------
# Enrollment
# ---------------------------------------------------------------------------

def test_enroll_requires_consent(el_configured):
    with pytest.raises(ValueError, match="consent"):
        voice_clone.enroll([FakeSample(b"RIFF")], consent="")


def test_enroll_sample_count_limits(el_configured):
    with pytest.raises(ValueError, match="1-5"):
        voice_clone.enroll([], consent="yes")
    with pytest.raises(ValueError, match="1-5"):
        voice_clone.enroll([FakeSample(b"RIFF")] * 6, consent="yes")


def test_enroll_missing_api_key(voice_env):
    with pytest.raises(RuntimeError, match="API key"):
        voice_clone.enroll([FakeSample(b"RIFF")], consent="yes")


def test_enroll_happy_path_cleans_temp_and_stores_outside_repo(el_configured, monkeypatch):
    seen_dirs = []

    def fake_add(name, paths):
        seen_dirs.append(Path(paths[0]).parent)
        assert all(p.exists() for p in paths)
        return "new-voice-id"

    monkeypatch.setattr(voice_clone, "_el_add_voice", fake_add)
    result = voice_clone.enroll(
        [FakeSample(b"RIFF-a"), FakeSample(b"RIFF-b")],
        consent="yes", name="Erkin",
    )
    assert result["voice_id"] == "new-voice-id"
    # samples dir deleted after processing
    assert seen_dirs and not seen_dirs[0].exists()
    # voice_id stored OUTSIDE the repo (tmp_path), and readable back
    cfg_path = Path(settings.voice_config_path)
    assert cfg_path.exists() and not cfg_path.is_relative_to(REPO_ROOT)
    assert voice_clone.effective_voice_id() == "new-voice-id"
    # status now reports configured (key + enrolled voice id)
    assert voice_clone.status()["elevenlabs"]["configured"] is True


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

def test_voice_status_endpoint(voice_env):
    r = client.get("/api/voice/status")
    assert r.status_code == 200
    body = r.json()
    assert body["resolved_provider"] == "openai"
    assert body["elevenlabs"]["configured"] is False


def test_voice_provider_endpoint_rejects_bogus(voice_env):
    assert client.post("/api/voice/provider",
                       json={"provider": "bogus"}).status_code == 400


def test_voice_provider_endpoint_rejects_unconfigured_elevenlabs(voice_env):
    r = client.post("/api/voice/provider", json={"provider": "elevenlabs"})
    assert r.status_code == 400 and "not configured" in r.json()["detail"]


def test_voice_provider_endpoint_switches_when_configured(el_configured):
    r = client.post("/api/voice/provider", json={"provider": "elevenlabs"})
    assert r.status_code == 200 and r.json()["resolved_provider"] == "elevenlabs"
    r = client.post("/api/voice/provider", json={"provider": "openai"})
    assert r.status_code == 200 and r.json()["resolved_provider"] == "openai"


def test_voice_enroll_endpoint(el_configured, monkeypatch):
    monkeypatch.setattr(voice_clone, "_el_add_voice",
                        lambda name, paths: "api-voice-id")
    # consent gate
    r = client.post("/api/voice/enroll",
                    files=[("audio", ("s.wav", b"RIFF", "audio/wav"))],
                    data={"consent": "", "name": "T"})
    assert r.status_code == 400 and "consent" in r.json()["detail"]
    # 6 samples -> 400
    r = client.post(
        "/api/voice/enroll",
        files=[("audio", (f"s{i}.wav", b"RIFF", "audio/wav")) for i in range(6)],
        data={"consent": "yes"},
    )
    assert r.status_code == 400 and "1-5" in r.json()["detail"]
    # happy path
    r = client.post(
        "/api/voice/enroll",
        files=[("audio", ("s1.wav", b"RIFF", "audio/wav")),
               ("audio", ("s2.wav", b"RIFF", "audio/wav"))],
        data={"consent": "yes", "name": "Erkin"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["voice_id"] == "api-voice-id"
    assert voice_clone.effective_voice_id() == "api-voice-id"


def test_voice_enroll_requires_api_key(voice_env):
    r = client.post("/api/voice/enroll",
                    files=[("audio", ("s.wav", b"RIFF", "audio/wav"))],
                    data={"consent": "yes"})
    assert r.status_code == 503


# ---------------------------------------------------------------------------
# provider_info truthfulness on a real /api/turn (mock mode)
# ---------------------------------------------------------------------------

def _post_turn(conv_id):
    return client.post(
        "/api/turn",
        files={"audio": ("rec.wav", _fake_wav_bytes(), "audio/wav")},
        data={"conversation_id": conv_id, "language": "uz",
              "mode": "dub", "source_language": "en"},
    )


def test_turn_provider_info_openai_unchanged(voice_env, mock_turn_env):
    r = _post_turn("vc1-openai")
    assert r.status_code == 200, r.text
    info = r.json()["provider_info"]
    assert info["tts"] == "openai/tts-1"  # legacy string, byte-identical


def test_turn_provider_info_elevenlabs_when_active(voice_env, mock_turn_env, monkeypatch):
    monkeypatch.setattr(settings, "elevenlabs_api_key", "k")
    monkeypatch.setattr(settings, "elevenlabs_voice_id", "vid")
    monkeypatch.setattr(voice_clone, "synthesize_elevenlabs",
                        lambda t, l: _fake_wav_bytes(rate=24000))
    voice_clone.set_provider("elevenlabs")
    r = _post_turn("vc1-el")
    assert r.status_code == 200, r.text
    info = r.json()["provider_info"]
    assert info["tts"] == "elevenlabs/eleven_multilingual_v2"
    assert info["mode"] == "dub"  # DUB1 observability untouched


# ---------------------------------------------------------------------------
# Frontend (structural + syntax)
# ---------------------------------------------------------------------------

def test_frontend_has_voice_ui_and_functions():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert 'id="voiceBtnEleven"' in html and 'id="voiceBtnOpenai"' in html
    assert "function refreshVoiceStatus()" in html
    assert "function setVoiceProvider(provider)" in html
    assert "refreshVoiceStatus();" in html  # called on load
    # DUB1 request shape still intact next to the new UI
    assert "formData.append('mode', 'dub');" in html


@requires_node
def test_frontend_inline_script_node_check():
    html = INDEX_HTML.read_text(encoding="utf-8")
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    assert scripts
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as f:
        f.write(scripts[0])
        path = f.name
    p = subprocess.run(["node", "--check", path], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[:1000]
