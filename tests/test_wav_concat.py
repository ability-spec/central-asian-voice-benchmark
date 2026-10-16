"""Joining per-sentence dub WAVs (wav_audio): stdlib only, no providers.

Regression: replay / Download WAV used the concatenated `audio` field, which
kept only the first sentence whenever parts differed in sample rate or used
IEEE-float WAV (Seed-VC), because the stdlib `wave` module cannot read float
WAV ("unknown format: 3").
"""

import array
import io
import math
import struct
import sys
import wave

import pytest

from product.backend.services import wav_audio


def pcm16_wav(rate, seconds, channels=1, amplitude=0.25, freq=440.0):
    frames = int(rate * seconds)
    samples = array.array("h")
    for i in range(frames):
        value = int(amplitude * 32767 * math.sin(2 * math.pi * freq * i / rate))
        samples.extend([value] * channels)
    if sys.byteorder == "big":
        samples.byteswap()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(samples.tobytes())
    return buffer.getvalue()


def float32_wav(rate, seconds, amplitude=0.25, freq=440.0, extensible=False):
    frames = int(rate * seconds)
    data = struct.pack(f"<{frames}f", *(amplitude * math.sin(2 * math.pi * freq * i / rate)
                                         for i in range(frames)))
    if extensible:
        guid_prefix = struct.pack("<H", 3)
        fmt = (struct.pack("<HHIIHH", 0xFFFE, 1, rate, rate * 4, 4, 32)
               + struct.pack("<HHI", 22, 32, 4) + guid_prefix + b"\x00" * 14)
    else:
        fmt = struct.pack("<HHIIHH", 3, 1, rate, rate * 4, 4, 32)
    body = (b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt
            + b"data" + struct.pack("<I", len(data)) + data)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def frames_and_rate(blob):
    with wave.open(io.BytesIO(blob), "rb") as wf:
        return wf.getnframes(), wf.getframerate(), wf.getnchannels(), wf.getsampwidth()


def test_stdlib_wave_cannot_read_float_wav():
    """Documents why the old stdlib-only join dropped clone audio."""
    with pytest.raises(wave.Error):
        wave.open(io.BytesIO(float32_wav(22050, 0.1)), "rb")


def test_identical_pcm_parts_join_byte_exact():
    parts = [pcm16_wav(24000, 0.5), pcm16_wav(24000, 0.25)]
    joined = wav_audio.concat_wavs(parts)
    assert frames_and_rate(joined) == (int(0.5 * 24000) + int(0.25 * 24000), 24000, 1, 2)
    with wave.open(io.BytesIO(joined), "rb") as wf:
        frames = wf.readframes(wf.getnframes())
    expected = b"".join(wav_audio.read_wav(p).data for p in parts)
    assert frames == expected


def test_float_clone_parts_are_all_kept():
    parts = [float32_wav(22050, 0.5), float32_wav(22050, 0.3), float32_wav(22050, 0.2)]
    frames, rate, channels, width = frames_and_rate(wav_audio.concat_wavs(parts))
    assert (rate, channels, width) == (22050, 1, 2)
    assert frames == int(0.5 * 22050) + int(0.3 * 22050) + int(0.2 * 22050)


def test_clone_plus_openai_fallback_keeps_total_duration():
    parts = [float32_wav(22050, 1.0), pcm16_wav(24000, 1.0), float32_wav(22050, 0.5, extensible=True)]
    frames, rate, _, _ = frames_and_rate(wav_audio.concat_wavs(parts))
    assert rate == 24000
    assert abs(frames / rate - 2.5) < 0.002


def test_stereo_is_mixed_to_mono_and_level_is_preserved():
    joined = wav_audio.concat_wavs([pcm16_wav(16000, 0.2, channels=2), float32_wav(16000, 0.2)])
    info = wav_audio.read_wav(joined)
    assert info.channels == 1
    peak = max(abs(s) for s in wav_audio.decode_mono(info))
    assert 0.24 < peak < 0.26


def test_streaming_placeholder_data_size_is_read_to_end():
    blob = bytearray(pcm16_wav(24000, 0.1))
    data_at = blob.index(b"data")
    blob[data_at + 4:data_at + 8] = struct.pack("<I", 0xFFFFFFFF)
    assert len(wav_audio.read_wav(bytes(blob)).data) == int(0.1 * 24000) * 2


@pytest.mark.parametrize("blob", [b"", b"not-a-wav", b"RIFF\x00\x00\x00\x00WAVE"])
def test_undecodable_parts_raise(blob):
    with pytest.raises(ValueError):
        wav_audio.concat_wavs([pcm16_wav(16000, 0.1), blob])


def test_resample_preserves_duration():
    samples = [0.0] * 22050
    assert len(wav_audio.resample_linear(samples, 22050, 24000)) == 24000
