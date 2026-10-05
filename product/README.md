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

## Route B daemon lifecycle

The current backend uses `RouteBDaemonClient` and the vendored wrapper's
`--daemon` JSONL protocol. Sayro and the external Seed-VC V2 daemon stay alive
between requests. The older `ROUTE_B_PERSISTENT_SAYRO` and
`ROUTE_B_PERSISTENT_SEEDVC` settings were removed and have no effect.
The retained cache/offload adapter helpers have independent component tests;
they are not the current backend dispatch path.

From the repository root in PowerShell, after configuring model/interpreter
paths and `SEEDVC_REFERENCE_WAV` in `product/backend/.env`:

```powershell
$env:SAYRO_SCRIPT = (Resolve-Path .\product\backend\services\routeb\b_sayro_then_seedvc.py).Path
.\product\backend\.venv\Scripts\python.exe -m uvicorn product.backend.main:app --host 127.0.0.1 --port 8000
```

Use one backend process per GPU, without `--workers` or auto-reload. Test two
short Uzbek utterances without restarting; compare measured wall time and
check daemon reuse and audible voice preservation. The first call loads models.
CPU tests do not establish a GPU speedup, VRAM fit or external-fork compatibility.

The client retries a failed daemon job once, then falls back to the one-shot
wrapper; TTS provider fallback is reported separately with `FALLBACK`. Shutdown
closes the daemon process tree. Restart after changing settings, dependencies,
checkpoints or reference audio. Seed-VC V1 uses the one-shot fallback path.
See [the handoff](../HANDOFF.md) for remaining release acceptance checks.

## Supported languages

| Code | Language | STT model | LLM | TTS |
|------|----------|-----------|-----|-----|
| `uz` | Uzbek | gpt-4o-transcribe (prompt="Uzbek") | gpt-4o-mini | tts-1/alloy |
| `kk` | Kazakh | gpt-4o-transcribe (prompt="Kazakh") | gpt-4o-mini | tts-1/alloy |

## Test discovery

`python -m pytest -q` from the repository root runs the automated test
directories configured in `pytest.ini`. Standalone research scripts are not
collected: they may initialize API clients or run experiments at import time.

## Daily startup and completed demo controls

With the backend environment activated, run from the repository root:

```bash
python product/run_local.py --check
python product/run_local.py
```

The check is offline. It detects missing Python dependencies, ffmpeg/ffprobe,
mock/live configuration and local clone configuration. It does not verify an
API key, GPU memory, voice quality or installed checkpoints by running models.
The launcher serves frontend and backend together at http://127.0.0.1:8000 and
uses repository-relative runtime directories even when launched elsewhere.

The UI shows MOCK/live configuration and audio-tool readiness. Microphone
recording and **Dub an English recording** share the streaming dubbing flow;
uploads are limited to 30 seconds / 10 MB. **Stop** cancels the browser request,
recording and playback; model work already running on the server may finish
before its files can be safely removed. **New session** also clears local
history and starts a fresh turn counter. Completed replies have **Download WAV**.
Interrupted streams show an error instead of claiming a complete result.
No-speech results stop before translation/TTS. Benchmark scores and the frozen
leaderboard remain separate from live dubbing.
