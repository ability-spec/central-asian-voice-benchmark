"""Exercise real IPC, CLI, cache lifecycle and cleanup without GPU models."""
import json
import os
from pathlib import Path
import sys

import pytest

from product.backend.config import settings
from product.backend.services import voice_clone
from product.backend.services.route_b_worker import RouteBWorker

ROUTEB = voice_clone._VENDORED_WRAPPER.parent


@pytest.fixture
def worker_setup(tmp_path, monkeypatch):
    seed = tmp_path / 'seed vc'
    seed.mkdir()
    (seed / 'inference_v2.py').write_text('''import json, sys
from pathlib import Path
args = sys.argv[1:]
items = json.loads(Path(args[args.index('--source-list')+1]).read_text())
for item in items:
    out = Path(item['output'])
    out.mkdir(parents=True, exist_ok=True)
    (out/'result.wav').write_bytes(Path(item['source']).read_bytes())
''')
    runner = tmp_path / 'wrapper.py'
    runner.write_text(f'''import sys, types, json, wave
from pathlib import Path
sys.path.insert(0, {str(ROUTEB)!r})
import b_sayro_then_seedvc as wrapper
import sayro_cache
log = Path({str(tmp_path / 'events.jsonl')!r})
def event(value):
    with log.open('a') as f: f.write(json.dumps(value)+'\\n')
class Module:
    def __init__(self, name): self.name, self.device = name, 'cuda:0'
    def to(self, device):
        self.device = device
        event([self.name, device])
        return self
class Model:
    def __init__(self):
        self.model = Module('sayro')
        self.model.speech_tokenizer = types.SimpleNamespace(model=Module('tokenizer'), device='cuda:0')
        self.device = 'cuda:0'
    def generate_custom_voice(self, text, **kwargs):
        assert self.model.device == self.device == 'cuda:0'
        assert self.model.speech_tokenizer.model.device == self.model.speech_tokenizer.device == 'cuda:0'
        event(['generate', text])
        return [[0.1] for t in text], 24000
def load(*args):
    event(['load', list(args)])
    return Model()
sayro_cache.load_qwen_model = load
wrapper.load_qwen_model = load
def write(path, wav, sr):
    with wave.open(str(path), 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(sr)
        f.writeframes(b'\\x01\\x00'*100)
wrapper.write_wav = write
sys.modules['torch'] = types.SimpleNamespace(device=lambda x:x, cuda=types.SimpleNamespace(
    empty_cache=lambda: None, max_memory_allocated=lambda: 0))
raise SystemExit(wrapper.main())
''')
    reference = tmp_path / 'reference.wav'
    reference.write_bytes(b'not read by the recording stub')
    sentences = tmp_path / 'sentences.txt'
    sentences.write_text('1. Salom, O‘zbekiston!\n', encoding='utf-8')
    for key, value in dict(sayro_script=str(runner), sayro_python=sys.executable,
                           seedvc_dir=str(seed), seedvc_python=sys.executable,
                           seedvc_reference_wav=str(reference), seedvc_version='v2',
                           route_b_extra_args='', route_b_persistent_sayro=True,
                           sayro_voice_lab_dir='', local_clone_timeout_s=10).items():
        monkeypatch.setattr(settings, key, value)
    worker = RouteBWorker()
    yield worker, sentences, tmp_path
    worker.close()


def run(worker, sentences, tmp, name='out'):
    cmd = voice_clone._build_route_b_cmd(sentences, tmp / name)
    return worker.run(cmd, 10, str(tmp), voice_clone._build_child_env(),
                      voice_clone._parse_wrapper_markers)


def test_two_requests_reuse_model_and_move_tokenizer(worker_setup):
    worker, sentences, tmp = worker_setup
    first = run(worker, sentences, tmp, 'first')
    pid = worker.proc.pid
    sentences.write_text('1. Ikkinchi gap.\n', encoding='utf-8')
    second = run(worker, sentences, tmp, 'second')
    assert worker.proc.pid == pid
    assert first['markers']['sayro_cache'] == 'miss'
    assert second['markers']['sayro_cache'] == 'hit'
    events = [json.loads(line) for line in (tmp / 'events.jsonl').read_text().splitlines()]
    assert sum(e[0] == 'load' for e in events) == 1
    assert [e[1] for e in events if e[0] == 'generate'] == [['Salom, O‘zbekiston!'], ['Ikkinchi gap.']]
    assert [e for e in events if e[0] == 'tokenizer'] == [
        ['tokenizer', 'cpu'], ['tokenizer', 'cuda:0'], ['tokenizer', 'cpu']]
    for name in ('first', 'second'):
        voice_clone._validate_wav_bytes((tmp / name / 'b_sayro_vc/t01.wav').read_bytes())
    assert 'sayro_generation_s' in second['timings']
    assert 'sayro_offload_s' in second['timings']
    assert 'seedvc_total_s' in second['timings']


def test_model_config_change_invalidates_cache(worker_setup, monkeypatch):
    worker, sentences, tmp = worker_setup
    run(worker, sentences, tmp, 'first')
    monkeypatch.setattr(settings, 'route_b_extra_args', '--dtype float32')
    result = run(worker, sentences, tmp, 'second')
    assert result['markers']['sayro_cache'] == 'miss'
    loads = [json.loads(s) for s in (tmp/'events.jsonl').read_text().splitlines() if '"load"' in s]
    assert len(loads) == 2
    assert loads[-1][1][2] == 'float32'


def test_failed_job_clears_worker_then_next_request_recovers(worker_setup, monkeypatch):
    worker, sentences, tmp = worker_setup
    monkeypatch.setattr(settings, 'seedvc_reference_wav', str(tmp/'missing.wav'))
    with pytest.raises(RuntimeError, match='target ref not found'):
        run(worker, sentences, tmp)
    assert worker.proc is None
    monkeypatch.setattr(settings, 'seedvc_reference_wav', str(tmp/'reference.wav'))
    assert run(worker, sentences, tmp)['markers']['sayro_cache'] == 'miss'


def test_backend_dispatch_and_shutdown(worker_setup, monkeypatch):
    worker, _, tmp = worker_setup
    monkeypatch.setattr(voice_clone, '_route_b_worker', worker)
    monkeypatch.setattr(voice_clone, '_VENDORED_WRAPPER', Path(settings.sayro_script))
    for text in ('Birinchi gap.', 'Ikkinchi gap.'):
        voice_clone._validate_wav_bytes(voice_clone.synthesize_local_clone(text, 'uz'))
    proc = worker.proc
    assert proc.poll() is None
    voice_clone.close_route_b_worker()
    assert proc.poll() is not None
    assert worker.proc is None


def test_disabled_mode_uses_original_cli(worker_setup, monkeypatch):
    worker, _, tmp = worker_setup
    monkeypatch.setattr(voice_clone, '_route_b_worker', worker)
    monkeypatch.setattr(voice_clone, '_VENDORED_WRAPPER', Path(settings.sayro_script))
    monkeypatch.setattr(settings, 'route_b_persistent_sayro', False)
    voice_clone._validate_wav_bytes(voice_clone.synthesize_local_clone('Salom.', 'uz'))
    assert worker.proc is None


def test_external_wrapper_keeps_original_cli(worker_setup, monkeypatch):
    worker, _, _ = worker_setup
    monkeypatch.setattr(voice_clone, '_route_b_worker', worker)
    voice_clone._validate_wav_bytes(voice_clone.synthesize_local_clone('Salom.', 'uz'))
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
