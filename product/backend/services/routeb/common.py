#!/usr/bin/env python3
"""Shared helpers for the voice-lab scripts. Stdlib-only at import time (works on py3.9+)."""
import contextlib
import inspect
import re
import wave
from pathlib import Path

LAB = Path(__file__).resolve().parent


def parse_numbered(path):
    """Parse 'NN. text' lines -> list of (num:int, text:str). Skips blanks and # comments."""
    out = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^(\d+)[.)]\s*(.+)$", line)
        if m:
            out.append((int(m.group(1)), m.group(2).strip()))
    if not out:
        raise SystemExit(f"[common] no numbered lines found in {path}")
    return out


def filter_kwargs(func, kwargs):
    """Drop kwargs the callable does not accept (survives minor API drift between versions)."""
    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError):
        return kwargs
    for p in sig.parameters.values():
        if p.kind is inspect.Parameter.VAR_KEYWORD:
            return kwargs
    return {k: v for k, v in kwargs.items() if k in sig.parameters}


def load_qwen_model(model_id, device="cuda:0", dtype_name="bfloat16", attn="sdpa"):
    """Load a Qwen3TTSModel, tolerating kwarg-name drift (dtype vs torch_dtype, attn optional)."""
    import torch
    from qwen_tts import Qwen3TTSModel

    dtype = {"bfloat16": torch.bfloat16, "float16": torch.float16, "float32": torch.float32}[dtype_name]
    attempts = [
        dict(device_map=device, dtype=dtype, attn_implementation=attn),
        dict(device_map=device, torch_dtype=dtype, attn_implementation=attn),
        dict(device_map=device, dtype=dtype),
        dict(device_map=device, torch_dtype=dtype),
        dict(device_map=device),
    ]
    last = None
    for kw in attempts:
        try:
            return Qwen3TTSModel.from_pretrained(model_id, **kw)
        except TypeError as e:
            last = e
            continue
    raise last


def unpack_generation(result):
    """Return (list_of_wavs, sample_rate) from a generate_* call, tolerant of return ordering."""
    if not (isinstance(result, tuple) and len(result) == 2):
        raise RuntimeError(f"unexpected generation return type: {type(result)}")
    a, b = result
    if isinstance(a, int) and not hasattr(b, "__len__"):
        return [b], a
    if isinstance(a, int):
        wavs = list(b) if isinstance(b, (list, tuple)) else [b]
        return wavs, int(a)
    wavs = list(a) if isinstance(a, (list, tuple)) else [a]
    return wavs, int(b)


def write_wav(path, wav, sr):
    """Write a numpy array / torch tensor to a 16-bit mono WAV. Stdlib only."""
    import numpy as np

    if hasattr(wav, "detach"):
        wav = wav.detach().cpu().numpy()
    arr = np.asarray(wav)
    arr = np.squeeze(arr)
    if arr.ndim == 2 and arr.shape[-1] == 2:
        arr = arr.mean(axis=-1)  # defensive: stereo -> mono
    if arr.ndim == 2 and arr.shape[0] == 1:
        arr = arr[0]
    if arr.ndim != 1:
        raise RuntimeError(f"cannot write wav with shape {np.asarray(wav).shape}")
    if arr.dtype.kind == "f":
        peak = float(np.max(np.abs(arr))) or 1.0
        if peak > 1.0:
            arr = arr / peak
        pcm = (arr * 32767.0).astype("<i2")
    else:
        pcm = arr.astype("<i2")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.closing(wave.open(str(path), "wb")) as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sr))
        w.writeframes(pcm.tobytes())


def print_oom_advice():
    print("\n[!] CUDA out of memory. In order of preference:")
    print("    1) close other GPU apps (browser hardware accel, games, other notebooks)")
    print("    2) retry with:  --model Qwen/Qwen3-TTS-12Hz-0.6B-Base   (~1.2 GB weights instead of ~3.4 GB)")
    print("    3) retry with:  --dtype float16")
    print("    4) run stages separately:  b_sayro_then_seedvc.py --stage sayro   then   --stage convert")


def is_cuda_oom(exc):
    return "out of memory" in str(exc).lower()
