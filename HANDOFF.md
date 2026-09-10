# BirOvoz MVP — Handoff

## HEAD / branch
- Workspace: master @ b39acd0 (local; content-duplicate of origin — see note)
- origin/master: 094092c (CP1 live; pushed from Windows via git-am of b39acd0 patch)
- NOTE: local b39acd0 and origin 094092c have IDENTICAL trees (verified empty diff).
  Next commit-bearing step must first export work as patch, then reset local
  master to origin/master to avoid duplicate history. Do NOT merge.

## Completed checkpoints
- CP1 reference-scored POST /api/turn — origin 094092c (workspace: b39acd0).
  reference_text form field; wer/cer/scored + stt/llm/tts/total_ms in response.
- CP2 read-only data endpoints — IMPLEMENTED, UNCOMMITTED, 29/29 tests green.
  GET /api/prompts + GET /api/leaderboard (CSV passthrough, zero recompute).

## MVP status
Done: scored turn API, prompts + leaderboard APIs, pipeline (STT/LLM/TTS + mock),
GO TEST + mic + chat UI. Pending: frontend result card/upload/leaderboard UI
(CP3+CP4), real-key live smoke (CP5). No frontend changes made yet.

## Next checkpoint: CP3 frontend core demo loop
File: product/frontend/index.html ONLY. Add: result card (transcript vs reference,
WER/CER %, latency, provider, MOCK badge when provider_info.mock_mode), API_BASE
same-origin fix (no hardcoded 127.0.0.1). Acceptance: page serves, card renders
from /api/turn JSON shapes, no other files touched, suite still green.

## API contracts (frozen)
- POST /api/turn (multipart): audio*, conversation_id*, language* (uz|kk),
  reference_text (optional, default ""). 200: transcript, response_text, audio
  (b64 wav), turn_number, language, provider_info{stt,llm,tts,mock_mode},
  wer|cer (float|null), scored (bool), stt_ms, llm_ms, tts_ms, total_ms.
  Errors: 400 bad lang/empty audio, 413 oversize/overlong, 429 turn cap (20),
  422 ffmpeg fail, 502 stage fail. No reference -> scored=false, wer/cer null.
- GET /api/prompts?language=uz|kk -> {language, prompts:[{id, sentence,
  duration_s}]} (100 rows, manifest order). 400 bad lang, 422 missing param.
- GET /api/leaderboard -> {rows:[{model, language, condition, n, wer, cer,
  p50_ms, p95_ms, ...}]} (12 rows verbatim; empty cells -> null).

## Important paths
- API: product/backend/main.py, models.py, routers/turn.py, routers/data.py,
  routers/health.py, services/score.py, services/stt.py, services/llm.py,
  services/tts.py, services/session.py, services/log_jsonl.py
- UI: product/frontend/index.html (single file, no framework)
- Data (read-only, never modify): research/phase3a_audio_manifest.csv (200 rows),
  research/final_benchmark_results.csv (12 rows)
- Tests: tests/test_product_api.py. Env file: product/backend/.env (gitignored).
- Patch archive (workspace only, outside repo): /home/user/b39acd0.patch

## Test commands (run from repo root)
- Full suite: python -m pytest tests/test_product_api.py
- CP2 only: python -m pytest tests/test_product_api.py -k "prompts or leaderboard"

## Known quirks
- Mock mode when OPENAI_API_KEY unset: all stages canned, transcript fixed per
  language. Badge it in UI; never present WER as real when mock_mode is true.
- Tests stub routers.turn._to_wav (no ffmpeg in sandbox); audio code untouched.
- Frontend API_BASE hardcoded to http://127.0.0.1:8000 (CP3 fixes it).
- OpenAI live path untested against openai 3.x — CP5 must verify before UI polish.
- Sessions in-memory; single uvicorn worker only (cap/history break otherwise).
- Normaliser quirk (frozen methodology, do not fix): U+2018/U+2019 deleted as
  punctuation and can split words; scores stay comparable with frozen results.
- Pushes happen ONLY from the user's Windows machine (no creds in sandbox).
- Snapshot restores wipe .git/config, so the origin remote + upstream tracking
  can vanish; re-add with remote add + branch --set-upstream-to if missing.

## OUT OF SCOPE (never do without explicit order)
OSS-2, new datasets, fine-tuning/training, new benchmark runs or re-scoring,
autonomous benchmarking, publication/academic work, Docker/CI/DB/auth/queues,
multi-worker tuning, committing data/audio (gitignored by design), frontend
framework rewrite, websockets/streaming, i18n, TurnRequest dead-code cleanup.
