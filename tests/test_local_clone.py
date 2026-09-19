"""
CP5 local-clone tests â€” voice-lab Route B wrapper integration seam.

No GPU, no network, no real Sayro/Seed-VC environments are ever run. The
subprocess seam (_run_subprocess) is monkeypatched; a fake WAV is written
into the wrapper's output dir to simulate a successful conversion. The
global serialization lock is tested by racing concurrent synthesize calls
and asserting the seam is entered serially.

Run: python -m pytest tests/test_local_clone.py -v
"""

import io
import json
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
    is patched in each test â€” no real Sayro/Seed-VC ever runs)."""
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
        "sentences_path_is_file": False, "sentence_file_text": None,
        "only_flag": None, "stage_flag": None, "seedvc_version": None,
    }

    def fake_run(cmd, timeout, cwd=None):
        info["calls"].append(list(cmd))
        info["cwd"] = cwd
        if fail_once and info["fail_count"][0] == 0:
            info["fail_count"][0] += 1
            raise RuntimeError("simulated GPU OOM")
        sent_path = out_dir = None
        stage = only = sv = None
        for i, a in enumerate(cmd):
            if a == "--sentences" and i + 1 < len(cmd):
                sent_path = Path(cmd[i + 1])
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
        assert sent_path is not None, f"no --sentences in cmd: {cmd}"
        assert out_dir is not None, f"no --out in cmd: {cmd}"
        # --sentences must point to a FILE (the numbered-sentences file)
        # not a directory. The real wrapper calls Path(path).read_text().
        assert sent_path.is_file(), (
            f"--sentences must be a file, got: {sent_path} "
            f"(is_dir={sent_path.is_dir()})"
        )
        info["sentences_path_is_file"] = True
        out_dir.mkdir(parents=True, exist_ok=True)
        info["sentence_file_text"] = sent_path.read_text(encoding="utf-8").strip()
        _write_fake_wav(out_dir / "1.wav", seconds=0.2, rate=24000)
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
    # --sentences points to a FILE path (sentences.txt), not a directory â€”
    # the real wrapper calls Path(path).read_text() on this argument.
    # We assert this by inspecting what the fake_run saw WHILE the temp
    # workspace was still alive (the temp dir is deleted in finally AFTER
    # synthesize returns, so stat'ing the path here would be too late).
    sent_idx = cmd.index("--sentences")
    sent_path = Path(cmd[sent_idx + 1])
    assert sent_path.name == "sentences.txt"
    assert info["sentences_path_is_file"] is True
    # The file content matches parse_numbered() expected format: "1. <text>"
    assert info["sentence_file_text"] == "1. Salom dunyo"
    assert info["stage_flag"] == "all"
    assert info["only_flag"] == "1"
    assert info["seedvc_version"] == "v2"
    assert "--out" in cmd
    assert "--target" in cmd and settings.seedvc_reference_wav in cmd
    assert "--seedvc-python" in cmd and settings.seedvc_python in cmd
    assert "--seedvc-dir" in cmd and settings.seedvc_dir in cmd
    assert cmd[cmd.index("--diffusion-steps") + 1] == "15"
    assert cmd[cmd.index("--diffusion-steps") + 1] == "15"
    # Flags that are NOT CLI-exposed by the wrapper must NOT be present:
    for forbidden in ("--text", "--output", "--seedvc-script",
                      "--seedvc-reference", "--normalizer",
                      "--length-adjust",
                      "--inference-cfg-rate", "--fp16",
                      "--f0-condition", "--auto-f0-adjust", "--semi-tone-shift"):
        assert forbidden not in cmd, f"unexpected flag {forbidden} sent to wrapper"
    leftover = list(Path(_tf.gettempdir()).glob("birovoz_localclone_*"))
    assert not leftover


def test_synthesize_local_clone_rejects_kazakh(local_configured, monkeypatch):
    _install_route_b_fake(monkeypatch)
    voice_clone.set_provider("local-clone")
    with pytest.raises(RuntimeError, match="Uzbek only"):
        voice_clone.synthesize_local_clone("Ð¡Ó™Ð»ÐµÐ¼", "kk")


def test_synthesize_local_clone_missing_output_raises(local_configured, monkeypatch):
    def fake_run(cmd, timeout, cwd=None):
        for i, a in enumerate(cmd):
            if a in ("--out", "--sentences") and i + 1 < len(cmd):
                Path(cmd[i + 1]).parent.mkdir(parents=True, exist_ok=True)
                p = Path(cmd[i + 1])
                if a == "--sentences":
                    p.write_text("1. salom\n", encoding="utf-8")
                else:
                    p.mkdir(parents=True, exist_ok=True)
        # Do NOT write a converted wav
    monkeypatch.setattr(voice_clone, "_run_subprocess", fake_run)
    voice_clone.set_provider("local-clone")
    with pytest.raises(RuntimeError, match="no converted WAV"):
        voice_clone.synthesize_local_clone("salom", "uz")


def test_format_numbered_sentence_matches_parse_numbered_regex():
    # Directly assert that _format_numbered_sentence produces a line that
    # parse_numbered() (re.compile(r"^(\d+)[.)]\s*(.+)$")) will match.
    import re
    pat = _re.compile(r"^(\d+)[.)]\s*(.+)$")
    line = voice_clone._format_numbered_sentence(1, "Salom dunyo")
    m = pat.match(line)
    assert m is not None, f"line {line!r} does not match parse_numbered()"
    assert int(m.group(1)) == 1
    assert m.group(2) == "Salom dunyo"
    # Multi-line input gets collapsed to a single line so splitlines()
    # in the wrapper doesn't treat it as multiple entries.
    multi = voice_clone._format_numbered_sentence(1, "line one\nline two")
    assert "\n" not in multi
    assert pat.match(multi).group(2) == "line one line two"


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
        sfile = None
        for i, a in enumerate(cmd):
            if a == "--out" and i + 1 < len(cmd):
                out_dir = Path(cmd[i + 1]); break
        for i, a in enumerate(cmd):
            if a == "--sentences" and i + 1 < len(cmd):
                sfile = Path(cmd[i + 1]); break
        assert out_dir is not None and sfile is not None
        out_dir.mkdir(parents=True, exist_ok=True)
        # Ensure the sentences file exists (it will, from the caller).
        if not sfile.exists():
            sfile.parent.mkdir(parents=True, exist_ok=True)
            sfile.write_text("1. salom\n", encoding="utf-8")
        _write_fake_wav(out_dir / "1.wav", seconds=0.05, rate=24000)
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
    out = tts_module.synthesize("Ð¡Ó™Ð»ÐµÐ¼", "kk", report=rep)
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


# ---------------------------------------------------------------------------
# B1 regression: _run_subprocess decodes UTF-8 (incl. Cyrillic) safely.
# ---------------------------------------------------------------------------

def test_run_subprocess_decodes_utf8_cyrillic_stderr(tmp_path):
    """Regression for B1: on default Windows cp1252, a child writing
    Uzbek-Cyrillic UTF-8 to stderr must NOT raise UnicodeDecodeError â€”
    stderr tail is preserved (with replacement chars for invalid bytes)
    and surfaced in the RuntimeError message."""
    script = tmp_path / "cyrillic_err.py"
    script.write_text(
        "import sys\n"
        "sys.stderr.write('Ð¡Ð°Ð»Ð¾Ð¼ Ð´ÑƒÐ½Ñ‘ â€” Seed-VC Ñ…Ð°Ñ‚Ð¾: CUDA out of memory\\n')\n"
        "sys.exit(2)\n",
        encoding="utf-8",
    )
    import sys as _sys
    with pytest.raises(RuntimeError) as exc:
        voice_clone._run_subprocess(
            [_sys.executable, str(script)],
            timeout=10,
        )
    msg = str(exc.value)
    assert "exit=2" in msg
    # The Cyrillic MUST be decoded (not raise UnicodeDecodeError before
    # we can build the error message). With errors="replace", any bytes
    # that are not valid UTF-8 come through as U+FFFD rather than raising.
    assert "Ð¡Ð°Ð»Ð¾Ð¼" in msg or "\ufffd" in msg or "Seed-VC" in msg


def test_run_subprocess_nonzero_exit_includes_tail(tmp_path):
    """Non-zero exit still raises with the tail of stderr/stdout
    (preserves existing error-reporting behavior)."""
    script = tmp_path / "fail.py"
    script.write_text(
        "import sys\n"
        "print('line1')\n"
        "print('line2')\n"
        "print('line3', file=sys.stderr)\n"
        "print('line4', file=sys.stderr)\n"
        "sys.exit(3)\n",
        encoding="utf-8",
    )
    import sys as _sys
    with pytest.raises(RuntimeError) as exc:
        voice_clone._run_subprocess([_sys.executable, str(script)], timeout=10)
    msg = str(exc.value)
    assert "exit=3" in msg
    # tail is last 5 lines of stderr-or-stdout; line4 should be visible
    assert "line4" in msg


# ---------------------------------------------------------------------------
# B2 regression: _which rejects directories for absolute paths.
# ---------------------------------------------------------------------------

def test_which_rejects_directory_as_python_executable(tmp_path):
    """An absolute path that points at a DIRECTORY (e.g. a user typo
    leaving a trailing backslash) must NOT be accepted as a Python
    executable â€” otherwise local_clone_configured() would be True and
    subprocess.run would fail with an opaque WinError 193."""
    not_py = tmp_path / "not_python"
    not_py.mkdir()
    assert voice_clone._which(str(not_py)) is False
    # A file that exists is accepted.
    real_py = tmp_path / "py.exe"
    real_py.write_bytes(b"#!/usr/bin/env python\n")
    real_py.chmod(0o755)
    assert voice_clone._which(str(real_py)) is True
    # Empty/None rejected.
    assert voice_clone._which("") is False


def test_which_bare_command_found_or_not(tmp_path, monkeypatch):
    """Bare command lookups still go through shutil.which (unchanged)."""
    # A bare name that doesn't exist on PATH returns False.
    assert voice_clone._which("definitely-not-a-real-exe-xyzzy-12345") is False


def test_local_clone_unconfigured_when_python_is_directory(voice_env, tmp_path, monkeypatch):
    """End-to-end: if SAYRO_PYTHON points at a directory, local-clone is
    reported as unconfigured and set_provider('local-clone') raises."""
    not_py = tmp_path / "venv_dir"; not_py.mkdir()
    seed_py = tmp_path / "sp"; seed_py.write_bytes(b"x"); seed_py.chmod(0o755)
    sd = tmp_path / "svc"; sd.mkdir()
    lab = tmp_path / "lab"; lab.mkdir()
    (lab / "b_sayro_then_seedvc.py").write_bytes(b"x")
    ref = tmp_path / "r.wav"; _write_fake_wav(ref)
    monkeypatch.setattr(settings, "sayro_python", str(not_py))
    monkeypatch.setattr(settings, "sayro_voice_lab_dir", str(lab))
    monkeypatch.setattr(settings, "sayro_script", "b_sayro_then_seedvc.py")
    monkeypatch.setattr(settings, "seedvc_python", str(seed_py))
    monkeypatch.setattr(settings, "seedvc_dir", str(sd))
    monkeypatch.setattr(settings, "seedvc_reference_wav", str(ref))
    monkeypatch.setattr(voice_clone, "_active_provider", None)
    assert voice_clone.local_clone_configured() is False
    with pytest.raises(ValueError, match="not configured"):
        voice_clone.set_provider("local-clone")


# ---------------------------------------------------------------------------
# A1 regression: /api/turn/stream chat mode truthful provider_info
# ---------------------------------------------------------------------------

def _stream_chat_with_local_failure(monkeypatch, conv="chat-fb", language="uz"):
    """POST a chat-mode stream request while local-clone is selected but
    forced to fail; returns parsed NDJSON events. The final done event's
    provider_info.tts must report openai (fallback), not local-clone."""
    # Force local-clone selected but synthesize_local_clone always raises â€”
    # matches the scenario in test_turn_provider_info_falls_back_on_local_failure
    # but via the STREAMING chat path (non-dub, single part).
    monkeypatch.setattr(voice_clone, "synthesize_local_clone",
                        lambda t, l: (_ for _ in ()).throw(RuntimeError("gpu oom")))
    voice_clone.set_provider("local-clone")

    out = []
    with client.stream(
        "POST", "/api/turn/stream",
        files={"audio": ("t.wav", _fake_wav_bytes(), "audio/wav")},
        data={"conversation_id": conv, "language": language, "mode": "chat"},
    ) as r:
        assert r.status_code == 200, r.read()
        for line in r.iter_lines():
            if not line.strip():
                continue
            out.append(json.loads(line))
    return out


def test_stream_chat_fallback_provider_info_truthful(local_configured, mock_turn_env, monkeypatch):
    """A1 regression: when local-clone is selected but fails for a
    chat-mode stream request, the done event's provider_info.tts must
    report 'openai/...' (what actually synthesized the audio) rather
    than lying 'local-clone/sayro-seedvc'."""
    evs = _stream_chat_with_local_failure(monkeypatch, conv="a1-fb")
    types = [e["type"] for e in evs]
    assert types == ["meta", "part", "done"], types
    done = next(e for e in evs if e["type"] == "done")
    assert done["provider_info"]["mode"] == "chat"
    # Must NOT claim local-clone â€” the clone raised and we fell back.
    assert done["provider_info"]["tts"].startswith("openai/"), (
        f"expected openai fallback label, got {done['provider_info']['tts']!r}"
    )


def test_stream_chat_happy_path_provider_info_truthful(local_configured, mock_turn_env, monkeypatch):
    """A1 positive path: when local-clone succeeds in chat-mode stream,
    provider_info.tts reports local-clone/sayro-seedvc (unchanged)."""
    monkeypatch.setattr(voice_clone, "synthesize_local_clone",
                        lambda t, l: _fake_wav_bytes(seconds=0.05, rate=24000))
    voice_clone.set_provider("local-clone")
    out = []
    with client.stream(
        "POST", "/api/turn/stream",
        files={"audio": ("t.wav", _fake_wav_bytes(), "audio/wav")},
        data={"conversation_id": "a1-ok", "language": "uz", "mode": "chat"},
    ) as r:
        assert r.status_code == 200, r.read()
        for line in r.iter_lines():
            if line.strip():
                out.append(json.loads(line))
    done = next(e for e in out if e["type"] == "done")
    assert done["provider_info"]["tts"] == "local-clone/sayro-seedvc"


# ---------------------------------------------------------------------------
# Existing local-clone -> OpenAI fallback unchanged (legacy /api/turn path).
# ---------------------------------------------------------------------------

def test_legacy_turn_fallback_still_openai_after_patch(local_configured, mock_turn_env, monkeypatch):
    """Guard: local-clone failure still falls back to OpenAI on the
    legacy /api/turn endpoint (unchanged behavior)."""
    monkeypatch.setattr(voice_clone, "synthesize_local_clone",
                        lambda t, l: (_ for _ in ()).throw(RuntimeError("gpu oom")))
    voice_clone.set_provider("local-clone")
    r = _post_turn("cp5-fb2")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider_info"]["tts"] == "openai/tts-1"


# ---------------------------------------------------------------------------
# DUB3 multi-part provider aggregation unchanged.
# ---------------------------------------------------------------------------

def test_dub3_merge_mixed_providers_reports_openai():
    """Guard: _merge_part_reports still downgrades to openai when any
    part fell back (DUB3 aggregation contract)."""
    assert tts_module._merge_part_reports([
        {"provider": "local-clone", "model": "sayro-seedvc"},
        {"provider": "openai", "model": "tts-1"},
    ]) == {"provider": "openai", "model": settings.tts_model}
    assert tts_module._merge_part_reports([
        {"provider": "local-clone", "model": "sayro-seedvc"},
        {"provider": "local-clone", "model": "sayro-seedvc"},
    ]) == {"provider": "local-clone", "model": "sayro-seedvc"}
    assert tts_module._merge_part_reports([]) == {}


# ---------------------------------------------------------------------------
# Latency instrumentation: marker parsing, Popen streaming, env hardening,
# marker-based VC output selection.
# ---------------------------------------------------------------------------

def _make_emitting_script(out_dir: Path, emit_vc_path: str = "b_sayro_vc/t01.wav",
                          exit_code: int = 0):
    """Write a tiny Python script that prints the real Route B marker
    lines exactly as observed on Windows, plus a real WAV file into
    <out_dir>/<emit_vc_path>. Returns path to script."""
    out_dir.mkdir(parents=True, exist_ok=True)
    vc_full = out_dir / emit_vc_path
    vc_full.parent.mkdir(parents=True, exist_ok=True)
    _write_fake_wav(vc_full, seconds=0.1, rate=22050)
    # Also write Sayro's raw wav one directory up (decoy).
    sayro_full = out_dir / "b_sayro" / "t01.wav"
    sayro_full.parent.mkdir(parents=True, exist_ok=True)
    _write_fake_wav(sayro_full, seconds=0.05, rate=22050)
    script = out_dir.parent / "emit.py"
    out_dir_esc = str(out_dir).replace("\\", "\\\\")
    script.write_text(
        "import sys, os, time\n"
        f"os.makedirs(r'{out_dir_esc}', exist_ok=True)\n"
        "print('[B] loaded in 12.5s', flush=True)\n"
        "print('[B] t01 -> b_sayro/t01.wav', flush=True)\n"
        "print('[B] peak GPU memory: 4.35 GB', flush=True)\n"
        "print('[B] Sayro stage done - VRAM released', flush=True)\n"
        "print('[B] Seed-VC python: some/python.exe', flush=True)\n"
        "print('[B] Seed-VC: v1 via some/inference.py', flush=True)\n"
        "print('[B][vc] t01.wav -> b_sayro_vc/t01.wav', flush=True)\n"
        "print('[B] convert stage done', flush=True)\n"
        f"sys.exit({exit_code})\n",
        encoding="utf-8",
    )
    return script


def test_run_subprocess_parses_route_b_markers(tmp_path):
    """_run_subprocess must parse the wrapper's [B] markers and return
    total/sayro_load/vc timing info + vc_out relative path."""
    import sys as _sys
    out_dir = tmp_path / "emit" / "out"
    script = _make_emitting_script(out_dir)
    result = voice_clone._run_subprocess(
        [_sys.executable, str(script)],
        timeout=10,
        cwd=str(tmp_path),
    )
    assert isinstance(result, dict), "_run_subprocess must return a dict"
    assert result["total_s"] >= 0.0
    timings = result["timings"]
    assert timings["sayro_load_s"] == 12.5
    assert "sayro_done_s" in timings
    assert "vc_t_done_s" in timings
    assert "convert_done_s" in timings
    assert "total_s" in timings
    assert result["markers"]["vc_out"] == "b_sayro_vc/t01.wav"
    assert result["markers"]["peak_gpu_mem"] == "4.35"


def test_run_subprocess_sets_pythonunbuffered_env(tmp_path):
    """The child must receive PYTHONUNBUFFERED=1 and BLAS single-thread
    env overrides so output flushes immediately and CPU BLAS threads do
    not thrash."""
    import sys as _sys
    script = tmp_path / "envcheck.py"
    script.write_text(
        "import os, sys\n"
        "vals = {\n"
        "    'PYTHONUNBUFFERED': os.environ.get('PYTHONUNBUFFERED'),\n"
        "    'OMP_NUM_THREADS': os.environ.get('OMP_NUM_THREADS'),\n"
        "    'MKL_NUM_THREADS': os.environ.get('MKL_NUM_THREADS'),\n"
        "    'TORCH_CUDNN_V8_API_ENABLED': os.environ.get('TORCH_CUDNN_V8_API_ENABLED'),\n"
        "}\n"
        "sys.stdout.write('ENV:' + repr(vals) + '\\n')\n"
        "sys.stdout.flush()\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    result = voice_clone._run_subprocess(
        [_sys.executable, str(script)], timeout=10, cwd=str(tmp_path),
    )
    joined = "\n".join(result["stdout_tail"])
    assert "'PYTHONUNBUFFERED': '1'" in joined
    assert "'OMP_NUM_THREADS': '1'" in joined
    assert "'MKL_NUM_THREADS': '1'" in joined
    assert "'TORCH_CUDNN_V8_API_ENABLED': '1'" in joined


def test_run_subprocess_timeout_kills_child(tmp_path):
    """A child that outlasts timeout must be killed promptly and raise
    RuntimeError, not hang the caller."""
    import sys as _sys
    script = tmp_path / "sleeper.py"
    script.write_text(
        "import time, sys\n"
        "print('[B] loaded in 1.0s', flush=True)\n"
        "time.sleep(30)\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    t0 = time.time()
    with pytest.raises(RuntimeError, match="timed out"):
        voice_clone._run_subprocess(
            [_sys.executable, str(script)], timeout=2, cwd=str(tmp_path),
        )
    elapsed = time.time() - t0
    assert elapsed < 10, f"timeout kill took too long ({elapsed:.1f}s)"


def test_synthesize_uses_markers_to_pick_vc_output(local_configured, monkeypatch):
    """When the wrapper emits a '[B][vc] ... -> b_sayro_vc/t01.wav' marker,
    BirOvoz must pick THAT file rather than falling back to a directory
    scan (and never pick a stray Sayro-raw wav)."""
    captured = {"vc_bytes": None, "sayro_bytes": None}
    def fake_run(cmd, timeout, cwd=None):
        out_path = None
        for i, a in enumerate(cmd):
            if a == "--out" and i + 1 < len(cmd):
                out_path = Path(cmd[i + 1])
        if out_path is not None:
            (out_path / "b_sayro").mkdir(parents=True, exist_ok=True)
            (out_path / "b_sayro_vc").mkdir(parents=True, exist_ok=True)
            # Decoy Sayro-raw WAV (should NOT be picked) â€” very short.
            _write_fake_wav(out_path / "b_sayro" / "t01.wav", seconds=0.05, rate=22050)
            # Real VC wav â€” longer, easy to distinguish by length.
            _write_fake_wav(out_path / "b_sayro_vc" / "t01.wav", seconds=0.25, rate=22050)
            # Make the decoy NEWER to defeat naive mtime-only scanners.
            now = time.time()
            os.utime(out_path / "b_sayro_vc" / "t01.wav", (now - 20, now - 20))
            os.utime(out_path / "b_sayro" / "t01.wav", (now, now))
            captured["vc_bytes"] = (out_path / "b_sayro_vc" / "t01.wav").read_bytes()
            captured["sayro_bytes"] = (out_path / "b_sayro" / "t01.wav").read_bytes()
        return {
            "timings": {"sayro_load_s": 1.0, "total_s": 2.0},
            "markers": {"vc_out": "b_sayro_vc/t01.wav"},
            "total_s": 2.0,
            "stdout_tail": [],
            "stderr_tail": [],
        }
    monkeypatch.setattr(voice_clone, "_run_subprocess", fake_run)
    voice_clone.set_provider("local-clone")
    out = voice_clone.synthesize_local_clone("Salom", "uz")
    # The returned bytes must match the VC wav (0.25s @ 22050), not the
    # shorter Sayro decoy (0.05s @ 22050). Distinguish by byte length.
    assert captured["vc_bytes"] is not None and captured["sayro_bytes"] is not None
    assert out == captured["vc_bytes"]
    assert out != captured["sayro_bytes"]
    # Length sanity: 0.25s * 22050Hz * 2 bytes/samp (s16 PCM) + 44-byte
    # WAV header â‰ˆ 11069 bytes; Sayro decoy â‰ˆ 2249 bytes.
    assert len(out) > 5000, f"VC wav too short ({len(out)} bytes)"



