"""Stdlib-only WAV helpers for joining per-sentence dub audio.

A dub is synthesized sentence by sentence and the parts can differ: the local
clone (Seed-VC) may emit IEEE-float WAV at 22,050 Hz, while an OpenAI fallback
for one sentence returns 16-bit PCM at 24,000 Hz. The stdlib ``wave`` module
cannot read float WAV and cannot mix sample rates, so joining such parts used
to fall back to the first sentence only. These helpers decode every part to
mono floats, resample to one rate and write a single 16-bit PCM WAV.
"""

from __future__ import annotations

import array
import io
import struct
import sys
import wave
from dataclasses import dataclass

WAVE_FORMAT_PCM = 1
WAVE_FORMAT_IEEE_FLOAT = 3
WAVE_FORMAT_EXTENSIBLE = 0xFFFE


@dataclass(frozen=True)
class WavInfo:
    format_tag: int
    channels: int
    sample_rate: int
    bits_per_sample: int
    data: bytes


def read_wav(blob: bytes) -> WavInfo:
    """Parse a RIFF/WAVE container (PCM int or IEEE float, incl. EXTENSIBLE)."""
    if len(blob) < 12 or blob[:4] != b"RIFF" or blob[8:12] != b"WAVE":
        raise ValueError("not a RIFF/WAVE file")
    pos, end = 12, len(blob)
    fmt = None
    data = None
    while pos + 8 <= end:
        chunk_id = blob[pos:pos + 4]
        (size,) = struct.unpack("<I", blob[pos + 4:pos + 8])
        body_start = pos + 8
        body_end = body_start + size
        if chunk_id == b"data" and (size == 0xFFFFFFFF or body_end > end):
            # Streaming writers leave a placeholder size; the samples run to EOF.
            body_end = end
        if body_end > end:
            break
        body = blob[body_start:body_end]
        if chunk_id == b"fmt ":
            if len(body) < 16:
                raise ValueError("truncated fmt chunk")
            format_tag, channels, rate, _, _, bits = struct.unpack("<HHIIHH", body[:16])
            if format_tag == WAVE_FORMAT_EXTENSIBLE and len(body) >= 26:
                (format_tag,) = struct.unpack("<H", body[24:26])  # sub-format GUID prefix
            fmt = (format_tag, channels, rate, bits)
        elif chunk_id == b"data":
            data = body
        pos = body_end + (size & 1 if body_end - body_start == size else 0)
    if fmt is None or data is None:
        raise ValueError("WAV is missing a fmt or data chunk")
    format_tag, channels, rate, bits = fmt
    if channels < 1 or rate <= 0:
        raise ValueError("invalid channel count or sample rate")
    if (format_tag, bits) not in {(WAVE_FORMAT_PCM, 8), (WAVE_FORMAT_PCM, 16), (WAVE_FORMAT_PCM, 24),
                                  (WAVE_FORMAT_PCM, 32), (WAVE_FORMAT_IEEE_FLOAT, 32),
                                  (WAVE_FORMAT_IEEE_FLOAT, 64)}:
        raise ValueError(f"unsupported WAV encoding: format {format_tag}, {bits} bits")
    frame_bytes = channels * bits // 8
    data = data[:len(data) - len(data) % frame_bytes]
    return WavInfo(format_tag, channels, rate, bits, data)


def _typed(code: str, raw: bytes) -> array.array:
    values = array.array(code)
    values.frombytes(raw)
    if sys.byteorder == "big":
        values.byteswap()
    return values


def decode_mono(info: WavInfo) -> list[float]:
    """Samples in [-1, 1], channels averaged to mono."""
    raw, bits = info.data, info.bits_per_sample
    if info.format_tag == WAVE_FORMAT_IEEE_FLOAT:
        samples = list(_typed("f" if bits == 32 else "d", raw))
    elif bits == 8:
        samples = [(b - 128) / 128.0 for b in raw]
    elif bits == 16:
        samples = [v / 32768.0 for v in _typed("h", raw)]
    elif bits == 32:
        samples = [v / 2147483648.0 for v in _typed("i", raw)]
    else:  # 24-bit little-endian signed
        samples = [int.from_bytes(raw[i:i + 3], "little", signed=True) / 8388608.0
                   for i in range(0, len(raw), 3)]
    channels = info.channels
    if channels == 1:
        return samples
    return [sum(samples[i:i + channels]) / channels for i in range(0, len(samples), channels)]


def resample_linear(samples: list[float], source_rate: int, target_rate: int) -> list[float]:
    """Linear-interpolation resampling; adequate for joining speech clips."""
    if source_rate == target_rate or not samples:
        return samples
    count = max(1, round(len(samples) * target_rate / source_rate))
    step = source_rate / target_rate
    last = len(samples) - 1
    out = []
    for i in range(count):
        position = i * step
        j = int(position)
        if j >= last:
            out.append(samples[last])
            continue
        fraction = position - j
        out.append(samples[j] + (samples[j + 1] - samples[j]) * fraction)
    return out


def encode_pcm16(samples: list[float], sample_rate: int) -> bytes:
    pcm = array.array("h", (int(max(-1.0, min(1.0, s)) * 32767.0) for s in samples))
    if sys.byteorder == "big":
        pcm.byteswap()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(sample_rate)
        target.writeframes(pcm.tobytes())
    return buffer.getvalue()


def concat_wavs(parts: list[bytes]) -> bytes:
    """Join WAV parts in order into one playable WAV.

    Identical integer-PCM parts are joined without re-encoding (byte-exact
    frames, original channels and rate). Otherwise every part is converted to
    mono, resampled to the highest rate among the parts and written as 16-bit
    PCM. Raises ValueError if any part cannot be decoded.
    """
    if not parts:
        raise ValueError("no WAV parts")
    infos = [read_wav(part) for part in parts]
    shapes = {(i.format_tag, i.channels, i.sample_rate, i.bits_per_sample) for i in infos}
    if len(shapes) == 1 and infos[0].format_tag == WAVE_FORMAT_PCM and infos[0].bits_per_sample <= 32:
        first = infos[0]
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as target:
            target.setnchannels(first.channels)
            target.setsampwidth(first.bits_per_sample // 8)
            target.setframerate(first.sample_rate)
            target.writeframes(b"".join(i.data for i in infos))
        return buffer.getvalue()
    target_rate = max(i.sample_rate for i in infos)
    joined: list[float] = []
    for info in infos:
        joined.extend(resample_linear(decode_mono(info), info.sample_rate, target_rate))
    return encode_pcm16(joined, target_rate)
