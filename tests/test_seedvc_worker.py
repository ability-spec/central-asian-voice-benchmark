"""Run the supplied Seed-VC CLI and both real worker protocols with fake models.

The fixture is the project owner's inference_v2.py snapshot. Its main(), model
loading orchestration, argument namespace and WAV save path execute unchanged.
"""
import json
import os
from pathlib import Path
import shutil

import pytest

from product.backend.config import settings
from product.backend.services import voice_clone
from test_route_b_worker import worker_setup  # noqa: F401


@pytest.fixture
def seed_setup(worker_setup, monkeypatch):
    worker, sentences, tmp = worker_setup
    seed = tmp / 'seed vc'
    shutil.copyfile(Path(__file__).parent/'fixtures/seedvc_inference_v2.py', seed/'inference_v2.py')
    (seed/'configs/v2').mkdir(parents=True)
    (seed/'configs/v2/vc_wrapper.yaml').write_text('{}')
    (seed/'torch.py').write_text('''from fake_models import Tensor
class Cuda:
    def is_available(self): return True
    def empty_cache(self): pass
cuda = Cuda()
device = str
float16 = 'float16'
''')
    (seed/'yaml.py').write_text('def safe_load(file):\n    file.close()\n    return {}\n')
    (seed/'omegaconf.py').write_text('DictConfig = dict\n')
    (seed/'hydra').mkdir()
    (seed/'hydra/__init__.py').write_text('')
    (seed/'hydra/utils.py').write_text('from fake_models import Model\ndef instantiate(cfg): return Model()\n')
    (seed/'modules').mkdir()
    (seed/'modules/__init__.py').write_text('')
    (seed/'modules/commons.py').write_text("def str2bool(value): return value.lower() == 'true'\n")
    (seed/'soundfile.py').write_text('''import wave
def write(path, audio, sr):
    with wave.open(str(path), 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(sr)
        f.writeframes(b'\\x01\\x00'*100)
''')
    (seed/'fake_models.py').write_text('''import json, os
from pathlib import Path

def event(value):
    with Path('seed-events.jsonl').open('a') as f: f.write(json.dumps(value)+'\\n')

class Tensor:
    def __init__(self, device): self.device = device
    def to(self, device): return Tensor(device)

class Model:
    def __init__(self):
        self.device = 'cpu'
        self.features = {'voice': [Tensor('cuda')]}
        self.features['alias'] = self.features['voice'][0]
        self.rotary_cache = (Tensor('cuda'),)
        event(['load', os.getpid()])
    def load_checkpoints(self, **kw): pass
    def eval(self): pass
    def setup_ar_caches(self, **kw): self.mask = Tensor(kw['device'])
    def modules(self): return [self]
    def to(self, device):
        if device == 'cpu' and Path('fail-offload').exists():
            raise RuntimeError('fixture offload failure')
        self.device = device
        Path('seed-device.txt').write_text(device)
        event(['move', device])
        return self
    def convert_voice_with_streaming(self, **kw):
        assert self.device == kw['device'] == 'cuda'
        assert self.mask.device == self.rotary_cache[0].device == 'cuda'
        assert self.features['voice'][0].device == 'cuda'
        assert self.features['alias'] is self.features['voice'][0]
        # The other worker must already have parked Sayro before we convert.
        events = [json.loads(s) for s in Path('../events.jsonl').read_text().splitlines()]
        assert [e for e in events if e[0] == 'sayro'][-1] == ['sayro', 'cpu']
        event(['convert', {k:v for k,v in kw.items() if k not in ('source_audio_path','target_audio_path')}])
        yield None, (24000, [0.1]*100)
''')
    runner = tmp/'wrapper.py'
    source = runner.read_text()
    source = source.replace("        event(['generate', text])", """        seed_device = Path('seed vc/seed-device.txt')
        assert not seed_device.exists() or seed_device.read_text() == 'cpu'
        event(['generate', text])""")
    runner.write_text(source)
    monkeypatch.setattr(voice_clone, '_route_b_worker', worker)
    monkeypatch.setattr(voice_clone, '_VENDORED_WRAPPER', runner)
    monkeypatch.setattr(settings, 'route_b_persistent_seedvc', True)
    monkeypatch.setattr(settings, 'route_b_diffusion_steps', 15)
    monkeypatch.setattr(settings, 'route_b_intelligibility', 0.8)
    monkeypatch.setattr(settings, 'route_b_similarity', 0.8)
    return worker, sentences, tmp, seed


