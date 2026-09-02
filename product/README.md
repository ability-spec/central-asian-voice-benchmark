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

## Logs

Each turn is appended to `logs/turns.jsonl` (relative to the working directory when the server starts):

```json
{"ts":1725200000.123,"request_id":"c7c959ce","conversation_id":"...","language":"uz","turn_number":1,"stt_ms":2890,"llm_ms":3010,"tts_ms":3340,"total_ms":9240,...}
```

## Mock mode

Without an `OPENAI_API_KEY`, the backend returns canned transcripts and a pre-generated WAV beep. Use this to test the frontend flow without spending API credits.

## Supported languages

| Code | Language | STT model | LLM | TTS |
|------|----------|-----------|-----|-----|
| `uz` | Uzbek | gpt-4o-transcribe (prompt="Uzbek") | gpt-4o-mini | tts-1/alloy |
| `kk` | Kazakh | gpt-4o-transcribe (prompt="Kazakh") | gpt-4o-mini | tts-1/alloy |
