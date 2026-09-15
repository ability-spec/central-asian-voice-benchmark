# BirOvoz Project Benchmark

BirOvoz is an AI dubbing demo: English speech → STT → translation → Uzbek/Kazakh TTS → playback.

This document records the verified baseline, engineering principles, priorities, and non-goals for anyone continuing work on the project.

## Repository

- GitHub: <https://github.com/ability-spec/central-asian-voice-benchmark>
- Working tree is at commit `9ea0004` (CP3 HEAD) with uncommitted CP5 local-clone work.
- **Do not commit or push CP5 changes until explicitly instructed.**

## Current verified baseline

- **Test suite:** 120 passed, 1 skipped (warnings only — FastAPI `on_event` deprecation, pre-existing).
- **DUB1–DUB4 regression:** 98 passed, 1 skipped across `test_dub_api`, `test_dub2_stream`, `test_dub3`, `test_dub4_continuous`, `test_dub4_recorder_fix`, `test_frontend_dub4`, `test_result_card`, `test_voice_clone`, `test_product_api`.
- **CP5 local clone (uncommitted):** integration with the real voice-lab Route B wrapper `b_sayro_then_seedvc.py` via its actual CLI (`--stage all --sentences <dir> --only 1 --out <dir> --target <ref.wav> --seedvc-python <py> --seedvc-dir <dir> --seedvc-version v1`). One subprocess per utterance with `cwd=SAYRO_VOICE_LAB_DIR`, per-request temp workspace, process-wide serialization lock (prevents concurrent Sayro loads), WAV validation, cleanup in `finally`. The wrapper internally handles Sayro load/Uzbek normalization/model teardown and the Seed-VC V1 subprocess with its known-good V1 flags (diffusion-steps=25, cfg-rate=0.8, f0 off, fp16, length-adjust=1.0, cwd=SEEDVC_DIR) — BirOvoz does not pass those flags and does not copy wrapper logic.
- **Language scope:** Local clone is **Uzbek-only** in CP5 MVP. Kazakh silently stays on OpenAI/Standard even when local-clone is selected; provider reports are truthful (labeled `openai/tts-1`). Do not claim Kazakh local-clone support without verification against a Kazakh Sayro voice and normalizer in voice-lab.
- **ElevenLabs:** Fully intact. `/api/voice/enroll` works, `eleven_multilingual_v2` provider is independent, local clone does not require an ElevenLabs key.
- **Fallback:** OpenAI/Standard TTS remains the default and the runtime fallback for any local-clone failure (missing config, subprocess error, Kazakh language, timeout).
- **Frontend:** 2-chip UI (Standard / My voice), no new UI surface added. Inline JS passes `node --check` via the repo's extract-then-check pattern. `git diff --check` is clean.
- **No binaries, models, references, or credentials** are committed. All model/reference paths are env-driven and live outside the repo; the reference WAV is never copied into the product tree.

## Engineering principles

1. **Preserve DUB1–DUB4.** The existing hands-free VAD capture, barge-in, latency HUD, sentence splitting, parallel translation/TTS, playback queue, continuous loop, NDJSON streaming, recorder lifecycle fixes, and result card are a strong baseline. Minimal call-site changes only.
2. **Do not rewrite working systems without evidence.** No speculative refactors, no framework swaps, no "while we're here" cleanups that aren't justified by a concrete failure.
3. **Incremental, measurable improvements.** Each change should be small, testable, and independently revertable.
4. **Do not drift into research-platform / generic SaaS territory.** BirOvoz is a product/demo. Do not build a generic dashboard, an OSS framework, an abstraction-heavy plugin architecture, or a research benchmark harness unless explicitly requested.
5. **No unnecessary dependencies or abstractions.** Prefer the simplest thing that works; avoid adding pip packages, npm deps, new service layers, or config knobs that aren't directly driven by a concrete requirement.
6. **Env-configured out-of-tree paths.** All voice-lab/Seed-VC/reference paths come from environment variables; never hard-code absolute Windows paths in tracked source.
7. **Do not modify or copy external projects.** Do not copy `b_sayro_then_seedvc.py`, `inference.py`, or `uzbek_normalizer.py` into the repo; invoke the existing voice-lab wrapper only.

## Priority order

1. **Real E2E verification** — confirm the product works end-to-end against the actual Windows voice-lab environment (not just mocks).
2. **Evidence-backed UX improvements** — fix concrete pain points observed during real use, not hypothetical ones.
3. **Latency / reliability** — reduce real wall-clock time and failure modes, keep `tts_ms`/`stt_ms`/`llm_ms`/`total_ms` truthful.
4. **Voice quality** — iterate on Sayro/Seed-VC tuning only after reliability is solid.
5. **Regression safety** — keep DUB1–DUB4, ElevenLabs, OpenAI fallback, and the latency HUD green on every change.

## Explicit non-goals

- Do not copy the voice-lab or Seed-VC implementation into the repository. Invoke the existing wrapper only.
- Do not commit local models, voice references, checkpoints (`.pt`/`.pth`/`.ckpt`/`.safetensors`/`.bin`/`.onnx`), audio files (`.wav`/`.mp3`/`.ogg`/`.flac`/`.aac`/`.m4a`), credentials, `.env` files with real values, or agent scratch artifacts.
- Do not modify backend behavior merely to enable a frontend experiment; front-end changes must not regress DUB1–DUB4 or alter TTS/STT semantics.
- Do not replace working architecture (FastAPI + direct subprocess + in-process state, static `index.html`, existing threading/queue model) without concrete evidence it's broken.
- Do not invent CLI flags for external tools; invoke them via their actual documented interface. If a flag is unknown, use the `ROUTE_B_EXTRA_ARGS` escape hatch rather than fabricating argparse entries.
- Do not claim support for languages (e.g., Kazakh local clone) that have not been verified against the real voice-lab environment.
