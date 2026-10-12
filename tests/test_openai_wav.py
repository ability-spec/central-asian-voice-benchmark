"""Regression for completed OpenAI WAV responses with streaming size fields."""
import io
import struct
import wave
from types import SimpleNamespace

from product.backend.services import tts


def test_openai_streaming_wav_is_finalized_without_changing_pcm(monkeypatch):
    frames = struct.pack('<hhhh', 0, 1000, -1000, 2000) * 2400
    output = io.BytesIO()
    with wave.open(output, 'wb') as w:
        w.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        w.writeframes(frames)
    data = bytearray(output.getvalue())
    struct.pack_into('<I', data, 4, 0xFFFFFFFF)
    struct.pack_into('<I', data, 40, 0xFFFFFFFF)
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(content=bytes(data))

    monkeypatch.setattr(tts, 'OpenAI', lambda **kwargs: SimpleNamespace(
        audio=SimpleNamespace(speech=SimpleNamespace(create=create))))
    result = tts._openai_synthesize('Сәлем.', 'kk')
    with wave.open(io.BytesIO(result), 'rb') as w:
        assert w.getnframes() == len(frames) // 2
        assert w.getframerate() == 24000
        assert w.readframes(w.getnframes()) == frames
    assert len(calls) == 1
    assert struct.unpack_from('<I', result, 4)[0] == len(result) - 8
