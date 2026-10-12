"""Configuration-selected Uzbek profile; no model/cloud calls."""
import pytest
from product.backend.config import Settings
from product.backend.services import voice_clone


def test_default_steps_are_ten(monkeypatch):
    monkeypatch.delenv('ROUTE_B_DIFFUSION_STEPS', raising=False)
    assert Settings().route_b_diffusion_steps == 10


@pytest.mark.parametrize('steps', [10, 15])
def test_explicit_profile_and_rollback_reach_wrapper_cli(monkeypatch, tmp_path, steps):
    monkeypatch.setenv('ROUTE_B_DIFFUSION_STEPS', str(steps))
    settings = Settings()
    assert settings.route_b_diffusion_steps == steps
    monkeypatch.setattr(voice_clone, 'settings', settings)
    monkeypatch.setattr(voice_clone, '_resolve_sayro_script', lambda: tmp_path/'wrapper.py')
    monkeypatch.setattr(voice_clone, '_resolve_sayro_python', lambda script: 'python')
    monkeypatch.setattr(voice_clone, '_resolve_seedvc_dir', lambda: tmp_path/'seed-vc')
    monkeypatch.setattr(voice_clone, '_resolve_seedvc_python', lambda directory: 'python')
    settings.seedvc_reference_wav = str(tmp_path/'reference.wav')
    settings.route_b_extra_args = ''
    cmd = voice_clone._build_route_b_cmd(tmp_path/'text.txt', tmp_path/'out')
    assert cmd[cmd.index('--diffusion-steps')+1] == str(steps)
