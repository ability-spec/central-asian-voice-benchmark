"""Upload duration limits must depend on the audio format, not byte count."""
import io
import wave

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from product.backend.routers import turn


def recording(seconds, rate=48000, channels=2, width=2):
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(b'\0' * (seconds * rate * channels * width))
    return buffer.getvalue()


@pytest.mark.parametrize('rate,channels,width', [(16000, 1, 2), (48000, 2, 2), (8000, 1, 1), (44100, 2, 3)])
def test_wav_duration_uses_header(rate, channels, width):
    # MIME metadata can be missing or inaccurate; the WAV header is authoritative.
    assert turn._get_audio_duration_seconds(recording(2, rate, channels, width), 'application/octet-stream') == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('stream', [False, True])
@pytest.mark.parametrize('seconds,rate,channels,width,rejected', [
    (10, 48000, 2, 2, False),  # old estimate incorrectly reported 60 seconds
    (31, 8000, 1, 1, True),  # old estimate incorrectly reported under 8 seconds
])
async def test_both_endpoints_apply_actual_duration(tmp_path, monkeypatch, stream, seconds, rate, channels, width, rejected):
    monkeypatch.setattr(turn.settings, 'upload_dir', tmp_path)
    monkeypatch.setattr(turn.settings, 'max_audio_duration_seconds', 30)
    converted = []

    async def stop_at_conversion(src, dst):
        converted.append(True)
        raise RuntimeError('test stops before provider calls')

    monkeypatch.setattr(turn, '_to_wav', stop_at_conversion)
    audio = UploadFile(file=io.BytesIO(recording(seconds, rate, channels, width)), filename='sample.wav',
                       headers=Headers({'content-type': 'audio/wav'}))
    endpoint = turn.handle_turn_stream if stream else turn.handle_turn
    with pytest.raises(HTTPException) as exc:
        await endpoint(audio, 'duration-regression', 'uz', '', 'chat', '')
    assert (exc.value.status_code == 413) == rejected
    assert bool(converted) == (not rejected)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize('stream', [False, True])
async def test_unknown_container_duration_is_checked_after_decode(tmp_path, monkeypatch, stream):
    monkeypatch.setattr(turn.settings, 'upload_dir', tmp_path)
    monkeypatch.setattr(turn.settings, 'max_audio_duration_seconds', 30)
    original_probe = turn._get_audio_duration_seconds
    monkeypatch.setattr(turn, '_get_audio_duration_seconds',
                        lambda data, mime: 0 if data == b'webm-without-duration' else original_probe(data, mime))
    async def decode(src, dst):
        dst.write_bytes(recording(31, 16000, 1, 2))
    def forbidden(*args):
        pytest.fail('Overlong decoded audio reached transcription')
    monkeypatch.setattr(turn, '_to_wav', decode)
    monkeypatch.setattr(turn, 'transcribe', forbidden)
    audio = UploadFile(file=io.BytesIO(b'webm-without-duration'), filename='recording.webm',
                       headers=Headers({'content-type': 'audio/webm'}))
    endpoint = turn.handle_turn_stream if stream else turn.handle_turn
    with pytest.raises(HTTPException) as error:
        await endpoint(audio, 'unknown-duration', 'uz', '', 'chat', '')
    assert error.value.status_code == 413
    assert list(tmp_path.iterdir()) == []
