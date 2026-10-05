"""CPU-only failure, cancellation and responsiveness regressions."""
import asyncio
import io
import json
import threading
import time
import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers
from product.backend.routers import turn
from product.backend.services import voice_clone

REAL_TO_WAV = turn._to_wav

@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    monkeypatch.setattr(turn.settings, 'upload_dir', tmp_path)
    monkeypatch.setattr(turn, '_get_audio_duration_seconds', lambda *a: 0.1)
    monkeypatch.setattr(turn, 'transcribe', lambda *a: 'Hello')
    monkeypatch.setattr(turn, 'respond', lambda *a: 'Salom')
    monkeypatch.setattr(turn, 'synthesize_b64', lambda *a, **k: 'YXVkaW8=')
    monkeypatch.setattr(turn, 'take_last_report', lambda: {})
    monkeypatch.setattr(turn, 'log_turn', lambda **k: None)
    async def convert(src, dst):
        dst.write_bytes(src.read_bytes())
    monkeypatch.setattr(turn, '_to_wav', convert)
    return tmp_path

def upload():
    return UploadFile(file=io.BytesIO(b'1234'), filename='test.wav', headers=Headers({'content-type': 'audio/wav'}))

async def call(stream=False):
    fn = turn.handle_turn_stream if stream else turn.handle_turn
    return await fn(upload(), 'audit-test', 'uz', '', 'chat', '')

@pytest.mark.asyncio
@pytest.mark.parametrize('stream', [False, True])
@pytest.mark.parametrize('stage', ['_to_wav', 'transcribe', 'respond', 'synthesize_b64'])
async def test_failure_removes_all_audio(pipeline, monkeypatch, stream, stage):
    def fail(*args, **kwargs):
        raise RuntimeError('injected failure')
    async def fail_conversion(src, dst):
        dst.write_bytes(b'partial')
        fail()
    monkeypatch.setattr(turn, stage, fail_conversion if stage == '_to_wav' else fail)
    if stream and stage != '_to_wav':
        response = await call(True)
        events = [json.loads(item) async for item in response.body_iterator]
        assert events[-1]['type'] == 'error'
    else:
        with pytest.raises(HTTPException):
            await call(stream)
    assert list(pipeline.iterdir()) == []

@pytest.mark.asyncio
async def test_event_loop_runs_during_transcription(pipeline, monkeypatch):
    started, release = threading.Event(), threading.Event()
    def transcribe(*args):
        started.set()
        assert release.wait(2), 'event loop could not release the worker'
        return 'Hello'
    monkeypatch.setattr(turn, 'transcribe', transcribe)
    task = asyncio.create_task(call())
    for _ in range(100):
        if started.is_set(): break
        await asyncio.sleep(0.01)
    assert started.is_set()
    release.set()
    await task
    assert list(pipeline.iterdir()) == []

@pytest.mark.asyncio
async def test_cancel_waits_for_audio_reader_before_cleanup(pipeline, monkeypatch):
    started, release = threading.Event(), threading.Event()
    def transcribe(path, *args):
        started.set()
        assert release.wait(2)
        assert path.exists()
        return 'Hello'
    monkeypatch.setattr(turn, 'transcribe', transcribe)
    task = asyncio.create_task(call())
    while not started.is_set(): await asyncio.sleep(.01)
    task.cancel()
    await asyncio.sleep(.02)
    assert list(pipeline.iterdir())
    release.set()
    with pytest.raises(asyncio.CancelledError): await task
    assert list(pipeline.iterdir()) == []

@pytest.mark.asyncio
async def test_upload_read_is_bounded(monkeypatch):
    monkeypatch.setattr(turn.settings, 'max_audio_size_mb', 1)
    class TooLarge:
        async def read(self, size=-1):
            assert size == 1024 * 1024 + 1
            return b'x' * size
    with pytest.raises(HTTPException) as exc:
        await turn._read_bounded_audio(TooLarge())
    assert exc.value.status_code == 413

@pytest.mark.asyncio
async def test_stream_chat_reports_distinct_stage_times(pipeline, monkeypatch):
    def reply(*args): time.sleep(.03); return 'Salom'
    def speak(*args, **kwargs): time.sleep(.06); return 'YXVkaW8='
    monkeypatch.setattr(turn, 'respond', reply)
    monkeypatch.setattr(turn, 'synthesize_b64', speak)
    response = await call(True)
    done = [json.loads(item) async for item in response.body_iterator][-1]
    assert done['type'] == 'done'
    assert done['llm_ms'] >= 25
    assert done['tts_ms'] >= 55
    assert done['total_ms'] >= done['llm_ms'] + done['tts_ms'] - 2

def test_shutdown_alias_importable():
    assert voice_clone.close_route_b_worker is voice_clone._shutdown_daemon

@pytest.mark.asyncio
async def test_ffmpeg_is_reaped_on_cancellation(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock, Mock
    started = asyncio.Event()
    async def communicate():
        started.set()
        await asyncio.Event().wait()
    proc = Mock(returncode=None, communicate=communicate, wait=AsyncMock())
    monkeypatch.setattr(turn.asyncio, 'create_subprocess_exec', AsyncMock(return_value=proc))
    task = asyncio.create_task(turn._to_wav(tmp_path/'raw', tmp_path/'norm'))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    proc.kill.assert_called_once()
    proc.wait.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('stream', [False, True])
async def test_conversion_timeout_reaps_process_and_removes_uploads(pipeline, monkeypatch, stream):
    from unittest.mock import AsyncMock, Mock
    monkeypatch.setattr(turn, '_to_wav', REAL_TO_WAV)
    monkeypatch.setattr(turn, 'AUDIO_CONVERSION_TIMEOUT_S', .01)
    async def communicate():
        await asyncio.Event().wait()
    proc = Mock(returncode=None, communicate=communicate, wait=AsyncMock())
    spawn = AsyncMock(return_value=proc)
    monkeypatch.setattr(turn.asyncio, 'create_subprocess_exec', spawn)
    with pytest.raises(HTTPException) as exc:
        await call(stream)
    assert exc.value.status_code == 422
    proc.kill.assert_called_once()
    proc.wait.assert_awaited_once()
    assert '-nostdin' in spawn.call_args.args
    assert list(pipeline.iterdir()) == []
