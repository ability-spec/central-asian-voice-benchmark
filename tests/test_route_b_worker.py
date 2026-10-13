"""CPU coverage for retained cache/IPC helpers, separate from production daemon.

The active backend uses RouteBDaemonClient, covered in test_routeb_daemon.py.
These helpers remain available to the optional offload adapter; do not invent
removed Settings fields or claim this is the backend's dispatch path.
"""
import importlib
import json
import os
from pathlib import Path
import sys
import types

import pytest

from product.backend.services import voice_clone
from product.backend.services.route_b_worker import RouteBWorker

ROUTEB = voice_clone._VENDORED_WRAPPER.parent


@pytest.fixture
def cache_setup(monkeypatch):
    monkeypatch.syspath_prepend(str(ROUTEB))
    cache_module = importlib.import_module("sayro_cache")
    events = []

    class Module:
        def __init__(self, name):
            self.name, self.device = name, "cuda:0"
        def to(self, device):
            self.device = device
            events.append((self.name, device))
            return self

    class Model:
        def __init__(self):
            self.model = Module("sayro")
            self.model.speech_tokenizer = types.SimpleNamespace(
                model=Module("tokenizer"), device="cuda:0")
            self.device = "cuda:0"

    def load(*args):
        events.append(("load", args))
        return Model()

    monkeypatch.setattr(cache_module, "load_qwen_model", load)
    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(
        device=str, cuda=types.SimpleNamespace(empty_cache=lambda: None)))
    cache = cache_module.SayroCache()
    args = types.SimpleNamespace(device="cuda:0", dtype="bfloat16", attn="sdpa")
    yield cache, args, events
    cache.clear()


def test_two_requests_reuse_model_and_move_tokenizer(cache_setup):
    cache, args, events = cache_setup
    first = cache.acquire(args)
    cache.park()
    assert first.device == first.model.device == "cpu"
    assert first.model.speech_tokenizer.device == "cpu"
    assert cache.acquire(args) is first
    assert first.device == first.model.speech_tokenizer.model.device == "cuda:0"
    cache.park()
    assert sum(e[0] == "load" for e in events) == 1
    assert [e for e in events if e[0] == "tokenizer"] == [
        ("tokenizer", "cpu"), ("tokenizer", "cuda:0"), ("tokenizer", "cpu")]


def test_model_config_change_invalidates_cache(cache_setup):
    cache, args, events = cache_setup
    first = cache.acquire(args)
    args.dtype = "float32"
    assert cache.acquire(args) is not first
    loads = [e[1] for e in events if e[0] == "load"]
    assert len(loads) == 2
    assert loads[-1][2] == "float32"


def test_clear_closes_child_and_next_acquire_reloads(cache_setup):
    cache, args, events = cache_setup
    first = cache.acquire(args)
    closed = []
    cache.seed_worker = types.SimpleNamespace(close=lambda: closed.append(True))
    cache.clear()
    assert closed == [True]
    assert cache.model is cache.key is cache.seed_worker is None
    assert cache.acquire(args) is not first
    assert sum(e[0] == "load" for e in events) == 2


@pytest.mark.parametrize("reply", [
    {"id": "wrong", "ok": True},
    {"ok": False, "error": "fixture failure"},
])
def test_invalid_reply_discards_worker(tmp_path, reply):
    script = tmp_path / "invalid.py"
    script.write_text("import sys, json\nfor line in sys.stdin:\n"
                      "    req = json.loads(line)\n"
                      f"    reply = {reply!r}\n"
                      "    reply.setdefault('id', req['id'])\n"
                      "    print('BIROVOZ_RESULT ' + json.dumps(reply), flush=True)\n")
    worker = RouteBWorker()
    with pytest.raises(RuntimeError, match="ID mismatch|fixture failure"):
        worker.run([sys.executable, str(script)], 2, str(tmp_path),
                   voice_clone._build_child_env(), lambda *a: None)
    assert worker.proc is None


def test_timeout_kills_worker_and_descendant(tmp_path):
    script = tmp_path/'hang.py'
    pidfile = tmp_path/'child.pid'
    script.write_text('''import subprocess, sys, time
from pathlib import Path
for line in sys.stdin:
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])
    Path('child.pid').write_text(str(child.pid))
    time.sleep(120)
''')
    worker = RouteBWorker()
    try:
        with pytest.raises(RuntimeError, match='timed out'):
            worker.run([sys.executable, str(script)], 1, str(tmp_path),
                       voice_clone._build_child_env(), lambda *a:None)
        assert worker.proc is None
        assert pidfile.exists()
        if os.name != 'nt':
            # An exited grandchild can briefly remain a zombie until reaped.
            status = Path('/proc')/pidfile.read_text()/'stat'
            assert not status.exists() or status.read_text().split()[2] == 'Z'
    finally:
        worker.close()


def test_crashed_worker_reports_stderr_and_restarts(tmp_path):
    script = tmp_path/'crash.py'
    script.write_text("import sys\nprint('fixture failure', file=sys.stderr, flush=True)\nraise SystemExit(3)\n")
    worker = RouteBWorker()
    for _ in range(2):
        with pytest.raises(RuntimeError, match='exited.*fixture failure'):
            worker.run([sys.executable, str(script)], 2, str(tmp_path),
                       voice_clone._build_child_env(), lambda *a:None)
        assert worker.proc is None
