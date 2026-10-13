"""Run the supplied Seed-VC CLI and the retained offload adapter protocol with fake models.

The fixture is the project owner's inference_v2.py snapshot. Its main(), model
loading orchestration, argument namespace and WAV save path execute unchanged.
"""
import json
import os
from pathlib import Path
import shutil
import sys

import pytest

from product.backend.services import voice_clone
from product.backend.services.route_b_worker import RouteBWorker

ROUTEB = voice_clone._VENDORED_WRAPPER.parent


@pytest.fixture
def seed_setup(tmp_path):
    tmp = tmp_path
    worker = RouteBWorker()
    seed = tmp / 'seed vc'
    seed.mkdir()
    (tmp / 'reference.wav').write_bytes(b'reference stub')
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
        event(['convert', {k:v for k,v in kw.items() if k not in ('source_audio_path','target_audio_path')}])
        yield None, (24000, [0.1]*100)
''')
    source = seed / 'source.wav'
    source.write_bytes(b'source stub')
    items = seed / 'sources.json'
    items.write_text(json.dumps([{'source': str(source), 'output': str(seed / 'out')}]))
    cmd = [sys.executable, str(ROUTEB / 'seedvc_worker.py'),
           '--inference-script', str(seed / 'inference_v2.py'),
           '--source-list', str(items), '--target', str(tmp / 'reference.wav'),
           '--diffusion-steps', '15', '--length-adjust', '1.0',
           '--intelligibility-cfg-rate', '0.8', '--similarity-cfg-rate', '0.8']
    yield worker, cmd, tmp, seed
    worker.close()


def run_adapter(worker, cmd, seed, timeout=10):
    result = worker.run(cmd, timeout, str(seed), voice_clone._build_child_env(),
                        voice_clone._parse_wrapper_markers)
    paths = list((seed / 'out').glob('*.wav'))
    assert paths, 'Adapter acknowledged success without an output WAV'
    for path in paths:
        voice_clone._validate_wav_bytes(path.read_bytes())
    return result


def test_two_requests_reuse_adapter_model_and_preserve_quality_args(seed_setup, caplog):
    worker, cmd, tmp, seed = seed_setup
    import logging
    caplog.set_level(logging.INFO)
    for _ in range(2):
        run_adapter(worker, cmd, seed)
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
    worker.close()
    assert worker.proc is None
    if os.name != 'nt':
        pid = next(e[1] for e in events if e[0] == 'load')
        stat = Path(f'/proc/{pid}/stat')
        assert not stat.exists() or stat.read_text().split()[2] == 'Z'


def test_offload_failure_discards_adapter_worker(seed_setup):
    worker, cmd, tmp, seed = seed_setup
    (seed/'fail-offload').touch()
    with pytest.raises(RuntimeError, match='fixture offload failure'):
        run_adapter(worker, cmd, seed)
    assert worker.proc is None
    # Clear only the test's simulated hardware failure and cross-process marker.
    (seed/'fail-offload').unlink()
    (seed/'seed-device.txt').unlink()
    run_adapter(worker, cmd, seed)
    events = [json.loads(s) for s in (seed/'seed-events.jsonl').read_text().splitlines()]
    assert sum(e[0] == 'load' for e in events) == 2


def test_adapter_invalidates_changed_script(seed_setup):
    worker, cmd, _, seed = seed_setup
    run_adapter(worker, cmd, seed)
    script = seed/'inference_v2.py'
    script.write_text(script.read_text()+'\n# new revision\n')
    run_adapter(worker, cmd, seed)
    events = [json.loads(s) for s in (seed/'seed-events.jsonl').read_text().splitlines()]
    assert sum(e[0] == 'load' for e in events) == 2


def test_seed_conversion_timeout_discards_process_tree(seed_setup):
    worker, cmd, _, seed = seed_setup
    run_adapter(worker, cmd, seed)
    # Trigger a long conversion only after the first job loaded the models.
    script = seed/'inference_v2.py'
    script.write_text(script.read_text().replace(
        'def main(args):', 'def main(args):\n    time.sleep(120)'))
    with pytest.raises(RuntimeError, match='timed out'):
        run_adapter(worker, cmd, seed, timeout=1)
    assert worker.proc is None
    if os.name != 'nt':
        events = [json.loads(s) for s in (seed/'seed-events.jsonl').read_text().splitlines()]
        for pid in {e[1] for e in events if e[0] == 'load'}:
            stat = Path(f'/proc/{pid}/stat')
            assert not stat.exists() or stat.read_text().split()[2] == 'Z'


def test_quality_setting_change_reuses_seed_model(seed_setup):
    worker, cmd, _, seed = seed_setup
    run_adapter(worker, cmd, seed)
    cmd[cmd.index('--diffusion-steps') + 1] = '12'
    run_adapter(worker, cmd, seed)
    events = [json.loads(s) for s in (seed/'seed-events.jsonl').read_text().splitlines()]
    assert sum(e[0] == 'load' for e in events) == 1
    assert [e[1]['diffusion_steps'] for e in events if e[0] == 'convert'] == [15, 12]
