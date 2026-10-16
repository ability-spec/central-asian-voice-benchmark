# BirOvoz — MVP handoff

## Status and next steps (as of 2026-10-16)

Dates are when the work first landed on `master` (from Git history). Labels:
**Verified (CPU)** = covered by the CPU regression suite with provider/model substitutes;
**Owner-reported** = recorded in `WORK_STATUS.md` from the owner's Windows/NVIDIA machine,
not re-run in CI; **Pending** = not yet done.

| Area | Status | First on `master` | Note |
| --- | --- | --- | --- |
| FastAPI + static HTML demo | Verified (CPU) | 2026-08-27 | Single machine, in-memory sessions |
| English → Uzbek/Kazakh dubbing (DUB1–DUB4), NDJSON streaming, barge-in | Verified (CPU) | 2026-09-10 – 2026-09-11 | Live OpenAI STT/translation/TTS not verified in CI |
| ElevenLabs voice + consent-gated enrollment (VC1) | Verified (CPU) | 2026-09-13 | Optional provider |
| Uzbek local clone, Sayro → Seed-VC (CP5), persistent daemon | Owner-reported | 2026-09-15; daemon 2026-09-26 | 3 local calls on 2026-10-12: cold 34.7 s, warm 9.2–10.7 s |
| 10-step listening-approved profile | Owner-reported | 2026-10-12 | `.env.example` aligned on 2026-10-16 |
| Stop / New session, upload, Download WAV, preflight | Verified (CPU) | 2026-10-05 | Full-dub WAV keeps every sentence since 2026-10-16 |
| Cancellation and stale-callback fixes | Verified (CPU) | 2026-10-06, 2026-10-12 | Real-browser check pending |
| Chrome side panel (MV3) | Verified (CPU, Node) | 2026-10-13 | Not yet loaded in real Chrome by CI |
| Server binds 127.0.0.1 by default | Verified (CPU) | 2026-10-16 | Set `HOST=0.0.0.0` only on a trusted network |
| Minimal "Voice workspace" UI | Pending merge | — | On branch `demo` (2026-10-13); `master` still serves the older page |
| Kazakh local clone | Not started | — | Kazakh uses OpenAI voices |
| Windows/NVIDIA release acceptance (below) | Pending | — | Required before calling the demo released |

Next steps, in order (target dates are proposals for the owner to adjust):

| # | Step | Proposed target | Done when |
| --- | --- | --- | --- |
| 1 | Run the five-step Windows/NVIDIA acceptance below with real keys | 2026-10-23 | Results recorded: EN→UZ and EN→KK audio, actual provider, cold/warm time, cancel with no stale audio |
| 2 | Review and merge the `demo` UI into `master` | 2026-10-23 | `/` serves the new page; CPU suite green |
| 3 | Re-check Download WAV on a real multi-sentence local-clone dub | 2026-10-23 | Downloaded duration equals the played audio |
| 4 | Decide on Kazakh local cloning (needs a verified Kazakh voice path) | 2026-11-06 | Decision recorded; no claim before verification |

## Current state

BirOvoz is a working FastAPI + static HTML voice demo for English speech →
Uzbek/Kazakh dubbing. The primary flow is DUB1–DUB4: microphone capture,
English STT, translation, sentence-level TTS, ordered playback, hands-free
re-listening, barge-in, and NDJSON streaming.

The prompted benchmark loop is now complete as an opt-in panel in
`product/frontend/index.html`:

- choose a frozen Uzbek/Kazakh reference prompt from `GET /api/prompts`;
- upload a target-language recording;
- score it through `POST /api/turn` with `reference_text`;
- see reference vs transcript, WER/CER, stage latency, provider, and a truthful
  `MOCK` badge;
- load the frozen read-only leaderboard from `GET /api/leaderboard`.

The normal dubbing microphone remains unchanged and does not send benchmark
references accidentally.

## Important paths

- API: `product/backend/main.py`, `product/backend/models.py`,
  `product/backend/routers/turn.py`, `product/backend/routers/data.py`
- UI: `product/frontend/index.html` (single file, no framework)
- Data (read-only): `research/phase3a_audio_manifest.csv`,
  `research/final_benchmark_results.csv`
- Tests: `tests/test_product_api.py`, `tests/test_result_card.py`, and the
  DUB1–DUB4 regression tests
