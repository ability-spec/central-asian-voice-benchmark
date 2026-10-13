"""Shutdown compatibility remains valid after merging application lifecycle changes."""
from fastapi.testclient import TestClient

from product.backend.main import app
from product.backend.services import voice_clone


def test_close_is_idempotent_and_clears_daemon(monkeypatch):
    calls = []

    class Daemon:
        def shutdown(self):
            calls.append('shutdown')

    monkeypatch.setattr(voice_clone, '_routeb_daemon', Daemon())
    voice_clone.close_route_b_worker()
    voice_clone.close_route_b_worker()
    assert calls == ['shutdown']
    assert voice_clone._routeb_daemon is None


def test_failed_shutdown_still_clears_daemon(monkeypatch):
    class Daemon:
        def shutdown(self):
            raise RuntimeError('injected shutdown failure')

    monkeypatch.setattr(voice_clone, '_routeb_daemon', Daemon())
    voice_clone.close_route_b_worker()
    assert voice_clone._routeb_daemon is None


def test_application_lifespan_closes_daemon_once(monkeypatch, tmp_path):
    calls = []

    class Daemon:
        def shutdown(self):
            calls.append('shutdown')

    monkeypatch.setattr(voice_clone, '_routeb_daemon', Daemon())
    monkeypatch.setattr(voice_clone.settings, 'upload_dir', tmp_path / 'uploads')
    monkeypatch.setattr(voice_clone.settings, 'audio_output_dir', tmp_path / 'audio')
    with TestClient(app):
        assert calls == []
    assert calls == ['shutdown']
    assert voice_clone._routeb_daemon is None
