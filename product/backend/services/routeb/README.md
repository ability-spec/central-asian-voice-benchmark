# Route B (Sayro → Seed-VC) — vendored orchestration wrapper

This directory contains the Route B end-to-end orchestration wrapper used by
BirOvoz's `local-clone` TTS provider. It is a **vendored copy** of the
standalone `voice-lab/b_sayro_then_seedvc.py` + `common.py` scripts used for
benchmarking on the developer's Windows machine. The heavy model code
(Sayro, Seed-VC, campplus, ASTRAL quantizers, vocoder) is NOT vendored — it
lives in external checkouts / HuggingFace cache.

## Contents

- `b_sayro_then_seedvc.py` — entry point. Two stages:
    1. `stage_sayro`: runs Sayro TTS (`uzlm/sayro-tts-1.7B`) in-process and
       writes numbered wavs to `out/b_sayro/tNN.wav`.
    2. `stage_convert`: launches **one persistent** `seed-vc/inference_v2.py`
       subprocess per batch with the `--source-list` JSON batch mode. The
       Seed-VC v2 wrapper (vc_wrapper.py) caches target/reference features
       in-process across sources.
- `common.py` — stdlib-only helpers (numbered-sentence parser, WAV writer,
  Sayro model loader, OOM helpers). Imports torch/qwen_tts lazily inside
  `load_qwen_model()`.

## Expected external layout

The wrapper shells out to Seed-VC; it does NOT import Seed-VC directly.
Expected Seed-VC layout (by conventional default `product/backend/third_party/seed-vc/`,
overridable via `SEEDVC_DIR`):

```
product/backend/
  .venv-routeb/         # Sayro venv (torch, transformers, qwen-tts, accelerate ...)
  third_party/
    seed-vc/            # git clone https://github.com/ability-spec/seed-vc
      inference_v2.py   # from commit 357cd6d  (persistent batch worker)
      vc_wrapper.py     # from commit 5c0a4f8  (target-feature cache)
      configs/v2/vc_wrapper.yaml
      .venv-vc/         # Seed-VC venv (torch, hydra, omegaconf, soundfile, librosa ...)
```

Pinned commits on `ability-spec/seed-vc`:

| Commit    | Description                                            |
|-----------|--------------------------------------------------------|
| `357cd6d` | `feat: support persistent Seed-VC V2 batch inference`  |
| `5c0a4f8` | `perf: cache Seed-VC V2 target features`               |

Running against a different Seed-VC checkout may work but is unverified.

## Out-of-repo by design

- Sayro weights: HuggingFace cache (`~/.cache/huggingface/`), `uzlm/sayro-tts-1.7B` (gated).
- Seed-VC weights: downloaded on first run by `hf_utils.load_custom_model_from_hf`
  (Plachta/Seed-VC v2 checkpoints, ASTRAL quantizers, campplus style encoder).
- Reference voice WAV: `SEEDVC_REFERENCE_WAV` env var points at the user's
  enrolled voice sample — never committed.
- `uzbek_normalizer.py`: gated Sayro-repo helper. Place it in this directory
  if you want it; the wrapper falls back to whitespace-only normalization
  when it's absent. The filename is gitignored.

## Quality knobs (hardcoded in the wrapper, matching the 74.86s/5-sentence benchmark)

| Flag                    | Value |
|-------------------------|-------|
| Seed-VC version         | v2    |
| diffusion_steps         | 15    |
| length_adjust           | 1.0   |
| intelligibility-cfg     | 0.8   |
| similarity-cfg          | 0.8   |
| top_p                   | 0.9   |
| temperature             | 1.0   |
| convert_style           | false |
| compile                 | false |
| fp16 (V2)               | float16 (from inference_v2.py global `dtype`) |

`--intelligibility` / `--similarity` / `--diffusion-steps` are exposed in the
wrapper CLI; BirOvoz passes them from env (`ROUTE_B_DIFFUSION_STEPS` etc.)
but the defaults above are the tuned production values.

## Manual smoke test (bypassing BirOvoz)

From `product/backend/`, with the Sayro venv activated:

```cmd
.venv-routeb\Scripts\python.exe services\routeb\b_sayro_then_seedvc.py ^
  --stage all --sentences path\to\numbered.txt ^
  --out routeb_smoke ^
  --target path\to\reference.wav ^
  --seedvc-python third_party\seed-vc\.venv-vc\Scripts\python.exe ^
  --seedvc-dir third_party\seed-vc ^
  --seedvc-version v2 ^
  --diffusion-steps 15 ^
  --intelligibility 0.8 --similarity 0.8
```

Expected `[B]` log markers (parsed by `services/voice_clone.py`):

- `[B] loaded in Xs` — Sayro model load
- `[B] t01 -> out/b_sayro/t01.wav` — Sayro wrote TTS wav
- `[B][vc] launching ONE persistent Seed-VC v2 process for N source(s)` — batch
- `[B][vc] t01.wav -> b_sayro_vc/t01.wav (X.XXs)` — per-sentence VC
- `[B] convert stage done -> out/b_sayro_vc`

## Updating the vendored snapshot

When a new micro-optimization lands in the standalone `voice-lab/` checkout
(e.g. a future Sayro daemon or DUB batch path):

1. Benchmark standalone first.
2. Copy `b_sayro_then_seedvc.py` and any changed helpers into this directory.
3. Bump the pinned Seed-VC commit in this README if `inference_v2.py` or
   `vc_wrapper.py` changed.
4. Run `tests/test_local_clone.py` and `tests/test_voice_clone.py` before
   committing.