- Environment: `product/backend/.env` (gitignored)

## API contracts

- `POST /api/turn` multipart: `audio`, `conversation_id`, `language`, optional
  `reference_text`, `mode`, and `source_language`. Returns transcript, reply,
  base64 WAV, provider info, scoring fields, and stage latency.
- `POST /api/turn/stream` NDJSON: the live dubbing transport (`meta`, `part`,
  `done`, `error`).
- `GET /api/prompts?language=uz|kk`: 100 manifest prompts in order.
- `GET /api/leaderboard`: frozen aggregate rows, passed through without
  recomputation.

## Verification

The focused product + frontend + DUB regression run is green:

```bash
python -m pytest tests/test_product_api.py tests/test_result_card.py \
  tests/test_frontend_dub4.py tests/test_dub_api.py tests/test_dub2_stream.py \
  tests/test_dub3.py tests/test_dub4_continuous.py tests/test_dub4_recorder_fix.py -q
# 103 passed in the current sandbox
```

The full CPU suite now runs with:

```bash
python -m pip install -r product/backend/requirements.txt pytest pytest-asyncio httpx jiwer
python -m pytest tests product/backend/tests -q
```

The retained offload adapter/cache helpers are tested independently from the
production `RouteBDaemonClient`. No removed settings are injected. The existing
GitHub Actions job now runs this complete suite, including product/UI tests.
No real-provider inference or benchmark rerun was performed in this sandbox.

## Run locally

```bash
# From repository root, with the backend virtual environment activated
python -m uvicorn product.backend.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. Without `OPENAI_API_KEY`, the demo is mock mode;
the UI labels benchmark results accordingly. For a static frontend on port
3000, the UI uses the same hostname's backend on port 8000, or pass an explicit
`?api=https://...` override. The browser frontend does not hard-code a
loopback API for remote/preview use.

## Known limitations

- Mock mode is deterministic and is not a real accuracy measurement.
- Live OpenAI and local Route B voice-clone smoke tests still require the
  owner's provider credentials, model checkpoints, and reference WAV outside
  this repository.
- Local clone is Uzbek-only until a Kazakh voice-lab path is verified.
- Sessions are in-memory; run one uvicorn worker for the demo.

## Out of scope

Do not add datasets, training/fine-tuning, automatic benchmark reruns,
Docker/CI/DB/auth/queues, a frontend framework rewrite, WebSockets, or copied
voice-lab/Seed-VC models. Keep model/reference paths and credentials outside the
repository.

## Remaining release acceptance on Windows/NVIDIA

Use one backend process and the current `master` plus the reviewed fixes.
Keep credentials, checkpoints and the reference WAV outside Git.

1. Start from the repository root; open the served UI on port 8000.
2. With a live provider key, dub a short English phrase into Uzbek, then Kazakh.
   Confirm the transcript/translation, playable audio, actual provider and absence
   of an unexpected MOCK result. Local voice clone remains Uzbek-only.
3. In Uzbek local-clone mode, send two short phrases without restarting.
   Record first and second request wall time, daemon PID/reuse, peak VRAM and
   audible voice quality. Current daemon logs differ from the retired offload
   adapter: do not require `sayro_cache=hit` / `seedvc_cache=hit` markers.
4. Cancel/barge in during a request; verify no stale audio plays, the next turn
   works, temporary uploads are eventually removed and shutdown reaps children.
5. Upload a target-language recording for a frozen benchmark prompt; confirm
   reference/transcript and WER/CER, then load the frozen leaderboard.

These manual checks are pending. CPU mocks do not establish voice quality,
GPU compatibility or real latency. A finished demo requires these results.

## Local completion checkpoint

The local completion branch adds correct WAV duration validation, bounded ffmpeg
normalization, full CPU regression collection, relative wrapper path resolution,
benchmark request ownership and missing-metric handling. The demo now includes
Stop/New session, English-audio upload, WAV download, explicit runtime mode/tool
readiness, stream truncation errors and no-speech handling. Start with
`python product/run_local.py --check`, then `python product/run_local.py`.

Code completion for this checkpoint does not establish real-provider/GPU release
acceptance. The Windows/NVIDIA checklist above remains the final manual gate;
record its actual results before marking the demo released. Commits stay local;
no PR or push is part of this workflow.
