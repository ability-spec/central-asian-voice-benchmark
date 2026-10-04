# BirOvoz — MVP handoff

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

The full historical suite also contains Route B tests for an older settings
shape and async tests that require `pytest-asyncio`; those are documented
compatibility/test-environment issues, not part of this frontend checkpoint.
No real-provider inference or benchmark rerun was performed in this sandbox.

## Run locally

```bash
cd product/backend
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
