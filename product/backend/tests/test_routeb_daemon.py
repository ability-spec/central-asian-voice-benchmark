"""Unit tests for the Route B persistent-daemon client in voice_clone.py.

These tests don't require CUDA / Sayro / Seed-VC — they replace the daemon
subprocess with a tiny Python stub script that speaks the same JSONL
protocol, so we verify:
  * the client correctly waits for the daemon "[B] ... daemon ready" line
    before sending jobs;
  * one job -> one base64-encoded WAV comes back and is returned as bytes;
  * a daemon crash mid-job triggers a respawn and retry;
  * Sayro load/generation failures release model/CUDA state so the next
    request can reload cleanly;
  * an explicit daemon error raises RuntimeError (so the caller falls back
    to the one-shot path);
  * the daemon is auto-disabled when the vendored wrapper lacks --daemon
    (older external voice-lab checkouts).
"""
import base64
import importlib.util
import io
import json
import os
import queue
import struct
import sys
import types
import tempfile
import textwrap
import threading
import time
from pathlib import Path
from unittest import mock

import pytest

# Ensure the repo root is importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


def _make_stub(tmp_path: Path, *, fail_n: int = 0, die_on_job: bool = False,
               die_once: bool = False, error_once: bool = False,
               record_ids: Path | None = None,
               skip_ready: bool = False, chatter_lines: int = 0,
               echo_text: bool = False) -> Path:
    """Write a tiny stub Python script that speaks the daemon JSONL protocol.

    Behaviour:
      * prints "[B] Route B daemon ready" on startup (unless skip_ready);
      * for each received job:
         - if die_on_job: exits immediately (simulates crash);
         - if die_once: the first process exits, then a replacement succeeds;
         - if error_once: the first accepted job returns a retryable Seed-VC
           error, then the same process succeeds;
         - if fail_n > 0: decrements and returns {"ok": false, "error": "..."};
         - if record_ids is set: appends every received job id to that file;
         - if chatter_lines > 0: prints that many log-like non-JSON lines to
           stdout BEFORE the JSON result (regression test for P1-1: client
           must skip these even if one contains a stray '{');
         - if echo_text: the stub also verifies the job's `text` field
           round-trips as valid UTF-8 (contains Uzbek diacritics), and
           returns it in an `echo` field so the caller can assert. Used
           by P1-2 regression test.
         - otherwise returns {"ok": true, "id": <id>, "wav_b64": <WAV>}.
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    stub = tmp_path / "stub_daemon.py"
    stub.write_text(textwrap.dedent(f"""
        import json, sys, time, base64, os
        fail_n = {fail_n}
        die = {repr(die_on_job)}
        die_once = {repr(die_once)}
        error_once = {repr(error_once)}
        die_once_state = {repr(str(tmp_path / "die_once.marker"))}
        error_once_state = {repr(str(tmp_path / "error_once.marker"))}
        record_ids = {repr(str(record_ids) if record_ids is not None else "")}
        skip_ready = {repr(skip_ready)}
        chatter = {chatter_lines}
        echo_text = {repr(echo_text)}
        if not skip_ready:
            print("[B] Route B daemon ready (stub)", flush=True)
        # Minimal valid WAV: 44-byte header, 1 sample (2 bytes).
        import struct
        pcm = struct.pack("<H", 0)
        wav = (b"RIFF" + struct.pack("<I", 36+len(pcm)) + b"WAVE"
               + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, 16000, 32000, 2, 16)
               + b"data" + struct.pack("<I", len(pcm)) + pcm)
        for raw in sys.stdin:
            line = raw.strip()
            if not line: continue
            job = json.loads(line)
            if record_ids:
                with open(record_ids, "a", encoding="utf-8") as f:
                    f.write(job.get("id", "") + "\\n")
            if die:
                sys.exit(2)
            if die_once and not os.path.exists(die_once_state):
                open(die_once_state, "w", encoding="utf-8").close()
                sys.exit(2)
            if error_once and not os.path.exists(error_once_state):
                open(error_once_state, "w", encoding="utf-8").close()
                print(json.dumps({{"ok": False, "id": job.get("id"),
                                   "error": "seed-vc daemon died after accepting job"}}),
                      flush=True)
                continue
            if fail_n > 0:
                fail_n -= 1
                print(json.dumps({{"ok": False, "id": job.get("id"), "error": "stub transient error"}}), flush=True)
                continue
            # Simulate third-party chatter (CUDA/torch/hydra log lines)
            # leaking onto stdout before the real JSON result.
            for i in range(chatter):
                # Include an opening brace in the middle of one line to
                # make sure the client doesn't mis-parse it as JSON. Use a
                # plain string (not f-string) so the braces are literal.
                print("[third-party] step " + str(i) + " warming up kernels {{...}}", flush=True)
            echo = {{}}
            if echo_text:
                t = job.get("text", "")
                # Uzbek diacritic probe: if UTF-8 decoding broke, these
                # chars will be replaced with ? / U+FFFD.
                echo["echo"] = t
                echo["diacritics_ok"] = ("Oʻ" in t) and ("Gʻ" in t) and ("ʻ" in t)
                if not echo["diacritics_ok"]:
                    print(json.dumps({{"ok": False, "id": job.get("id"),
                                       "error": "UTF-8 diacritics were corrupted",
                                       **echo}}), flush=True)
                    continue
            print(json.dumps({{
                "ok": True,
                "id": job.get("id"),
                "wav_b64": base64.b64encode(wav).decode("ascii"),
                "path": "/tmp/stub.wav",
                "elapsed_s": 0.01,
                "timings": {{"total_s": 0.01}},
                **echo,
            }}), flush=True)
    """), encoding="utf-8")
    return stub


def _silent_wav_bytes() -> bytes:
    pcm = struct.pack("<H", 0)
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE"
            + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, 16000, 32000, 2, 16)
            + b"data" + struct.pack("<I", len(pcm)) + pcm)


def _load_routeb_wrapper():
    """Import the wrapper without importing torch/qwen_tts."""
    wrapper_path = Path(__file__).resolve().parents[1] / \
        "services/routeb/b_sayro_then_seedvc.py"
    routeb_dir = str(wrapper_path.parent)
    if routeb_dir not in sys.path:
        sys.path.insert(0, routeb_dir)
    spec = importlib.util.spec_from_file_location(
        "routeb_wrapper_sayro_recovery_test", wrapper_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _fake_torch():
    cuda = types.SimpleNamespace(
        empty_cache=mock.Mock(),
        max_memory_allocated=lambda: 0,
    )
    return types.SimpleNamespace(cuda=cuda)


@pytest.fixture
def vc_env(tmp_path, monkeypatch):
    """Provide enough of the config/resolution environment for the client
    to point at our stub script and stub python, without hitting real files."""
    from product.backend.services import voice_clone

    stub = _make_stub(tmp_path)
    # Patch resolver functions so they return our stub regardless of config.
    monkeypatch.setattr(voice_clone, "_resolve_sayro_script", lambda: stub)
    monkeypatch.setattr(voice_clone, "_resolve_sayro_python", lambda _p: sys.executable)
    monkeypatch.setattr(voice_clone, "_resolve_seedvc_dir", lambda: tmp_path)
    monkeypatch.setattr(voice_clone, "_resolve_seedvc_python", lambda _d: sys.executable)
    monkeypatch.setattr(voice_clone, "_resolve_wrapper_cwd", lambda _p: str(tmp_path))
    # Replace the wrapper source sniff so we look at the stub (which has no --daemon
    # string, so we monkeypatch _get_daemon to skip the check instead).
    # Reset module-level daemon state for a clean test.
    voice_clone._routeb_daemon = None
    voice_clone._daemon_disabled = False
    # Stub settings used by the client.
    class _Settings:
        seedvc_reference_wav = str(tmp_path / "ref.wav")
        route_b_diffusion_steps = 15
        route_b_length_adjust = 1.0
        route_b_intelligibility = 0.8
        route_b_similarity = 0.8
        route_b_extra_args = ""
    (tmp_path / "ref.wav").write_bytes(b"\x00" * 16)
    monkeypatch.setattr(voice_clone.settings, "seedvc_reference_wav", str(tmp_path / "ref.wav"))
    monkeypatch.setattr(voice_clone.settings, "route_b_diffusion_steps", 15)
    monkeypatch.setattr(voice_clone.settings, "route_b_length_adjust", 1.0)
    monkeypatch.setattr(voice_clone.settings, "route_b_intelligibility", 0.8)
    monkeypatch.setattr(voice_clone.settings, "route_b_similarity", 0.8)
    monkeypatch.setattr(voice_clone.settings, "route_b_extra_args", "")
    # Bypass the "--daemon in source" sniff — the stub obviously doesn't
    # have that flag string.
    real_get = voice_clone._get_daemon
    def _get_no_sniff():
        if voice_clone._daemon_disabled:
            return None
        if voice_clone._routeb_daemon is None:
            voice_clone._routeb_daemon = voice_clone.RouteBDaemonClient()
        return voice_clone._routeb_daemon
    monkeypatch.setattr(voice_clone, "_get_daemon", _get_no_sniff)
    yield voice_clone
    # Cleanup: kill the daemon.
    if voice_clone._routeb_daemon is not None:
        voice_clone._routeb_daemon.shutdown()
        voice_clone._routeb_daemon = None


def test_daemon_happy_path(vc_env, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    wav = vc_env._synthesize_via_daemon("Salom", out, timeout=30.0)
    assert wav[:4] == b"RIFF"
    assert wav == _silent_wav_bytes()
    # Second call reuses the same process (no respawn).
    wav2 = vc_env._synthesize_via_daemon("Yaxshi", out, timeout=30.0)
    assert wav2[:4] == b"RIFF"


def _sayro_args(tmp_path):
    return types.SimpleNamespace(
        device="cuda:0",
        dtype="bfloat16",
        attn="sdpa",
        out=str(tmp_path / "out"),
    )


def test_sayro_partial_load_failure_clears_state_and_reloads(tmp_path, monkeypatch):
    """A failed load must not leave CUDA allocations/model state that
    prevents the next request from loading Sayro cleanly."""
    wrapper = _load_routeb_wrapper()
    fake_torch = _fake_torch()
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    good_model = types.SimpleNamespace(generate_custom_voice=lambda **kwargs: None)
    calls = []

    def load_model(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("CUDA out of memory while loading Sayro")
        return good_model

    monkeypatch.setattr(wrapper, "load_qwen_model", load_model)
    sayro = wrapper.SayroModel(_sayro_args(tmp_path))

    with pytest.raises(RuntimeError, match="out of memory"):
        sayro.load()
    assert sayro.model is None
    assert fake_torch.cuda.empty_cache.call_count == 1

    sayro.load()
    assert sayro.model is good_model
    assert len(calls) == 2


def test_sayro_invalid_model_is_discarded_and_reloaded(tmp_path, monkeypatch):
    """A returned checkpoint without the generation API is invalid, not a
    usable loaded model; the next request must retry from a clean state."""
    wrapper = _load_routeb_wrapper()
    fake_torch = _fake_torch()
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    good_model = types.SimpleNamespace(generate_custom_voice=lambda **kwargs: None)
    calls = []

    def load_model(*args, **kwargs):
        calls.append(1)
        return object() if len(calls) == 1 else good_model

    monkeypatch.setattr(wrapper, "load_qwen_model", load_model)
    sayro = wrapper.SayroModel(_sayro_args(tmp_path))

    with pytest.raises(RuntimeError, match="no generate_custom_voice"):
        sayro.load()
    assert sayro.model is None
    assert fake_torch.cuda.empty_cache.call_count == 1

    sayro.load()
    assert sayro.model is good_model
    assert len(calls) == 2


def test_sayro_generation_oom_resets_model_for_next_request(tmp_path, monkeypatch):
    """Generation OOM clears the resident model/cache and the following
    request reloads Sayro instead of reusing poisoned CUDA state."""
    wrapper = _load_routeb_wrapper()
    fake_torch = _fake_torch()
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    class OOMModel:
        def generate_custom_voice(self, **kwargs):
            raise RuntimeError("CUDA out of memory during generation")

    class GoodModel:
        def generate_custom_voice(self, **kwargs):
            return ([object()], 22050)

    oom_model = OOMModel()
    good_model = GoodModel()
    calls = []

    def load_model(*args, **kwargs):
        calls.append(1)
        return oom_model if len(calls) == 1 else good_model

    monkeypatch.setattr(wrapper, "load_qwen_model", load_model)
    sayro = wrapper.SayroModel(_sayro_args(tmp_path))

    with pytest.raises(RuntimeError, match="out of memory"):
        sayro.synthesize(["first"])
    assert sayro.model is None
    assert fake_torch.cuda.empty_cache.call_count == 1

    wavs, sr = sayro.synthesize(["second"])
    assert len(wavs) == 1
    assert sr == 22050
    assert sayro.model is good_model
    assert len(calls) == 2


def test_one_shot_sayro_failure_clears_cuda_cache(tmp_path, monkeypatch):
    """The non-daemon Sayro stage also cleans up when model loading fails."""
    wrapper = _load_routeb_wrapper()
    fake_torch = _fake_torch()
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setattr(
        wrapper, "load_qwen_model",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("CUDA out of memory in one-shot load")
        ),
    )
    args = _sayro_args(tmp_path)

    with pytest.raises(RuntimeError, match="one-shot load"):
        wrapper.stage_sayro_cli(args, [(1, "hello")])
    assert fake_torch.cuda.empty_cache.call_count == 1


def test_sayro_failure_keeps_seedvc_daemon_for_next_job(tmp_path, monkeypatch):
    """A Sayro failure is reported without stopping a healthy Seed-VC
    child; the next request can continue through that same daemon."""
    wrapper = _load_routeb_wrapper()
    target = tmp_path / "target.wav"
    target.write_bytes(b"target")
    vc_output = tmp_path / "vc.wav"
    vc_output.write_bytes(_silent_wav_bytes())

    class LiveProcess:
        def poll(self):
            return None

    class FakeSayro:
        def __init__(self, args):
            pass

    class FakeVC:
        instances = []

        def __init__(self, script_path, seedvc_dir, seedvc_python, target, args):
            self.proc = LiveProcess()
            self.target = Path(target).resolve()
            self.convert_calls = 0
            self.stop_calls = 0
            self.__class__.instances.append(self)

        def stop(self):
            self.stop_calls += 1

        def convert(self, source_wav, out_dir, job_id):
            self.convert_calls += 1
            return str(vc_output)

    sayro_calls = []

    def fake_sayro_to_wav(sayro, text, out_wav):
        sayro_calls.append(text)
        if len(sayro_calls) == 1:
            raise RuntimeError("CUDA out of memory during Sayro generation")

    monkeypatch.setattr(wrapper, "SayroModel", FakeSayro)
    monkeypatch.setattr(wrapper, "SeedVCDaemon", FakeVC)
    monkeypatch.setattr(wrapper, "_resolve_seedvc",
                        lambda args: ("v2", tmp_path / "inference_v2.py",
                                      tmp_path, sys.executable))
    monkeypatch.setattr(wrapper, "_resolve_target", lambda args: target)
    monkeypatch.setattr(wrapper, "_sayro_to_wav", fake_sayro_to_wav)
    monkeypatch.setattr(wrapper.atexit, "register", lambda fn: fn)
    monkeypatch.setattr(wrapper.signal, "signal", lambda *args: None)

    jobs = [
        {"id": "sayro-fail", "text": "first", "target": str(target),
         "work_dir": str(tmp_path / "job1")},
        {"id": "sayro-recover", "text": "second", "target": str(target),
         "work_dir": str(tmp_path / "job2")},
    ]
    stdin = io.StringIO("".join(json.dumps(job) + "\n" for job in jobs))
    stdout = io.BytesIO()
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", io.StringIO())

    wrapper.run_daemon(types.SimpleNamespace())

    messages = [json.loads(line) for line in
                stdout.getvalue().decode("utf-8").splitlines()
                if line.startswith("{")]
    assert messages[0]["ok"] is False
    assert messages[0]["id"] == "sayro-fail"
    assert messages[1]["ok"] is True
    assert messages[1]["id"] == "sayro-recover"
    assert len(FakeVC.instances) == 1
    assert FakeVC.instances[0].convert_calls == 1
    assert FakeVC.instances[0].stop_calls == 0
    assert len(sayro_calls) == 2


def _switch_daemon_stub(vc_env, stub, monkeypatch):
    monkeypatch.setattr(vc_env, "_resolve_sayro_script", lambda: stub)
    if vc_env._routeb_daemon is not None:
        vc_env._routeb_daemon.shutdown()
    vc_env._routeb_daemon = None


def test_daemon_death_during_inference_retries_same_job(vc_env, tmp_path, monkeypatch):
    """A child that exits after accepting a job is replaced once and the
    exact same JSON job id is submitted to the replacement."""
    ids = tmp_path / "death-job-ids.txt"
    stub = _make_stub(tmp_path / "death-once", die_once=True, record_ids=ids)
    _switch_daemon_stub(vc_env, stub, monkeypatch)
    out = tmp_path / "death-out"
    out.mkdir()

    wav = vc_env._synthesize_via_daemon("same job after death", out, timeout=15.0)

    assert wav == _silent_wav_bytes()
    submitted_ids = ids.read_text(encoding="utf-8").splitlines()
    assert len(submitted_ids) == 2
    assert submitted_ids[0] == submitted_ids[1]


def test_successful_same_job_retry_after_retryable_result(vc_env, tmp_path,
                                                          monkeypatch):
    """A retryable Seed-VC error after acceptance is retried once without
    changing the job id, and the second response is returned."""
    ids = tmp_path / "result-job-ids.txt"
    stub = _make_stub(tmp_path / "result-once", error_once=True, record_ids=ids)
    _switch_daemon_stub(vc_env, stub, monkeypatch)
    out = tmp_path / "result-out"
    out.mkdir()

    wav = vc_env._synthesize_via_daemon("same job after result error", out,
                                        timeout=15.0)

    assert wav == _silent_wav_bytes()
    submitted_ids = ids.read_text(encoding="utf-8").splitlines()
    assert len(submitted_ids) == 2
    assert submitted_ids[0] == submitted_ids[1]


def test_reader_ownership_across_restart():
    """Each stdout reader writes only to the queue belonging to its own
    pipe, even when a replacement reader is started immediately afterward."""
    from product.backend.services.voice_clone import RouteBDaemonClient

    client = RouteBDaemonClient()
    old_queue = queue.Queue()
    new_queue = queue.Queue()

    class _RestartPipe(io.BytesIO):
        def __init__(self, payload):
            super().__init__(payload)
            self.started = threading.Event()
            self.release = threading.Event()
            self._first_read = True

        def read(self, size=-1):
            if self._first_read:
                self._first_read = False
                self.started.set()
                assert self.release.wait(timeout=1.0)
            return super().read(size)

    old_stdout = _RestartPipe(b'{"id": "old", "ok": true}\n')
    new_stdout = io.BytesIO(b'{"id": "new", "ok": true}\n')
    old_thread = threading.Thread(
        target=client._drain_stdout,
        args=(object(), old_stdout, old_queue),
    )
    new_thread = threading.Thread(
        target=client._drain_stdout,
        args=(object(), new_stdout, new_queue),
    )

    old_thread.start()
    assert old_stdout.started.wait(timeout=1.0)
    # Replacement starts while the old reader is still attached to its
    # blocked pipe; the queues must remain independent.
    new_thread.start()
    new_thread.join(timeout=1.0)
    old_stdout.release.set()
    old_thread.join(timeout=1.0)

    assert not old_thread.is_alive()
    assert not new_thread.is_alive()
    assert old_queue.get_nowait()["data"]["id"] == "old"
    assert new_queue.get_nowait()["data"]["id"] == "new"
    assert old_queue.empty()
    assert new_queue.empty()
    assert old_stdout.closed
    assert new_stdout.closed


def test_shutdown_closes_pipes_and_joins_readers():
    """Shutdown closes every parent-side pipe, joins both readers within
    the bounded window, and is safe to call a second time."""
    from product.backend.services.voice_clone import RouteBDaemonClient

    client = RouteBDaemonClient()
    proc = mock.Mock()
    proc.pid = 12345
    proc.returncode = 0
    proc.poll.return_value = 0
    proc.stdin = io.BytesIO()
    proc.stdout = io.BytesIO(b"")
    proc.stderr = io.BytesIO(b"")
    responses = queue.Queue()
    stderr_tail = []
    client._proc = proc
    client._responses = responses
    client._stderr_thread = threading.Thread(
        target=client._drain_stderr,
        args=(proc, proc.stderr, stderr_tail),
    )
    client._stdout_thread = threading.Thread(
        target=client._drain_stdout,
        args=(proc, proc.stdout, responses),
    )
    client._stderr_thread.start()
    client._stdout_thread.start()

    client._kill_tree()
    client._kill_tree()

    assert client._proc is None
    assert client._stdout_thread is None
    assert client._stderr_thread is None
    assert proc.stdin.closed
    assert proc.stdout.closed
    assert proc.stderr.closed


def test_retry_failure_falls_back_to_one_shot(vc_env, tmp_path, monkeypatch):
    """If both the original daemon job and its one retry die, the public
    synthesis path uses the existing one-shot fallback exactly as before."""
    stub = _make_stub(tmp_path / "die-always", die_on_job=True)
    _switch_daemon_stub(vc_env, stub, monkeypatch)
    monkeypatch.setattr(vc_env.settings, "local_clone_timeout_s", 10)
    fake_wav = tmp_path / "fallback.wav"
    fake_wav.write_bytes(_silent_wav_bytes())
    calls = []
    monkeypatch.setattr(
        vc_env,
        "_run_subprocess",
        lambda cmd, timeout, cwd=None: calls.append((cmd, timeout, cwd)) or {
            "timings": {}, "markers": {}, "total_s": 1.0,
        },
    )
    monkeypatch.setattr(vc_env, "_find_converted_output",
                        lambda out_dir, stem: fake_wav)

    data = vc_env.synthesize_local_clone("fallback after retry", "uz")

    assert data == _silent_wav_bytes()
    assert len(calls) == 1


def test_daemon_error_propagates(vc_env, tmp_path, monkeypatch):
    """If the daemon returns ok:false, the client must raise so the caller
    can fall back to the one-shot path."""
    # Replace stub with one that fails on its first (and only) job.
    stub = _make_stub(tmp_path / "bad", fail_n=10**6)
    monkeypatch.setattr(vc_env, "_resolve_sayro_script", lambda: stub)
    # Recreate daemon so it picks up the new stub.
    if vc_env._routeb_daemon is not None:
        vc_env._routeb_daemon.shutdown()
    vc_env._routeb_daemon = None
    out = tmp_path / "out2"; out.mkdir()
    with pytest.raises(RuntimeError, match="stub transient error"):
        vc_env._synthesize_via_daemon("Salom", out, timeout=10.0)


def test_daemon_disable_when_wrapper_lacks_flag(tmp_path, monkeypatch):
    """An older vendored wrapper without --daemon support must auto-disable
    the daemon path so we don't spawn a child that exits with argparse
    errors."""
    from product.backend.services import voice_clone as vc2
    # Fresh state.
    vc2._routeb_daemon = None
    vc2._daemon_disabled = False
    old_wrapper = tmp_path / "old_wrapper.py"
    old_wrapper.write_text("# no daemon flag here\nprint('hi')\n", encoding="utf-8")
    monkeypatch.setattr(vc2, "_resolve_sayro_script", lambda: old_wrapper)
    assert vc2._get_daemon() is None
    assert vc2._daemon_disabled is True


def test_synthesize_local_clone_falls_back_on_daemon_failure(tmp_path, monkeypatch):
    """When the daemon path raises, synthesis must still succeed via the
    one-shot subprocess. We monkeypatch _run_subprocess + _find_converted_output
    so the one-shot path returns a tiny valid WAV without touching the real
    wrapper."""
    from product.backend.services import voice_clone as vc2
    vc2._routeb_daemon = None
    vc2._daemon_disabled = False
    # Force daemon path to always fail by pointing at a non-executable script path.
    missing = tmp_path / "nope.py"
    # But _get_daemon sniffs source for --daemon; write a file containing
    # that string so the daemon is attempted (and will fail to spawn).
    missing.write_text("parser.add_argument('--daemon', ...)\n", encoding="utf-8")
    monkeypatch.setattr(vc2, "_resolve_sayro_script", lambda: missing)
    monkeypatch.setattr(vc2, "_resolve_sayro_python", lambda _p: sys.executable)
    monkeypatch.setattr(vc2, "_resolve_seedvc_dir", lambda: tmp_path)
    monkeypatch.setattr(vc2, "_resolve_seedvc_python", lambda _d: sys.executable)
    monkeypatch.setattr(vc2, "_resolve_wrapper_cwd", lambda _p: str(tmp_path))
    (tmp_path / "ref.wav").write_bytes(b"\x00" * 16)
    monkeypatch.setattr(vc2.settings, "seedvc_reference_wav", str(tmp_path / "ref.wav"))
    monkeypatch.setattr(vc2.settings, "route_b_diffusion_steps", 15)
    monkeypatch.setattr(vc2.settings, "route_b_length_adjust", 1.0)
    monkeypatch.setattr(vc2.settings, "route_b_intelligibility", 0.8)
    monkeypatch.setattr(vc2.settings, "route_b_similarity", 0.8)
    monkeypatch.setattr(vc2.settings, "route_b_extra_args", "")
    monkeypatch.setattr(vc2.settings, "local_clone_timeout_s", 10)
    monkeypatch.setattr(vc2.settings, "seedvc_version", "v2")
    # Monkeypatch the one-shot path: _run_subprocess pretends to have run
    # successfully, and _find_converted_output returns a valid wav file.
    fake_wav = tmp_path / "fake.wav"
    fake_wav.write_bytes(_silent_wav_bytes())
    monkeypatch.setattr(vc2, "_run_subprocess",
                        lambda cmd, timeout, cwd=None: {"timings": {}, "markers": {}, "total_s": 1.0})
    monkeypatch.setattr(vc2, "_find_converted_output", lambda out_dir, stem: fake_wav)
    # synthesize_local_clone will try daemon -> spawn fails -> fall back to
    # the (monkeypatched) one-shot path -> return fake wav bytes.
    data = vc2.synthesize_local_clone("Salom dunyo", "uz")
    assert data[:4] == b"RIFF"


def test_validate_wav_accepts_pcm16():
    from product.backend.services import voice_clone as vc2
    vc2._validate_wav_bytes(_silent_wav_bytes())  # should not raise


# ---------------------------------------------------------------- P1-1 tests
# P1-1: stray non-JSON lines on daemon stdout must NOT break the client's
# JSONL parser; it must skip them and return the eventual JSON result.
# (The wrapper was patched to route its own "[vc]" chatter to stderr; this
# test hardens the client against any future regression where a third-party
# library leaks log lines onto stdout.)

def test_daemon_tolerates_nonjson_chatter_on_stdout(vc_env, tmp_path, monkeypatch):
    """The stub emits 5 log-like lines (one containing a stray '{' char)
    BEFORE the JSON result on every job. The client must skip them and
    return the WAV instead of raising 'bad json' / timeout."""
    stub = _make_stub(tmp_path / "chattery", chatter_lines=5)
    monkeypatch.setattr(vc_env, "_resolve_sayro_script", lambda: stub)
    if vc_env._routeb_daemon is not None:
        vc_env._routeb_daemon.shutdown()
    vc_env._routeb_daemon = None
    out = tmp_path / "out_c"; out.mkdir()
    wav = vc_env._synthesize_via_daemon("Salom", out, timeout=15.0)
    assert wav[:4] == b"RIFF"
    # Second call must also succeed (no parser state leak between jobs).
    out2 = tmp_path / "out_c2"; out2.mkdir()
    wav2 = vc_env._synthesize_via_daemon("Dunyo", out2, timeout=15.0)
    assert wav2[:4] == b"RIFF"


def test_p1_1_wrapper_routes_seedvc_chatter_to_stderr():
    """Static regression guard for P1-1: the wrapper's SeedVCDaemon stdout
    drain must route non-JSON '[vc]' lines to stderr, NOT stdout, so they
    never interleave with the wrapper's JSONL response stream. If anyone
    accidentally changes `file=sys.stderr` back to the default stdout,
    this test will fail."""
    wrapper = Path(__file__).resolve().parents[3] / \
        "product/backend/services/routeb/b_sayro_then_seedvc.py"
    src = wrapper.read_text(encoding="utf-8")
    # The chatter line in _drain_stdout must go to stderr.
    assert 'print(f"[vc] {line}", file=sys.stderr, flush=True)' in src, (
        "P1-1 REGRESSION: SeedVC non-JSON '[vc]' chatter must be written "
        "to stderr, not stdout, to avoid corrupting the JSONL protocol."
    )
    # Daemon mode also redirects the wrapper's text stdout globally, while
    # retaining the original binary handle for JSON responses. This covers
    # Sayro/common/imported logs in addition to the Seed-VC drain above.
    assert '_DAEMON_STDOUT = getattr(sys.stdout, "buffer", sys.stdout)' in src
    assert 'sys.stdout = sys.stderr' in src
    assert 'out = _DAEMON_STDOUT or sys.stdout.buffer' in src
    # Defensive: make sure no other print([vc]... goes to stdout in
    # _drain_stdout. Scan the relevant block:
    import re
    drain_idx = src.find("def _drain_stdout")
    assert drain_idx > 0, "_drain_stdout function not found in wrapper"
    next_def = src.find("\n    def ", drain_idx + 1)
    if next_def == -1:
        next_def = len(src)
    block = src[drain_idx:next_def]
    # Every [vc]-prefixed print in this function must explicitly target
    # stderr. Check the complete call text so a multiline print() (such as
    # the bad-JSON diagnostic) is not falsely flagged by a line-by-line scan.
    for match in re.finditer(r'print\(f?["\']\[vc][\s\S]*?\)', block):
        call = match.group(0)
        assert "file=sys.stderr" in call, (
            f"P1-1 REGRESSION: [vc] print lacks file=sys.stderr: {call}"
        )


# ---------------------------------------------------------------- P1-2 tests
# P1-2: on Windows the pipe-attached stdin defaults to cp1252 which mutes
# Uzbek diacritics (Oʻ, Gʻ, ʻ). We force UTF-8 via PYTHONIOENCODING on the
# child env AND reconfigure stdin in the wrapper. Test (a) the env var is
# present, and (b) end-to-end the diacritics survive the stdin pipe.

def test_p1_2_child_env_forces_utf8():
    from product.backend.services import voice_clone as vc2
    assert vc2._CHILD_ENV_HARDEN.get("PYTHONIOENCODING", "").lower() == "utf-8", (
        "P1-2 REGRESSION: _CHILD_ENV_HARDEN must set PYTHONIOENCODING=utf-8 "
        "so the wrapper/daemon stdin pipe uses UTF-8 on Windows (cp1252 "
        "silently mangles Uzbek diacritics)."
    )


def test_daemon_utf8_diacritics_roundtrip(vc_env, tmp_path, monkeypatch):
    """Send Uzbek text containing Oʻ/Gʻ/ʻ diacritics through the stub,
    which echoes the text back and reports whether diacritics survived
    JSONL decode. Failure here means the pipe encoding mangled text
    before the daemon even saw it (P1-2 on Windows)."""
    stub = _make_stub(tmp_path / "utf8", echo_text=True)
    monkeypatch.setattr(vc_env, "_resolve_sayro_script", lambda: stub)
    if vc_env._routeb_daemon is not None:
        vc_env._routeb_daemon.shutdown()
    vc_env._routeb_daemon = None
    out = tmp_path / "out_u"; out.mkdir()
    # Uzbek phrase heavy with Oʻ / Gʻ / ʻ (turned comma, the character
    # that breaks on cp1252).
    uz_text = "Bugun Oʻzbekistonda Gʻalaba kuni. Men oʻzimni yaxshi his qilyapman."
    wav = vc_env._synthesize_via_daemon(uz_text, out, timeout=15.0)
    assert wav[:4] == b"RIFF"


def test_p1_2_wrapper_reconfigures_stdin_to_utf8():
    """Static regression guard: the wrapper's run_daemon() must call
    sys.stdin.reconfigure(encoding='utf-8', ...)."""
    wrapper = Path(__file__).resolve().parents[3] / \
        "product/backend/services/routeb/b_sayro_then_seedvc.py"
    src = wrapper.read_text(encoding="utf-8")
    assert 'sys.stdin.reconfigure(encoding="utf-8"' in src, (
        "P1-2 REGRESSION: wrapper run_daemon must reconfigure stdin to "
        "UTF-8, otherwise Windows cp1252 stdin silently mangle Uzbek."
    )
