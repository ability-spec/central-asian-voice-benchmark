# BirOvoz — Local Development Guide

Voice AI pipeline for Uzbek (uz) and Kazakh (kk): microphone → STT → LLM → TTS → voice response.

## Requirements

- Python 3.11+
- ffmpeg (must be on PATH — needed for audio normalization)
- OpenAI API key (`gpt-4o-transcribe`, `gpt-4o-mini`, `tts-1`)

## Setup

```bash
# From repo root
cd product/backend

python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# Edit .env and set OPENAI_API_KEY=sk-...
```

## Run

Open two terminals from the repo root:

**Terminal 1 — Backend**
```bash
python -m uvicorn product.backend.main:app --host 127.0.0.1 --port 8000
```

**Terminal 2 — Frontend**
```bash
cd product/frontend
python -m http.server 3000
```

Open http://localhost:3000 in a browser.

> The backend also serves the frontend statically at http://127.0.0.1:8000 — you can skip Terminal 2 and open that URL directly.

## Verify

```bash
curl http://127.0.0.1:8000/health
```

Expected: `{"status":"ok","mock_mode":false,...}`

If `mock_mode` is `true`, the `OPENAI_API_KEY` in `.env` is not being read. Check that the `.env` file is at `product/backend/.env`.

## Usage

1. Click **GO TEST** on the hero screen.
2. Select language (Kazakh or Uzbek).
3. Click the microphone button and speak.
4. Click again to stop recording.
5. The pipeline runs: your speech is transcribed, sent to an LLM, and the response is spoken back.
6. Continue the conversation — up to 20 turns per session. Reload the page to start a new session.

## Prompted benchmark mode

The **Benchmark a recording** panel is optional and does not change the live
English-to-Uzbek/Kazakh dubbing loop. Open it from the app screen, choose a
reference sentence, upload a short recording in the selected target language,
and click **Run benchmark**. The request uses `POST /api/turn` with
`reference_text`, so the result card can show the transcript/reference pair,
WER/CER, stage latency, provider, and an explicit `MOCK` badge when no
`OPENAI_API_KEY` is configured. The frozen leaderboard is loaded read-only from
`GET /api/leaderboard`; it is not recomputed in the browser.

The benchmark panel is intentionally upload-based: it makes the reference
being scored explicit and avoids confusing the English dubbing microphone with
a target-language benchmark recording. Use the selected language's prompts
from `GET /api/prompts?language=uz` or `kk`.

## Logs

Each turn is appended to `logs/turns.jsonl` (relative to the working directory when the server starts):

```json
{"ts":1725200000.123,"request_id":"c7c959ce","conversation_id":"...","language":"uz","turn_number":1,"stt_ms":2890,"llm_ms":3010,"tts_ms":3340,"total_ms":9240,...}
```

## Mock mode

Without an `OPENAI_API_KEY`, the backend returns canned transcripts and a pre-generated WAV beep. Use this to test the frontend flow without spending API credits.

## Route B: reuse Sayro between requests

The vendored wrapper now keeps Sayro loaded in a private worker process. After
each Sayro generation, both the TTS model and its separate speech tokenizer move
to CPU RAM before Seed-VC starts. The next request restores them to the GPU
instead of loading the checkpoint again. The first request remains a cold load.
The reference voice, model, diffusion steps, and generation parameters are unchanged.

This first optimization reuses **Sayro only**. Seed-VC still runs through the
existing CLI in its own environment on every request; no external fork files are
modified. Keeping Sayro in RAM requires several GB of additional resident RAM,
and its CUDA context may retain some GPU memory even while weights are on CPU.
Use one backend process per GPU, without `--workers` or development auto-reload.

`ROUTE_B_PERSISTENT_SAYRO=1` is the default for the vendored wrapper. An external
`SAYRO_SCRIPT` retains the original one-shot behavior. To explicitly select the
vendored wrapper for a Windows test, run from the repository root:

```powershell
$env:SAYRO_SCRIPT = (Resolve-Path .\product\backend\services\routeb\b_sayro_then_seedvc.py).Path
$env:ROUTE_B_PERSISTENT_SAYRO = "1"
.\product\backend\.venv\Scripts\python.exe -m uvicorn product.backend.main:app --host 127.0.0.1 --port 8000
```