def test_two_requests_reuse_both_models_and_preserve_quality_args(seed_setup, caplog):
    worker, sentences, tmp, seed = seed_setup
    import logging
    caplog.set_level(logging.INFO)
    for text in ('Salom dunyo.', 'Yaxshimisiz?'):
        data = voice_clone.synthesize_local_clone(text, 'uz')
        voice_clone._validate_wav_bytes(data)
        assert (seed/'seed-device.txt').read_text() == 'cpu'
    events = [json.loads(s) for s in (seed/'seed-events.jsonl').read_text().splitlines()]
    assert sum(e[0] == 'load' for e in events) == 1
    assert [e[1] for e in events if e[0] == 'move'] == ['cuda', 'cpu', 'cuda', 'cpu']
    for _, args in (e for e in events if e[0] == 'convert'):
        assert args == dict(diffusion_steps=15, length_adjust=1.0,
                            intelligebility_cfg_rate=0.8, similarity_cfg_rate=0.8,
                            top_p=0.9, temperature=1.0, repetition_penalty=1.0,
                            convert_style=False, anonymization_only=False,
                            device='cuda', dtype='float16', stream_output=True)
    assert 'seedvc_cache=miss' in caplog.text
    assert 'seedvc_cache=hit' in caplog.text
    assert 'seedvc_conversion_s=' in caplog.text
    assert 'seedvc_offload_s=' in caplog.text
    assert 'sayro_cache=hit' in caplog.text
    voice_clone.close_route_b_worker()
    assert worker.proc is None
    if os.name != 'nt':
        pid = next(e[1] for e in events if e[0] == 'load')
        stat = Path(f'/proc/{pid}/stat')
        assert not stat.exists() or stat.read_text().split()[2] == 'Z'


def test_offload_failure_discards_both_workers(seed_setup):
    worker, _, tmp, seed = seed_setup
    (seed/'fail-offload').touch()
    with pytest.raises(RuntimeError, match='fixture offload failure'):
        voice_clone.synthesize_local_clone('Salom.', 'uz')
    assert worker.proc is None
    # Clear only the test's simulated hardware failure and cross-process marker.
    (seed/'fail-offload').unlink()
    (seed/'seed-device.txt').unlink()
    voice_clone._validate_wav_bytes(voice_clone.synthesize_local_clone('Salom.', 'uz'))
    events = [json.loads(s) for s in (seed/'seed-events.jsonl').read_text().splitlines()]
    assert sum(e[0] == 'load' for e in events) == 2


def test_adapter_invalidates_changed_script(seed_setup):
    worker, _, _, seed = seed_setup
    voice_clone.synthesize_local_clone('Salom.', 'uz')
    script = seed/'inference_v2.py'
    script.write_text(script.read_text()+'\n# new revision\n')
    voice_clone.synthesize_local_clone('Salom.', 'uz')
    events = [json.loads(s) for s in (seed/'seed-events.jsonl').read_text().splitlines()]
    assert sum(e[0] == 'load' for e in events) == 2


def test_seed_conversion_timeout_discards_process_tree(seed_setup, monkeypatch):
    worker, _, _, seed = seed_setup
    voice_clone.synthesize_local_clone('Salom.', 'uz')
    # Trigger a long conversion only after the first job loaded the models.
    script = seed/'inference_v2.py'
    script.write_text(script.read_text().replace(
        'def main(args):', 'def main(args):\n    time.sleep(120)'))
    monkeypatch.setattr(settings, 'local_clone_timeout_s', 1)
    with pytest.raises(RuntimeError, match='timed out'):
        voice_clone.synthesize_local_clone('Salom.', 'uz')
    assert worker.proc is None
    if os.name != 'nt':
        events = [json.loads(s) for s in (seed/'seed-events.jsonl').read_text().splitlines()]
        for pid in {e[1] for e in events if e[0] == 'load'}:
            stat = Path(f'/proc/{pid}/stat')
            assert not stat.exists() or stat.read_text().split()[2] == 'Z'


def test_quality_setting_change_reuses_seed_model(seed_setup, monkeypatch):
    _, _, _, seed = seed_setup
    voice_clone.synthesize_local_clone('Salom.', 'uz')
    monkeypatch.setattr(settings, 'route_b_diffusion_steps', 12)
    voice_clone.synthesize_local_clone('Salom.', 'uz')
    events = [json.loads(s) for s in (seed/'seed-events.jsonl').read_text().splitlines()]
    assert sum(e[0] == 'load' for e in events) == 1
    assert [e[1]['diffusion_steps'] for e in events if e[0] == 'convert'] == [15, 12]
