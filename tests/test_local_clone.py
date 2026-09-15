"""
CP5 local-clone tests — voice-lab Route B wrapper integration seam.

No GPU, no network, no real Sayro/Seed-VC environments are ever run. The
subprocess seam (_run_subprocess) is monkeypatched; a fake WAV is written
into the wrapper's output dir to simulate a successful conversion. The
global serialization lock is tested by racing concurrent synthesize calls
and asserting the seam is entered serially.

Run: python -m pytest tests/test_local_clone.py -v
"""

import io
import os
import re as _re
import shutil
import subprocess
import tempfile as _tf
import threading
import time
import wave
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

os.environ.pop("OPENAI_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from product.backend.config import settings  # noqa: E402
from product.backend.main import app  # noqa: E402
from product.backend.routers import turn as turn_module  # noqa: E402
from product.backend.services import voice_clone  # noqa: E402
from product.backend.services import tts as tts_module  # noqa: E402
from product.backend.services.session import session_manager  # noqa: E402

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_wav_bytes(seconds: float = 0.05, rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x01" * int(rate * seconds))
    return buf.getvalue()


def _write_fake_wav(path: Path, seconds: float = 0.05, rate: int = 24000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_fake_wav_bytes(seconds=seconds, rate=rate))


@pytest.fixture()
def voice_env(tmp_path, monkeypatch):
    """Isolated voice state: empty keys, out-of-repo config, fresh provider."""
    monkeypatch.setattr(settings, "elevenlabs_api_key", "")
    monkeypatch.setattr(settings, "elevenlabs_voice_id", "")
    monkeypatch.setattr(settings, "voice_config_path", tmp_path / "voice.json")
    monkeypatch.setattr(settings, "sayro_voice_lab_dir", "")
    monkeypatch.setattr(settings, "sayro_script", "b_sayro_then_seedvc.py")
    monkeypatch.setattr(settings, "sayro_python", "")
    monkeypatch.setattr(settings, "seedvc_python", "")
    monkeypatch.setattr(settings, "seedvc_dir", "")
    monkeypatch.setattr(settings, "seedvc_reference_wav", "")
    monkeypatch.setattr(settings, "route_b_extra_args", "")
    monkeypatch.setattr(settings, "local_clone_timeout_s", 30)
    monkeypatch.setattr(voice_clone, "_active_provider", None)
    voice_clone._local_clone_busy = False
    return tmp_path


@pytest.fixture()
def local_configured(voice_env, tmp_path, monkeypatch):
    """Local clone appears fully configured (paths exist; subprocess seam
    is patched in each test — no real Sayro/Seed-VC ever runs)."""
    fake_py = tmp_path / "venv" / "python.exe"
    fake_py.parent.mkdir(parents=True, exist_ok=True)
    fake_py.write_bytes(b"#!python\n"); fake_py.chmod(0o755)
    seed_py = tmp_path / "seedvc" / "python.exe"
    seed_py.parent.mkdir(parents=True, exist_ok=True)
    seed_py.write_bytes(b"#!python\n"); seed_py.chmod(0o755)
    lab_dir = tmp_path / "voice-lab"; lab_dir.mkdir()
    (lab_dir / "b_sayro_then_seedvc.py").write_bytes(b"# wrapper\n")
    seed_dir = tmp_path / "seed-vc"; seed_dir.mkdir()
    ref = tmp_path / "my_voice.wav"; _write_fake_wav(ref, seconds=0.1)
    monkeypatch.setattr(settings, "sayro_voice_lab_dir", str(lab_dir))
    monkeypatch.setattr(settings, "sayro_script", "b_sayro_then_seedvc.py")
    monkeypatch.setattr(settings, "sayro_python", str(fake_py))
    monkeypatch.setattr(settings, "seedvc_python", str(seed_py))
    monkeypatch.setattr(settings, "seedvc_dir", str(seed_dir))
    monkeypatch.setattr(settings, "seedvc_reference_wav", str(ref))
    monkeypatch.setattr(voice_clone, "_active_provider", None)
    return tmp_path


@pytest.fixture()
def mock_turn_env(tmp_path, monkeypatch):
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


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------

def test_seedvc_configured_requires_python_dir_and_reference(voice_env, tmp_path, monkeypatch):
    assert voice_clone.seedvc_configured() is False
    py = tmp_path / "py"; py.write_bytes(b"x"); py.chmod(0o755)
    sd = tmp_path / "svc"; sd.mkdir()
    ref = tmp_path / "ref.wav"; _write_fake_wav(ref)
    monkeypatch.setattr(settings, "seedvc_python", str(py))
    monkeypatch.setattr(settings, "seedvc_dir", str(sd))
    monkeypatch.setattr(settings, "seedvc_reference_wav", str(ref))
    assert voice_clone.seedvc_configured() is True
    monkeypatch.setattr(settings, "seedvc_reference_wav", "")
    assert voice_clone.seedvc_configured() is False


def test_sayro_configured_requires_wrapper_python_and_seedvc(voice_env, tmp_path, monkeypatch):
    assert voice_clone.sayro_configured() is False
    py = tmp_path / "py"; py.write_bytes(b"x"); py.chmod(0o755)
    lab = tmp_path / "lab"; lab.mkdir()
    (lab / "b_sayro_then_seedvc.py").write_bytes(b"x")
    spy = tmp_path / "sp"; spy.write_bytes(b"x"); spy.chmod(0o755)
    sd = tmp_path / "sd"; sd.mkdir()
    ref = tmp_path / "r.wav"; _write_fake_wav(ref)
    monkeypatch.setattr(settings, "sayro_python", str(py))
    monkeypatch.setattr(settings, "sayro_voice_lab_dir", str(lab))
    assert voice_clone.sayro_configured() is False
    monkeypatch.setattr(settings, "seedvc_python", str(spy))
    monkeypatch.setattr(settings, "seedvc_dir", str(sd))
    monkeypatch.setattr(settings, "seedvc_reference_wav", str(ref))
    assert voice_clone.sayro_configured() is True


def test_default_provider_resolves_to_openai_when_unconfigured(voice_env, monkeypatch):
    monkeypatch.setattr(settings, "tts_provider", "local-clone")
    monkeypatch.setattr(voice_clone, "_active_provider", None)
    assert voice_clone.active_provider() == "local-clone"
    assert voice_clone.resolved_provider() == "openai"


def test_set_provider_rejects_unconfigured_local(voice_env):
    with pytest.raises(ValueError, match="not configured"):
        voice_clone.set_provider("local-clone")


def test_set_provider_rejects_unknown(voice_env):
    with pytest.raises(ValueError):
        voice_clone.set_provider("azure")


def test_resolved_provider_local_when_configured(local_configured):
    voice_clone.set_provider("local-clone")
    assert voice_clone.resolved_provider() == "local-clone"
    assert voice_clone.tts_label() == "local-clone/sayro-seedvc"
    st = voice_clone.status()
    assert st["local_clone"]["configured"] is True
    assert st["local_clone"]["languages"] == ["uz"]
    voice_clone.set_provider("openai")
    assert voice_clone.resolved_provider() == "openai"


def test_status_reports_no_secrets_or_paths(voice_env):
    body = client.get("/api/voice/status").json()
    flat = str(body)
    assert "C:\\" not in flat
    assert body["resolved_provider"] == "openai"
    assert body["local_clone"]["busy"] is False


# ---------------------------------------------------------------------------
# synthesize_local_clone end-to-end (faked subprocess seam)
# ---------------------------------------------------------------------------

def _install_route_b_fake(monkeypatch, sleep_s: float = 0.0,
                          fail_once: bool = False):
    info = {
        "calls": [], "cwd": None, "fail_count": [0],
        "sentences_dir_existed": False, "sentence_file_text": None,
        "only_flag": None, "stage_flag": None, "seedvc_version": None,
    }

    def fake_run(cmd, timeout, cwd=None):
        info["calls"].append(list(cmd))
        info["cwd"] = cwd
        if fail_once and info["fail_count"][0] == 0:
            info["fail_count"][0] += 1
            raise RuntimeError("simulated GPU OOM")
        sent_dir = out_dir = None
        stage = only = sv = None
        for i, a in enumerate(cmd):
            if a == "--sentences" and i + 1 < len(cmd):
                sent_dir = Path(cmd[i + 1])
            if a == "--out" and i + 1 < len(cmd):
                out_dir = Path(cmd[i + 1])
            if a == "--stage" and i + 1 < len(cmd):
                stage = cmd[i + 1]
            if a == "--only" and i + 1 < len(cmd):
                only = cmd[i + 1]
            if a == "--seedvc-version" and i + 1 < len(cmd):
                sv = cmd[i + 1]
        info["stage_flag"] = stage; info["only_flag"] = only
        info["seedvc_version"] = sv
        assert sent_dir is not None, f"no --sentences in cmd: {cmd}"
        assert out_dir is not None, f"no --out in cmd: {cmd}"
        # Sentences dir was created by the caller *before* invoking us;
        # capture that fact here because the temp dir is deleted after
        # synthesize_local_clone returns.
        info["sentences_dir_existed"] = sent_dir.is_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        sfile = sent_dir / "001.txt"
        assert sfile.is_file(), f"sentence file missing: {sfile}"
        info["sentence_file_text"] = sfile.read_text(encoding="utf-8").strip()
        _write_fake_wav(out_dir / "001.wav", seconds=0.2, rate=24000)
        if sleep_s:
            time.sleep(sleep_s)

    monkeypatch.setattr(voice_clone, "_run_subprocess", fake_run)
    return info


def test_synthesize_local_clone_happy_path_returns_valid_wav(local_configured, monkeypatch):
    info = _install_route_b_fake(monkeypatch)
    voice_clone.set_provider("local-clone")
    out = voice_clone.synthesize_local_clone("Salom dunyo", "uz")
    with wave.open(io.BytesIO(out)) as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getnframes() > 0
    assert len(info["calls"]) == 1
    cmd = info["calls"][0]
    assert info["cwd"] == settings.sayro_voice_lab_dir
    assert Path(cmd[1]).name == "b_sayro_then_seedvc.py"
    assert cmd[0] == settings.sayro_python
    # Real wrapper CLI flags only:
    assert cmd[2:4] == ["--stage", "all"]
    assert "--sentences" in cmd
    # sentences dir existed when wrapper was invoked (created per-request)
    assert info["sentences_dir_existed"] is True
    assert info["sentence_file_text"] == "Salom dunyo"
    assert info["stage_flag"] == "all"
    assert info["only_flag"] == "1"
    assert info["seedvc_version"] == "v1"
    assert "--out" in cmd
    assert "--target" in cmd and settings.seedvc_reference_wav in cmd
    assert "--seedvc-python" in cmd and settings.seedvc_python in cmd
    assert "--seedvc-dir" in cmd and settings.seedvc_dir in cmd
    # Flags that are NOT CLI-exposed by the wrapper must NOT be present:
    for forbidden in ("--text", "--output", "--seedvc-script",
                      "--seedvc-reference", "--normalizer",
                      "--diffusion-steps", "--length-adjust",
                      "--inference-cfg-rate", "--fp16",
                      "--f0-condition", "--auto-f0-adjust", "--semi-tone-shift"):
        assert forbidden not in cmd, f"unexpected flag {forbidden} sent to wrapper"
    leftover = list(Path(_tf.gettempdir()).glob("birovoz_localclone_*"))
    assert not leftover


def test_synthesize_local_clone_rejects_kazakh(local_configured, monkeypatch):
    _install_route_b_fake(monkeypatch)
    voice_clone.set_provider("local-clone")
    with pytest.raises(RuntimeError, match="Uzbek only"):
        voice_clone.synthesize_local_clone("Сәлем", "kk")


def test_synthesize_local_clone_missing_output_raises(local_configured, monkeypatch):
    def fake_run(cmd, timeout, cwd=None):
        for i, a in enumerate(cmd):
            if a in ("--out", "--sentences") and i + 1 < len(cmd):
                Path(cmd[i + 1]).mkdir(parents=True, exist_ok=True)
        # Do NOT write a converted wav
    monkeypatch.setattr(voice_clone, "_run_subprocess", fake_run)
    voice_clone.set_provider("local-clone")
    with pytest.raises(RuntimeError, match="no converted WAV"):
        voice_clone.synthesize_local_clone("salom", "uz")


def test_synthesize_local_clone_serialized_under_lock(local_configured, monkeypatch):
    concurrent = 4
    in_flight = [0]
    max_in_flight = [0]
    guard = threading.Lock()

    def fake_run(cmd, timeout, cwd=None):
        with guard:
            in_flight[0] += 1
            max_in_flight[0] = max(max_in_flight[0], in_flight[0])
        time.sleep(0.05)
        out_dir = None
        for i, a in enumerate(cmd):
            if a == "--out" and i + 1 < len(cmd):
                out_dir = Path(cmd[i + 1]); break
        assert out_dir is not None
        out_dir.mkdir(parents=True, exist_ok=True)
        # Also ensure the sentences dir exists with the file (it will, from
        # the caller, but be defensive for this test-local fake).
        for i, a in enumerate(cmd):
            if a == "--sentences" and i + 1 < len(cmd):
                sd = Path(cmd[i + 1])
                if sd.is_dir() and not (sd / "001.txt").exists():
                    (sd / "001.txt").write_text("salom", encoding="utf-8")
                break
        _write_fake_wav(out_dir / "001.wav", seconds=0.05, rate=24000)
        with guard:
            in_flight[0] -= 1

    monkeypatch.setattr(voice_clone, "_run_subprocess", fake_run)
    voice_clone.set_provider("local-clone")

    errs = []
    def worker():
        try:
            voice_clone.synthesize_local_clone("salom", "uz")
        except Exception as e:
            errs.append(e)

    threads = [threading.Thread(target=worker) for _ in range(concurrent)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert not errs, errs
    assert max_in_flight[0] == 1, (
        f"local-clone not serialized: max in-flight={max_in_flight[0]}"
    )
    assert voice_clone._local_clone_busy is False


# ---------------------------------------------------------------------------
# tts.synthesize dispatch + fallback + Kazakh routing
# ---------------------------------------------------------------------------

def test_tts_uses_local_clone_for_uzbek(local_configured, monkeypatch):
    monkeypatch.setattr(voice_clone, "synthesize_local_clone",
                        lambda t, l: _fake_wav_bytes(seconds=0.1, rate=24000))
    voice_clone.set_provider("local-clone")
    rep = {}
    out = tts_module.synthesize("salom", "uz", report=rep)
    with wave.open(io.BytesIO(out)) as wf:
        assert wf.getnframes() > 0
    assert rep == {"provider": "local-clone", "model": "sayro-seedvc"}


def test_tts_kazakh_stays_on_openai_when_local_selected(local_configured, monkeypatch):
    hit = {"local": False}
    def boom(t, l):
        hit["local"] = True
        raise RuntimeError("should not be called")
    monkeypatch.setattr(voice_clone, "synthesize_local_clone", boom)
    voice_clone.set_provider("local-clone")
    rep = {}
    out = tts_module.synthesize("Сәлем", "kk", report=rep)
    with wave.open(io.BytesIO(out)) as wf:
        assert wf.getnframes() > 0
    assert rep["provider"] == "openai"
    assert hit["local"] is False


def test_local_clone_failure_falls_back_to_mock(local_configured, monkeypatch):
    monkeypatch.setattr(voice_clone, "synthesize_local_clone",
                        lambda t, l: (_ for _ in ()).throw(RuntimeError("gpu oom")))
    voice_clone.set_provider("local-clone")
    rep = {}
    out = tts_module.synthesize("salom", "uz", report=rep)
    with wave.open(io.BytesIO(out)) as wf:
        assert wf.getnframes() > 0
    assert rep["provider"] == "openai"


def test_synthesize_b64_threadlocal_report(local_configured, monkeypatch):
    monkeypatch.setattr(voice_clone, "synthesize_local_clone",
                        lambda t, l: _fake_wav_bytes(seconds=0.05, rate=24000))
    voice_clone.set_provider("local-clone")
    b64 = tts_module.synthesize_b64("salom", "uz")
    assert isinstance(b64, str) and len(b64) > 0
    rep = tts_module.take_last_report()
    assert rep == {"provider": "local-clone", "model": "sayro-seedvc"}


# ---------------------------------------------------------------------------
# /api/turn truthful provider_info
# ---------------------------------------------------------------------------

def _post_turn(conv_id, lang="uz"):
    return client.post(
        "/api/turn",
        files={"audio": ("rec.wav", _fake_wav_bytes(), "audio/wav")},
        data={"conversation_id": conv_id, "language": lang,
              "mode": "dub", "source_language": "en"},
    )


def test_turn_provider_info_local_clone_when_active(local_configured, mock_turn_env, monkeypatch):
    monkeypatch.setattr(voice_clone, "synthesize_local_clone",
                        lambda t, l: _fake_wav_bytes(seconds=0.05, rate=24000))
    voice_clone.set_provider("local-clone")
    r = _post_turn("cp5-local")
    assert r.status_code == 200, r.text
    assert r.json()["provider_info"]["tts"] == "local-clone/sayro-seedvc"


def test_turn_provider_info_falls_back_on_local_failure(local_configured, mock_turn_env, monkeypatch):
    monkeypatch.setattr(voice_clone, "synthesize_local_clone",
                        lambda t, l: (_ for _ in ()).throw(RuntimeError("gpu oom")))
    voice_clone.set_provider("local-clone")
    r = _post_turn("cp5-fb")
    assert r.status_code == 200, r.text
    assert r.json()["provider_info"]["tts"] == "openai/tts-1"


def test_turn_kazakh_uses_openai_despite_local_selected(local_configured, mock_turn_env, monkeypatch):
    hit = {"local": False}
    def boom(t, l):
        hit["local"] = True
        raise RuntimeError("nope")
    monkeypatch.setattr(voice_clone, "synthesize_local_clone", boom)
    voice_clone.set_provider("local-clone")
    r = _post_turn("cp5-kk", lang="kk")
    assert r.status_code == 200, r.text
    assert r.json()["provider_info"]["tts"].startswith("openai/")
    assert hit["local"] is False


# ---------------------------------------------------------------------------
# Safety: no absolute paths / no audio/model files in product+tests
# ---------------------------------------------------------------------------

TRACKED_SOURCE_EXTS = (".py", ".html", ".md", ".txt", ".json", ".toml",
                       ".yml", ".yaml", ".ini", ".cfg", ".example")


def _iter_tracked_sources():
    for sub in ("product", "tests"):
        root = REPO_ROOT / sub
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            parts = set(p.relative_to(REPO_ROOT).parts)
            if "__pycache__" in parts or ".venv" in parts:
                continue
            if p.suffix.lower() in TRACKED_SOURCE_EXTS:
                yield p


def test_no_absolute_windows_paths_in_tracked_source():
    offenders = []
    for p in _iter_tracked_sources():
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = p.relative_to(REPO_ROOT)
        for line_no, line in enumerate(text.splitlines(), 1):
            if "C:\\Users" in line:
                stripped = line.lstrip()
                if rel.as_posix() == "product/backend/.env.example" and stripped.startswith("#"):
                    continue
                offenders.append((rel.as_posix(), line_no, line.strip()[:160]))
    assert not offenders, f"Absolute Windows paths: {offenders[:5]}"


def test_no_reference_audio_or_model_files():
    audio_exts = {".wav", ".mp3", ".ogg", ".flac", ".aac", ".m4a"}
    model_exts = {".ckpt", ".pt", ".pth", ".bin", ".safetensors", ".onnx"}
    bad = []
    for sub in ("product", "tests"):
        root = REPO_ROOT / sub
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            parts = set(p.relative_to(REPO_ROOT).parts)
            if "__pycache__" in parts or ".venv" in parts:
                continue
            suf = p.suffix.lower()
            rel = p.relative_to(REPO_ROOT).as_posix()
            if suf in audio_exts and rel != "product/frontend/hero.mp4":
                bad.append(rel)
            if suf in model_exts:
                bad.append(rel)
    assert not bad, f"reference audio/model files: {bad}"


# ---------------------------------------------------------------------------
# Frontend JS: existing repo method (extract inline <script>, node --check).
# ---------------------------------------------------------------------------

@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_frontend_inline_script_node_check_after_cp5():
    html = (REPO_ROOT / "product" / "frontend" / "index.html").read_text(encoding="utf-8")
    scripts = _re.findall(r"<script>(.*?)</script>", html, _re.S)
    assert scripts
    with _tf.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(scripts[0])
        path = f.name
    try:
        p = subprocess.run(["node", "--check", path], capture_output=True, text=True)
        assert p.returncode == 0, p.stderr[:1500]
    finally:
        os.unlink(path)


def test_frontend_has_two_chip_ui_and_local_clone_branches():
    html = (REPO_ROOT / "product" / "frontend" / "index.html").read_text(encoding="utf-8")
    assert 'id="voiceBtnOpenai"' in html
    assert 'id="voiceBtnEleven"' in html
    assert ">My voice<" in html
    assert "function _selectMyVoiceProvider" in html
    assert "'local-clone'" in html
    assert "formData.append('mode', 'dub');" in html
    assert "API_BASE + '/api/turn/stream'" in html