Send the same short utterance twice, waiting for the first audio to finish.
Do not restart the backend between requests. Expect `sayro_cache=miss` on the
first request and `sayro_cache=hit` on the second. Logs now report generation,
CPU offload, and total Seed-VC stage time separately. `acquire_s` means a full
load on a cache miss or a RAM-to-GPU restore on a cache hit. Seed-VC stage time
still includes its startup and model loading. Measure actual GPU speed and voice
quality locally; automated tests use model substitutes and do not establish a
latency improvement or CUDA compatibility for the installed model version.

Timeouts and failed requests discard the worker; a later request creates a fresh
one. Normal backend shutdown also closes the worker. The existing TTS fallback
still applies to a failed request and is logged with `FALLBACK`.

To restore the original lifecycle, stop the backend, set
`$env:ROUTE_B_PERSISTENT_SAYRO = "0"`, and restart it. No model reinstallation is
needed. These PowerShell environment overrides affect this terminal session;
put the chosen values in `product/backend/.env` to retain them for later sessions.

## Optional Seed-VC reuse

`ROUTE_B_PERSISTENT_SEEDVC=1` additionally keeps Seed-VC V2 in a second worker
using `SEEDVC_PYTHON`. It requires the vendored wrapper and persistent Sayro mode.
The default is `0` so an existing installation can compare this separately.
V1 continues to use its original CLI. The Seed-VC checkout is never overwritten:
the adapter imports the installed `inference_v2.py` and calls its existing
`load_v2_models(args)` and batch `main(args)` with the same quality arguments.
Compatibility tests use the project owner's supplied script snapshot under
`tests/fixtures/seedvc_inference_v2.py`; that snapshot is not used at runtime.

After each conversion, registered model parameters/buffers and tensor caches
stored directly in module attributes (including list/dict/tuple containers) move
to CPU before the worker acknowledges completion. Sayro and Seed-VC therefore
take turns on the GPU. Both model sets remain in host RAM; additional RAM and
both retained CUDA contexts must fit on the laptop. Arbitrary tensors hidden in
custom Python objects or external module globals are not managed by the adapter.
GPU memory consumption and speed must be verified with the installed fork.

Stop the backend before updating, then from the repository root in PowerShell:

```powershell
git pull --ff-only origin fix/route-b-diffusion-cli
$env:SAYRO_SCRIPT = (Resolve-Path .\product\backend\services\routeb\b_sayro_then_seedvc.py).Path
$env:ROUTE_B_PERSISTENT_SAYRO = "1"
$env:ROUTE_B_PERSISTENT_SEEDVC = "1"
.\product\backend\.venv\Scripts\python.exe -m uvicorn product.backend.main:app --host 127.0.0.1 --port 8000
```

Send the same short phrase twice without restarting. Expect both
`sayro_cache=hit` and `seedvc_cache=hit` on the second request. New logs separate
`seedvc_acquire_s`, `seedvc_conversion_s` (including reference preprocessing and
WAV writing), and `seedvc_offload_s`. `seedvc_total_s` includes adapter startup
on the first request. No first-request or warm-request speedup is guaranteed by
CPU-only tests; compare measured times and confirm that your voice is preserved.

Failures/timeouts discard both workers through the outer process tree. Existing
TTS fallback still applies to that failed request. To keep the working Sayro
optimization but disable Seed-VC reuse, stop the backend, set
`$env:ROUTE_B_PERSISTENT_SEEDVC = "0"`, and restart. Restart after changing model
configuration, dependencies or checkpoint files. Compiled graphs are not
supported by this CPU-offloading adapter. Reference preprocessing remains under
the external fork's control; this change does not add a new reference cache.

## Supported languages

| Code | Language | STT model | LLM | TTS |
|------|----------|-----------|-----|-----|
| `uz` | Uzbek | gpt-4o-transcribe (prompt="Uzbek") | gpt-4o-mini | tts-1/alloy |
| `kk` | Kazakh | gpt-4o-transcribe (prompt="Kazakh") | gpt-4o-mini | tts-1/alloy |
