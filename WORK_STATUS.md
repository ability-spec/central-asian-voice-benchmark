# BirOvoz local demo validation

## 2026-10-12 — baseline
- Working branch: `codex/birovoz-local-demo`, starting HEAD `47e092f`.
- Existing `voice_clone.py` deletion and all untracked files preserved; no staging, reset, clean, push, or external model changes.
- FastAPI entry point: `product.backend.main:app`; frontend served from the same server.
- Backend Python 3.11.16; Sayro Python 3.12.10 / torch 2.6.0+cu124; Seed-VC Python 3.10.11 / torch 2.4.0+cu124. Both model environments report CUDA available outside the sandbox.
- Existing model weights and reference WAV found. Actual wrapper and Seed-VC `--help` checked; both support daemon mode.
- Previous `product/run_local.py --check` failed because this optional file is absent; it is not the application entry point.
- Runtime checks use HF_HUB_OFFLINE=1 and TRANSFORMERS_OFFLINE=1 to prevent model downloads.
- Paid full-voice smoke budget: 0 / 4 used. No quality claims before listening.
- Next: two short Uzbek local-clone runs, memory/process measurements, then server/API and cancellation checks.

## Local synthesis verified
- Added `close_route_b_worker()` after `_shutdown_daemon()` to repair FastAPI shutdown import; preserved the owner's deleted premature alias.
- Added optional `SAYRO_MODEL_PATH` in vendored wrapper. Installed Qwen attempts HF metadata lookup for repository ids even offline; direct existing snapshot path avoids that lookup without downloading or changing external installations.
- Local daemon call `Salom, bugun havo yaxshi.`: cold 48.000 s, repeat 11.453 s; same wrapper PID 17424. Both WAVs saved under ignored `audio_output/demo_validation/`.
- Existing external Seed-VC daemon CLI compatible. No fallback used in these direct daemon calls.
- 131/132 selected tests passed in sandbox; timeout child-kill test took 13.1 s. First outside-sandbox retry encountered pytest temp-directory ACL; retry with a fresh explicit basetemp pending.
- Audible quality/reference identity awaiting user listening; do not call quality validated.
- Paid requests still 0/4. Next: FastAPI stream requests: Uzbek twice, cancellation, Kazakh after cancellation.

## Final measured smoke results
- Four real multipart `/api/turn/stream` requests used the same server without restarting between requests. Input was a free Windows-generated 3.324 s English WAV: `Hello. The weather is good today.`
- Request 1 Uzbek: STT 2644 ms; translation jobs 3751 ms summed; first part 38087 ms; total server 47057 ms, client 47.453 s. Actual TTS `local-clone/sayro-seedvc`, mock false.
- Request 2 Uzbek: STT 1904 ms; translation jobs 1813 ms summed; first part 10954 ms; total server 21770 ms, client 22.187 s. Actual TTS `local-clone/sayro-seedvc`, mock false.
- Request 3: client closed stream after real STT meta at 1.266 s; no audio delivered to that client. Already-started translation/local synthesis tasks continued and finished. Cancellation does not preempt running GPU work; queued jobs are cancellable. There was no `Stream done` for this request.
- Request 4 Kazakh after cancellation: STT 1611 ms; translation jobs 3284 ms summed; first part 4112 ms; total server 5821 ms, client 6.250 s. Actual TTS `openai/tts-1`, mock false. This is the standard voice fallback for unsupported Kazakh, NOT Kazakh local cloning.
- Captured translations: Uzbek `Salom. Bugun ob-havo yaxshi.`; Kazakh `Сәлем. Бүгін ауа райы жақсы.` No subjective translation-quality claim.
- Server wrapper PID 12076 and Seed-VC launcher PID 15552 persisted throughout all 40 memory samples and both completed Uzbek requests. Memory sampling was partial, not a continuous instrumented full-run peak: highest sampled total GPU use 7805 MiB (includes desktop); server process-tree working set 5.311 GiB; private committed bytes 13.283 GiB (not physical RAM). Both models stay resident in this installed daemon implementation; RAM/VRAM headroom is narrow.
- Uzbek WAVs valid mono PCM16 22050 Hz. Direct local runs 3.355 / 2.949 s, normalized RMS 0.0296 / 0.0298; full-request parts also non-silent. These metrics establish valid signal, not audible quality.
- Captured OpenAI Kazakh parts used streaming WAV length placeholders: added `_finalize_pcm_wav` after complete API responses. Offline finalization preserves PCM and yields 0.463 / 1.400 s. New regression passes with a fake streaming response; no extra paid call.
- Browser decoded all six preview WAVs (readyState 4, no media errors). Uzbek playback reached its end; Kazakh playback advanced with paused=false. This verifies browser playability, not human hearing or reference identity.

## Fixes and validation
- Existing owner's modifications and untracked files remain intact. No commit, push, staging, model download, external-checkout modification, or paid-service installation.
- Frontend now explicitly reports OpenAI standard voice when Kazakh is selected with local clone configured.
- Reproduced a stale-audio race: old `Audio.play()` rejection / ended/error callbacks after barge-in could erase the next playback. Added ownership guards and detached old error handler. Regression exercises actual page functions with delayed audio callbacks; stream aborted, old audio paused, next capture started, new playback survives.
- Original selected suite: 131 passed / 1 sandbox timeout failure. Timeout test then passed outside sandbox with fresh `--basetemp logs/pytest_timeout_retry` (3.24 s).
- After frontend/TTS fixes: 79 relevant tests passed; WAV regression initially exposed retaining the placeholder frame count, repaired and then passed. New playback-race regression passed. Across these runs all 134 distinct selected/new tests pass. `git diff --check` passes.
- Test commands:
  - `.\product\backend\.venv\Scripts\python.exe -B -m pytest tests/test_local_clone.py tests/test_voice_clone.py tests/test_dub_api.py tests/test_dub2_stream.py tests/test_dub3.py tests/test_dub4_continuous.py tests/test_dub4_recorder_fix.py tests/test_frontend_dub4.py -q -p no:cacheprovider`
  - Timeout retry outside sandbox: same Python, `-m pytest tests/test_local_clone.py::test_run_subprocess_timeout_kills_child -q -p no:cacheprovider --basetemp logs/pytest_timeout_retry`
  - New regressions: same Python, `-m pytest tests/test_frontend_cancel_race.py tests/test_openai_wav.py -q -p no:cacheprovider`
- Paid smoke budget exhausted: 4/4 voice requests submitted. No additional paid requests without explicit approval. Preview playback costs no API calls.
- Runtime logs, WAVs, telemetry and scripts are in ignored `logs/` and `audio_output/demo_validation/`; do not commit them or existing secret backup files.

## Exact launch command (PowerShell, repository root)
```powershell
cd C:\Users\erkin\central-asian-voice-benchmark
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:SAYRO_MODEL_PATH = 'C:\Users\erkin\.cache\huggingface\hub\models--uzlm--sayro-tts-1.7B\snapshots\77a6db76f4e709510b7d479de5e927ab662b3dac'
.\product\backend\.venv\Scripts\python.exe -B -m uvicorn product.backend.main:app --host 127.0.0.1 --port 8000
```
- No reload / multiple workers. Existing `.env` supplies API credentials and external Python/reference paths; never print it.
- Server was restarted after fixes and remains running; current launcher PID stored in `logs/demo_server.pid`. `/health` returns ok, mock false. Do not launch a second server while port 8000 is occupied.
- Live app: http://127.0.0.1:8000/ ; free saved-audio preview: http://127.0.0.1:8001/listen.html . Preview process PID in `logs/demo_audio_preview.pid`.
- Optional preview command: same backend Python, `-m http.server 8001 --bind 127.0.0.1 --directory audio_output/demo_validation`.

## Remaining external/manual validation
- User listening still needed: Uzbek intelligibility, resemblance to enrolled voice, Kazakh pronunciation. Browser playback is not a listening-quality verdict.
- Physical microphone capture and acoustic barge-in (speaker bleed, echo cancellation, VAD thresholds) were not live-tested. Deterministic VAD/recorder/cancellation regressions pass; a real stream cancellation and next real request passed. Do not claim a complete microphone demo acceptance until this manual check.
- To listen without API usage, open the preview and press Play. With approval for further API usage, open the live app, select Uzbek / My voice, speak a short English sentence, interrupt during playback with the mic, then send a fresh utterance; confirm old audio does not resume. Kazakh uses standard voice.
- No further paid tests or automatic resumption scheduled. Next step: user listening and separately approved microphone/barge-in acceptance if desired.

## Baseline freeze — no further paid API calls
- User now prohibits paid API calls. No new optimizations or push before baseline acceptance. Older suggestions involving microphone capture are superseded by this restriction.
- User supplied `10/10` and a screenshot of live English → Uzbek (`I'm going to school right now.` → `Hozir maktabga ketyapman.`). Screenshot shows STT 6.9 s, AI 1.8 s, TTS 37.5 s, whole cycle 46.1 s. It does not identify a saved WAV, its duration, its actual provider, or cancellation behavior. Record 10/10 as an overall user rating; per-file intelligibility/reference similarity await clarification.
- RTF = corresponding TTS wall time / output audio duration. Local TTS times include Sayro + Seed-VC and cold model/startup overhead, not STT/translation. API-part times below exclude logged lock wait; whole-cycle totals and summed parallel task times are NOT per-file TTS times.

| Saved WAV | Duration s | Corresponding TTS s | RTF |
|---|---:|---:|---:|
| uz_local_1.wav | 3.355 | 48.000 | 14.306 |
| uz_local_2.wav | 2.949 | 11.453 | 3.884 |
| api_1_part_0.wav | 1.033 | 33.670 | 32.585 |
| api_1_part_1.wav | 1.916 | 8.980 | 4.688 |
| api_2_part_0.wav | 1.672 | 8.230 | 4.923 |
| api_2_part_1.wav | 2.879 | 10.810 | 3.754 |
| api_4_part_0_final.wav | 0.463 | unknown individually | — |
| api_4_part_1_final.wav | 1.400 | unknown individually | — |
| english_input.wav | 3.324 | not measured | — |

- Kazakh `_final` files contain the same captured PCM as original files with corrected WAV headers. Original streaming-header versions are not separate generation runs and are excluded from duration comparisons. Do not compute RTF from their placeholder frame counts.

### Free manual checklist
1. Open http://127.0.0.1:8001/listen.html; use only saved-audio Play/Pause/seek controls. No API calls are made by this page.
2. Listen to both direct Uzbek WAVs: expected `Salom, bugun havo yaxshi.` Rate intelligibility, resemblance to reference, clicks/cutoffs, loudness and pronunciation separately. Then listen to English→Uzbek parts in order: `Salom.` / `Bugun ob-havo yaxshi.`
3. Listen to finalized Kazakh parts in order: `Сәлем.` / `Бүгін ауа райы жақсы.` Rate pronunciation/intelligibility; these use standard OpenAI voice, not a clone.
4. Pause a saved WAV midway, wait, resume and seek; confirm no overlapping audio. This checks the preview player's controls, NOT BirOvoz barge-in.
5. On the live app, change Uzbek/Kazakh and inspect the provider status without recording. Kazakh must explicitly say OpenAI standard voice. If the already completed reply remains present, `Play again` is local playback. Avoid Retry, Send recording and microphone capture: they can initiate paid requests. If already listening, stop the session by tapping the mic without sending; confirm the label becomes idle.
6. Return ratings as file/group + intelligibility /10 + reference similarity /10 (Uzbek only) + specific artifacts; say explicitly whether Stop/acoustic barge-in was actually tried.

### Cancellation evidence, precisely scoped
- Real HTTP stream closure after STT meta: verified. Next real Kazakh request succeeds; already-running Uzbek model work continued. This did NOT test cancellation during audible playback or immediate next Uzbek synthesis.
- Real page playback-function regression with simulated delayed Audio callbacks: verifies abort, pause, next capture initiation, and immunity of next playback to stale callbacks. It does NOT verify the physical microphone, browser audio device, or acoustic VAD.
- Deterministic recorder/VAD/job-queue tests pass. Actual browser decoding/playback of saved WAVs verified; live Stop/barge-in was not operated during those checks.
- Unverified live scenarios: tap interruption during app playback, speech-triggered barge-in, Stop while STT/translation/TTS is in progress, absence of old audio after a real UI interruption, and a fresh microphone request after that interruption. No new paid tests authorized.
- Next: collect user listening assessments and append them here; baseline remains awaiting those precise ratings and any manual cancellation evidence.

## Local latency diagnostic — baseline accepted by user
- User explicitly froze/accepted baseline and authorized up to three local-only synthesis attempts. Paid API remains prohibited; no quality/diffusion/architecture changes, external-checkout edits or push.
- Temporarily stopped the previously launched BirOvoz process tree to release its resident GPU models for a clean cold-model-load comparison. Server restoration pending at end of diagnostic.
- Temporary diagnostic adapters under ignored `logs/tts_diag/` execute the existing wrapper/Seed-VC source and original CLI arguments, adding scoped wall-clock wrappers around normalization, model loading, generation, subprocess readiness, and WAV saving. External source and production source remain unchanged in this stage.
- Windows memory sampling: process-tree physical working set, private commit, system physical RAM and total device VRAM at approximately 200 ms intervals. Peaks are sampled peaks, not exact CUDA allocator maxima.
- First attempt failed before Sayro generation: a temporary Popen function replacement conflicted with a dependency expecting a class. Diagnostic adapter fixed to retain a Popen subclass. Failure evidence saved as `logs/tts_diag/failed_initialization*.json`.
- Conservatively count that failed initialization against the three-attempt limit: only two remaining local requests will be made, cold and repeat. Direct daemon client has retries disabled and no one-shot/cloud fallback.
- Text unchanged: `Salom, bugun havo yaxshi.`; existing enrolled reference; 15 diffusion steps and all generation settings unchanged. Next: aggregate per-stage timings, RTF, process reuse and sampled memory; restore the idle app without paid requests.

### Completed diagnostic results
- Three attempts total, counting one diagnostic initialization failure. Two successful WAVs, no retries, no one-shot or cloud fallback. STT/translation/API were not invoked.
- Cold means fresh model processes, not a cold disk/OS cache. Repeated output length varies with unchanged stochastic generation; this is not a controlled speedup benchmark.

| Non-overlapping wall-clock stage | Cold, s | Repeat, s |
|---|---:|---:|
| Local serialization queue | 0.000002 | 0.000002 |
| Request setup / outer wrapper startup | 0.138674 | 0.001027 |
| Text normalization | 0.000430 | 0.000643 |
| Sayro import/model load/init | 10.654207 | 0.000002 (cache check) |
| Seed-VC process startup/imports/ready | 2.387653 | 0.000002 (alive check) |
| Seed-VC model load/device/cache init | 9.349211 | 0 |
| Sayro generation, excluding load | 6.834699 | 5.150025 |
| Seed-VC conversion, excluding model load and file save | 7.210939 | 4.490802 |
| Intermediate Sayro WAV save | 0.000948 | 0.000971 |
| Seed-VC WAV save | 0.002168 | 0.001939 |
| Final artifact save | 0.000488 | 0.000585 |
| Final WAV read | 0.000128 | 0.000122 |
| IPC/serialization/polling/unattributed remainder | 0.897870 | 0.480886 |
| Total local-only request incl. artifact save | **37.477416** | **10.127007** |

- Nested timers were subtracted before adding stages: Sayro synthesize includes Sayro load; Seed-VC conversion includes Seed-VC model load; Seed-VC RPC includes subprocess readiness, child load/conversion/save and transport. Import time is already inside startup/load rows, NOT added again. These are function-boundary wall times, not CUDA kernel profiles.
- Queue was uncontended because requests were sequential and the live server was stopped. This does not estimate queue latency under concurrent sentence jobs.

| Successful artifact | WAV duration, s | RTF | Peak sampled tree physical RAM, GiB | Private commit, GiB | Peak sampled system physical RAM, GiB | Peak sampled device VRAM, MiB |
|---|---:|---:|---:|---:|---:|---:|
| audio_output/tts_diag/uz_diag_1.wav | 3.274014 | 11.446933 | 6.103516 | 14.753323 | 14.579773 | 7778 |
| audio_output/tts_diag/uz_diag_2.wav | 2.391655 | 4.234309 | 5.262657 | 13.223164 | 13.726166 | 7773 |

- Sampling approximately 5 Hz; very short peaks may be missed. Process-tree RAM includes driver and Python launcher/runtime processes; private commit is not physical RAM. Device VRAM includes desktop/other consumers. Failed initialization produced no WAV/RTF; peak sampled tree RAM 0.371735 GiB and device VRAM 742 MiB. Its error belonged to the temporary diagnostic adapter, not the production synthesis path.
- Detailed machine-readable evidence: ignored `logs/tts_diag/results_with_stages.json`, `events_*.jsonl`, `memory.json`, `failed_initialization*.json`; WAVs in ignored `audio_output/tts_diag/`.

### Persistence and bottleneck
- Same wrapper launcher PID 29624, actual Sayro runtime PID 15456 and actual Seed-VC runtime PID 2476 for both successes. Sayro load cache-hit false then true; Seed-VC model false then true, no second load event.
- Sayro retains the Qwen3-TTS 1.7B model and its speech tokenizer in its process. Seed-VC retains AR, CFM/diffusion with length regulators, ASTRAL narrow/wide content extractors, CAMPPlus style encoder and the configured vocoder in its child process. AR caches persist. Code also keeps reference-feature tensors in `_target_cache` keyed by reference file fingerprint and settings; unchanged reference permits reuse. Reference-cache hit itself was not separately instrumented.
- Both model sets remain resident; this installed daemon does not CPU-offload between stages. Each source is generated and converted anew. WAV outputs, source content features and actual generation results are not reused as a text-result cache.
- Main first-request bottleneck: model loading/init plus Seed-VC process startup **22.391 s (~59.7% of 37.477 s)**. Including outer request/wrapper startup: **22.530 s (~60.1%)**.
- Main repeated-request cost: actual Sayro generation **5.150 s (~50.9%)**, Seed-VC conversion **4.491 s (~44.3%)**. Text preparation and all WAV writes combined take <5 ms and are not meaningful bottlenecks here. RAM/VRAM headroom remains narrow; no OOM observed in successful runs.

### One proposed small change — not implemented
- Add an explicit optional local warm-up before the first user request, using one short existing phrase through the same persistent daemon, no cloud fallback. This moves model initialization into a visible preparation step and reuses the existing processes/quality settings. It does not accelerate actual generation and does not reduce RAM/VRAM usage.
- Verify in a separately authorized local test: warm-up completes; first user-facing request keeps identical runtime PIDs, records cache hits and near-zero model-load/init stages. Compare TTS latency and RTF with output length reported; anticipated removal is the measured ~22.5 s cold initialization overhead, not a guaranteed fixed total or warm speedup. Do not run another synthesis under the exhausted three-attempt allowance.
- Production source/parameters/external checkouts unchanged during diagnostic. No new optimization installed, no push. Existing source diff remains the previous baseline diff; diagnostic files are ignored runtime artifacts.
- Restored idle FastAPI server; launcher PID 27492 saved in `logs/demo_server.pid`, `/health` ok. No model warm-up, microphone use, paid API request or fallback on restoration. Next: user decision on the single warm-up proposal.

## Explicit load-only warm-up request — capability limitation
- User requests load-only warm-up and explicitly requires reporting first if the existing wrapper cannot load models without synthesis.
- Verified current production wrapper: `SayroModel.load()` can load Sayro without generation, but outer daemon jobs always call `_sayro_to_wav()` and then `SeedVCDaemon.convert()`. There is no warm-up/load-only operation.
- Verified installed external `seed-vc/inference_v2.py`: `load_v2_models(args)` exists, but its JSONL daemon requires `source` and invokes `_save_one()` / `convert_voice_v2()`. Only `convert_voice_v2()` populates persistent `vc_wrapper_v2` via `load_v2_models(args)`. No CLI or daemon job exposes load-only initialization.
- Both `daemon ready` handshakes precede model loading. Existing `sayro_ready`/`seedvc_ready` status booleans check configuration/path availability, not loaded model readiness; they cannot establish the requested warm-up success.
- Consequently stopped at the user-specified capability gate. No source change, warm-up, synthesis, paid API, cloud fallback, process restart, test run or push in this turn. The one authorized post-warm-up local synthesis has not been used.
- Implementing this properly requires a new load-only protocol operation and confirmation from both resident model processes. A repository-owned Seed-VC adapter could invoke the existing `load_v2_models(args)` and retain `vc_wrapper_v2` for subsequent conversions without editing the external project; this is a distinct runtime/protocol change, not a capability of the current wrapper. Not implemented pending user direction at this gate.

## Real browser cancellation/playback verification, no paid API
- User deferred load-only adapter. It remains unimplemented. Local voice UI now says models load on demand / cold start possible, instead of claiming loaded readiness from path checks.
- Offline transport fixture `logs/ui_replay/server.py` serves the actual `product/frontend/index.html` at http://127.0.0.1:8002/ with an explicitly labeled replay panel. It imports no product services/keys and calls no STT, translation, TTS, cloud API or models. Saved `uz_local_1.wav` is repeated 5× in-memory solely to allow enough time to operate Stop. Original files and production audio parameters unchanged.
- Replay processing is a delayed HTTP response, NOT real inference. Microphone recording can be manually exercised on this origin; fixture ignores recording content and returns saved WAV, so it cannot establish STT/translation accuracy.
- Initial real browser inspection proved Stop was unavailable during processing: mic disabled, no Stop control. Added explicit Stop for recording/listening/processing/playback. It discards capture, disables continuous listening, aborts HTTP, clears queued audio, detaches callbacks, pauses current audio, revokes its URL and returns UI to idle. It does not terminate server model computations.
- Reproduced a second race with real frontend functions: an old aborted sendRequest catch/finally reset the next request's processing flag/audio queue. Fixed with stream-controller ownership checks after fetch/read, before events, in error handling and finalization. cancelStream now invalidates the old owner immediately and drops queued parts.
- Browser checks on replay origin:
  1. Processing state displayed an enabled Stop. Stop returned idle, processingInFlight false, queue empty, no audio. Fixture logged `client_disconnected` before any part for that request.
  2. Saved audio genuinely playing (audioPaused false). Stop returned idle, current audio cleared, queue empty; fixture logged client disconnection while delayed stream remained open.
  3. Next replay after processing Stop began playback; next replay after playback Stop completed stream and rendered a reply. No API/model involved.
  4. Reload/new session while saved audio was playing generated a new conversation id, empty chat/queue/audio. After old response delay windows elapsed, no old audio or late reply appeared. A request in the new session completed successfully, with one newly completed audio item; final Stop left idle.
- Verified sessions included `0d8dd162-9f1d-4e23-90cc-be5c2aa14f0b` before reload and `75a406ab-0b6a-49cb-a8d9-fddf42e98c00` after reload. Logs `logs/ui_replay/events.jsonl`, screenshot `logs/ui_replay/stopped-ui.png`. Reload is the app's existing way to create a new conversation; no separate production new-session mechanism added.
- Explicit user-triggered Play again on an already completed reply remains available by design. Stopped in-flight audio is not added to completed-turn storage; automatic resume/late stale responses are suppressed.
- 50 relevant tests passed (7.27 s): frontend cancellation races/Stop behavior, VAD/recorder/continuous flow, sentence playback/stream transport and JS syntax. Command: backend Python `-B -m pytest tests/test_frontend_cancel_race.py tests/test_frontend_dub4.py tests/test_dub4_continuous.py tests/test_dub4_recorder_fix.py tests/test_dub3.py tests/test_dub2_stream.py tests/test_voice_clone.py::test_frontend_inline_script_node_check -q -p no:cacheprovider`. `git diff --check` passes.
- Work changed only detected frontend faults and corresponding regressions. Production backend/model path, quality settings, external projects and prior work preserved. No warm-up adapter, paid request, local synthesis, model download or push.
- Working app on 8000 was not restarted or driven with recording. Browser must reload at an idle moment to pick up updated static frontend. Replay server left running, launcher PID 27188 in `logs/ui_replay/server.pid`; it is separate from working app.

### Cancellation meanings and remaining manual checks
- Playback stop: verified in a real browser with saved audio. HTTP-client disconnection: verified against the delayed replay backend. Fixture coroutine cancellation does NOT prove interruption of GPU computation.
- Real model-computation termination is NOT implemented or claimed. Earlier real cancelled Uzbek request kept computing; Stop only prevents that result from being delivered/played by its cancelled client. New requests may still wait for the shared model lock.
- Physical microphone, acoustic speech-triggered barge-in, speaker echo/bleed and browser capture permissions remain unverified until user's actual report. No fabricated success recorded.
- Free joint check ONLY on http://127.0.0.1:8002/ (check OFFLINE REPLAY banner): start mic and grant access yourself; speak a short phrase and press Send recording or pause; while saved WAV plays, speak to trigger acoustic barge-in; press Stop; repeat with a fresh phrase. Report whether playback stopped, listening resumed, next reply worked, and old audio ever reappeared. This tests real capture/VAD/UI but not recognition/translation.
- Do not use recording/Send/Retry on working origin 8000: it would call configured paid OpenAI STT/translation. No such call authorized. Next: record user's factual microphone/barge-in results here and fix only reproducible faults.

### User manual feedback on offline replay
- User reports: Stop works. They hear only the fixed `Salom, bugun havo yaxshi.` output and could not test their own example.
- Fixed output is intentional on origin 8002: saved-audio replay ignores input contents and performs no STT/translation. This is not evidence of a fault in the live pipeline.
- Record manual Stop as working per user report, without assuming whether it was processing Stop or playback Stop (not specified).
- User-specific speech recognition/translation, acoustic speech-triggered barge-in, successful next capture after interruption, and absence of old audio in that manual scenario remain unconfirmed by the user.
- Paid API prohibition remains in force. No requests, synthesis, restart, code changes, external-project edits or push made in response to this feedback; only this status record updated.

## Stage closed — preliminary manual replay acceptance
- User reports: everything works on OFFLINE REPLAY by their observation. Record as **preliminary manual replay verification only**, without assigning success to individual Stop, microphone, acoustic barge-in, next-request or session-isolation scenarios not separately described by the user. Earlier specific report that Stop works is retained.
- Final branch: `codex/birovoz-local-demo`; original owner's deleted alias and all original untracked files preserved. Final tracked diff: 4 files, 57 insertions / 10 deletions; new regression files `tests/test_frontend_cancel_race.py`, `tests/test_openai_wav.py` and this status document remain untracked. No staging, commit or push.
- Reviewed complete tracked diff and both new regression files. Changes remain limited to local Sayro snapshot override, shutdown compatibility wrapper, PCM WAV finalization, truthful language/cold-start status, explicit Stop, stream ownership and stale-audio guards. No new changes/functions added in this finalization turn. `git diff --check` clean; Git only reports Windows LF/CRLF conversion notices.
- Final regression command (API keys empty in test-process environment; models/API calls substituted): backend Python `-B -m pytest tests/test_local_clone.py tests/test_voice_clone.py tests/test_dub_api.py tests/test_dub2_stream.py tests/test_dub3.py tests/test_dub4_continuous.py tests/test_dub4_recorder_fix.py tests/test_frontend_dub4.py tests/test_frontend_cancel_race.py tests/test_openai_wav.py -q -p no:cacheprovider --basetemp logs/final_regression_20261012`.
- Result: 135 passed, 1 failed solely because an enrollment test asserts its temp config is outside the repository, whereas the chosen basetemp was in logs/. Re-ran ONLY `tests/test_voice_clone.py::test_enroll_happy_path_cleans_temp_and_stores_outside_repo` with a fresh unique OS-temp basetemp outside the repository: 1 passed (1.06 s). All 136 selected tests therefore pass across those two runs. No production/test code adjustment to bypass the assertion. Four FastAPI on_event deprecation warnings remain.
- Evidence: ignored `logs/final_regression_20261012.log`, `logs/final_voice_storage_retry.log`; no new paid/local-model synthesis or server restart during finalization.

### Evidence categories
**Real models / earlier authorized real API smoke:** existing Sayro→Seed-VC Uzbek WAV generation, model process reuse, cold/repeated times and RTF/memory; two English→Uzbek complete requests with actual local-clone provider; English→Kazakh with standard OpenAI TTS, not Kazakh cloning; real stream closure after STT followed by a successful Kazakh request. Already-running cancelled Uzbek GPU work continued. OpenAI calls occurred before the later paid-API ban, not during this finalization. Later latency diagnostic used only local models. Saved WAV browser decoding/playback verified; broad 10/10 user rating retained without inventing per-file scores.

**Replay / automated tests:** actual frontend browser Stop during delayed HTTP delivery and saved-WAV playback; next saved replay requests; new conversation after reload with no old automatic audio/late replies; fixture logs confirm HTTP disconnection. Node regressions cover stale stream/audio callbacks, Stop cleanup, VAD/recorder/sentence-flow behavior. User gives preliminary overall manual replay acceptance; no fabricated per-scenario observations.

**Still unverified / not implemented:** precise user-confirmed physical microphone and acoustic barge-in outcomes; cancellation followed by a fresh real Uzbek model request via the final UI; Stop during real active model stages after these UI fixes; per-file voice resemblance/pronunciation assessment; real paid Kazakh TTS response through the final WAV-fix code (tested offline on its captured response and regression); Kazakh local clone; load-only warm-up; interruption of already-running GPU inference. No additional API calls permitted.

### Next launch and constraints
- Free UI replay, from repository root: `.\product\backend\.venv\Scripts\python.exe -B logs/ui_replay/server.py`; page http://127.0.0.1:8002/ . Its output is intentionally fixed saved audio; no recognition/translation/model/API calls. The script is an ignored local test artifact, not shipped application code.
- Actual app launch remains the PowerShell command documented above (`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, exact existing `SAYRO_MODEL_PATH`, uvicorn `product.backend.main:app` on 127.0.0.1:8000, single worker/no reload). Starting the server makes no cloud call; recording/Send/Retry on that origin invokes configured paid STT/translation and is prohibited without new user authorization.
- Existing servers were still present at finalization (launcher PIDs 27492 app / 27188 replay). Do not launch duplicates on occupied ports. Reload the app only when idle to load changed frontend.
- Cold startup remains; no load-only adapter or warm-up installed. Both model sets stay resident with narrow RAM/VRAM headroom. Local clone is Uzbek-only; Kazakh uses OpenAI standard voice. Stop pauses playback, clears queue and disconnects client, but does not guarantee model-computation termination. In-flight server work may finish and hold the shared model lock.
- Runtime logs, diagnostics, audio, weights, references, keys and existing secret backups must not be committed. No external-project/quality changes and no push. Current stage complete; future work requires a new user request.

## Local commit scope
- User authorized a local commit of stage-owned code/tests/documentation only. Each candidate reviewed; no credential patterns detected in the six selected files. Runtime artifacts, replay server, audio, models, secrets/backups and all originally untracked files excluded.
- Selected paths: `product/backend/services/routeb/b_sayro_then_seedvc.py`, `product/backend/services/tts.py`, `product/frontend/index.html`, `tests/test_frontend_cancel_race.py`, `tests/test_openai_wav.py`, `WORK_STATUS.md`.
- Entire `product/backend/services/voice_clone.py` deliberately excluded: stage-owned shutdown wrapper depends on the owner's initial deletion of a premature alias. Mechanically staging only the added function would retain the problematic alias in the committed tree. Both hunks remain unchanged in the working tree; no owner's change is incorporated into the commit.
- The recorded 136 passing regressions apply to the working tree including the retained local voice_clone fixes. This commit is not claimed to make a fresh checkout independently runnable without resolving that baseline dependency.
- No `git add .`, reset, clean, external edit or push. All six paths are explicitly staged; staged path list/diff checked before committing. Commit hash reported in chat after creation.

## Accepted clean-HEAD recovery and new Uzbek experiment
- Subsequent commits: `29cfc9adf506e9d8fa284b8efed46f53b5d58f5c` preserves the shutdown function; user then authorized original alias deletion, committed alone as `eef98798d75b335858e960f4469aa6d76c3b92a3`.
- Clean detached worktree `logs/head-recovery-eef9879` imported the application solely from HEAD; five no-synthesis shutdown/lifecycle checks passed in 1.46 s, including actual idle Python termination. Existing .env read without copying; cloud keys disabled. Worktree clean afterward. User accepts import/lifecycle recovery, not a repeated full voice pipeline from that worktree.
- Exact backup path `/product/backend/.env.pre-vendored.bak` added once to local `.git/info/exclude`; backup unchanged. Original remaining 22 untracked files preserved.
- User now authorizes optimization: at most six local syntheses / 30 minutes, no API, model downloads, external-project changes or push. Stop retesting and Kazakh clone excluded.
- Experiment started 2026-10-12 19:42 UTC (14:42 Winnipeg); deadline no later than 20:12 UTC. Temporary measurements in ignored `logs/uz_opt_20261012/`, audio in ignored `audio_output/uz_opt_20261012/`.
- Six-request design: cold+repeat baseline (Seed-VC 15 steps, Sayro bfloat16), cold+repeat Seed-VC candidate (10 steps, Sayro bfloat16), cold+repeat Sayro candidate (15 steps, Sayro float16). Each candidate differs from baseline by one setting. Existing text/reference and other knobs unchanged. No combined candidate in this budget.
- Reuse existing diagnostic adapter/function timers and 200 ms RAM/VRAM sampling. Disable daemon retry, use direct local client without one-shot/cloud fallback. Fresh daemon between configurations, same daemon within each pair. Production settings/source unchanged.
- Stopped only previously launched FastAPI tree for uncontended GPU measurement; restore baseline server afterward. Fixed saved-audio replay server remains separate and untouched.
- Quality is pending user listening. Output-length randomness remains; six runs are exploratory comparisons, not statistical proof.

### Six-run results, completed within budget
- Completed exactly 6/6 local synthesis requests, no retries, no one-shot/cloud fallback, no errors or model downloads. Active request span including configuration restarts: 154.51 s; results summarized by 19:45:56 UTC, under four minutes after experiment preparation began. No additional synthesis authorized/performed. No Stop or Kazakh tests repeated.
- Each pair reused actual Sayro/Seed-VC processes. PIDs (wrapper / Sayro runtime / Seed-VC runtime): baseline 20712 / 22784 / 32868; Seed-VC 10 steps 4444 / 24640 / 12368; Sayro float16 25768 / 25524 / 10008. Fresh model processes between configurations; cold means process/model cold, not disk-cache cold.

| Variant | State | Total local TTS s | Sayro generation s | Seed-VC conversion s | Model-load s | WAV s | RTF | Peak tree RAM GiB | Peak device VRAM MiB |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline: 15 steps / bfloat16 | cold | 43.027 | 7.998 | 7.847 | 22.909 | 3.193 | 13.476 | 6.12 | 7826 |
| Baseline: 15 steps / bfloat16 | repeat | 10.696 | 5.399 | 4.826 | 0 | 2.310 | 4.630 | 5.26 | 7845 |
| Seed-VC: 10 steps / bfloat16 | cold | 36.601 | 5.804 | 6.044 | 22.053 | 2.554 | 14.330 | 6.03 | 7839 |
| Seed-VC: 10 steps / bfloat16 | repeat | 8.385 | 4.470 | 3.460 | 0 | 2.229 | 3.762 | 5.05 | 7856 |
| Sayro: 15 steps / float16 | cold | 41.935 | 8.789 | 8.055 | 21.808 | 3.750 | 11.183 | 6.09 | 7861 |
| Sayro: 15 steps / float16 | repeat | 13.111 | 6.902 | 5.449 | 0 | 2.949 | 4.446 | 6.66 | 7858 |

- Stage generation/conversion excludes model loading. Total includes loading, startup, transport and tiny file writes; no STT/translation in any total. Queue uncontended (<0.003 ms). Nested timers are not summed twice. RAM/VRAM maxima sampled ~200 ms; device total includes desktop. Tree RAM is physical working set, not private commit.
- For each row, peak tree private commit GiB: 14.23 / 13.22 / 13.88 / 13.22 / 14.63 / 14.04. System physical RAM peaks GiB: 14.73 / 13.71 / 14.28 / 13.33 / 14.52 / 15.14. Memory headroom is still narrow; no demonstrated memory optimization.
- Separate normalized repeat-stage comparison: baseline Sayro 2.327 s per second of raw audio, float16 Sayro 2.332 (no convincing gain). Baseline Seed-VC 2.089 s per second of converted output, 10-step candidate 1.552 (~25.7% lower in this single comparison). Total repeat latency 10.696→8.385 s (~21.6% lower); total RTF 4.630→3.762 (~18.7% lower). These exploratory differences are not statistical guarantees. Unchanged Sayro also varies between runs; its faster time in the Seed-VC candidate is not attributed to the diffusion-step change.
- Six WAVs are valid non-silent PCM16 mono, 22050 Hz, RMS 0.0300–0.0362. This is a technical container/signal check, NOT a listening-quality or voice-identity verdict.
- Tentative best candidate for listening: Seed-VC 10 steps, Sayro bfloat16. Sayro float16 is not recommended on these measurements. No combined candidate tested; no candidate adopted as production default.
- Saved page http://127.0.0.1:8003/listen.html provides all six output links and three repeat-output players, plus separate raw Sayro players before voice conversion. Browser decoded all six displayed full/raw players with readyState 4 and no media error. User auditory evaluation still pending.
- Artifacts: ignored `logs/uz_opt_20261012/results.json`, `summary.json`, `events_*.jsonl`, `memory.json`, `listen-preview.png`; output WAVs/raw Sayro under ignored `audio_output/uz_opt_20261012/`. The listening page makes no API/model call.
- Restored actual FastAPI with unchanged baseline (15 steps confirmed via `/api/voice/status`, models not preloaded); launcher PID 33832 in `logs/demo_server.pid`. Preview launcher PID 23520. External voice-lab/Seed-VC, .env, quality defaults and production source untouched; only tracked WORK_STATUS.md updated in this experiment. No source-change regression rerun needed; real local outputs verified. No commit/push.
- Next: user listens to baseline vs seedvc10 (and optional float16), supplies intelligibility/voice similarity/artifact notes and selects acceptable setting. Until then baseline remains active and MVP quality acceptance is not declared complete. Six-synthesis allowance exhausted.

## User-approved 10-step profile adoption
- User listened to baseline and seedvc10 and states quality is satisfactory. This is the user's **subjective evaluation of those samples**, not a quality guarantee or invented per-file score. Sayro float16 was not selected.
- BirOvoz Settings default changed from 15 to 10 steps. Updated only the matching ROUTE_B_DIFFUSION_STEPS entry in the untracked local .env to 10 without printing/copying its other fields. Sayro remains bfloat16; all other quality settings and external projects unchanged.
- Previous baseline rollback: stop backend, set `$env:ROUTE_B_DIFFUSION_STEPS = '15'`, then restart the same uvicorn command. For persistent rollback edit only that key in local .env. Existing resident daemon arguments require restart.
- Documented accepted profile and launch/rollback in tracked product/README.md. Configuration regression checks cover default 10 and explicit 10/15 CLI forwarding. Historical CLI tests pin their old 15-step fixture explicitly.
- Validation limited to three sequential local calls using existing text/reference, no retries, one-shot/cloud fallback, STT or translation. Daemon was unloaded at start: one cold plus two repeat calls, NOT three already-warm calls. No extra synthesis to hide the cold start. Diagnostics log actual parsed Seed-VC diffusion_steps and actual Sayro dtype.
- Pending: per-request results, appropriate regressions, restore 10-step server, targeted commit of config/documentation/tests only. Before this change, agent-created local commits were 3a3345b, 29cfc9a, eef9879 (three total).

### Adoption verified
- Exactly three successful direct local calls; first cold, next two repeat. All reported actual parsed Seed-VC args `diffusion_steps=10` and actual Sayro loader `dtype=bfloat16`. No STT, translation, paid API, retries, one-shot/cloud fallback or downloads.
- Persistent PIDs unchanged through all three: wrapper launcher 32784, Sayro runtime 31380, Seed-VC runtime 29060.

| Request | State | WAV duration s | Total local TTS s | RTF | Peak tree physical RAM GiB | Peak device VRAM MiB | Fallback |
|---|---|---:|---:|---:|---:|---:|---|
| 1 | cold | 2.392 | 34.724 | 14.519 | 6.19 | 7801 | no |
| 2 | repeat | 2.635 | 9.241 | 3.506 | 4.97 | 7801 | no |
| 3 | repeat | 3.111 | 10.710 | 3.442 | 5.34 | 7809 | no |

- Total TTS includes process/model startup on cold run, inference, transport and artifact save; no full voice-cycle time mixed in. Sampling ~200 ms; physical RAM is driver/model-process working set, VRAM total includes desktop. These observations are not a guaranteed 22% speedup. Generated WAV lengths and times vary.
- Evidence in ignored `logs/uz_profile10_validation/confirmed_results.json`, `events_*.jsonl`, `memory.json`, `run.log`; WAVs in ignored `audio_output/uz_profile10_validation/`.
- 72 relevant regressions verified across two runs: 71 passed initially; one documentation test rejected a machine-specific absolute Windows path. Replaced it with Join-Path USERPROFILE, then that test passed (1.29 s). No test weakened. Tests cover local-clone CLI/fallback seams, provider status, default 10, explicit 10 and rollback 15, and completed WAV normalization. Cloud clients/models substituted and API keys blank in test process. `git diff --check` passes.
- Regression command: backend Python `-B -m pytest tests/test_local_clone.py tests/test_voice_clone.py tests/test_route_b_profile.py tests/test_openai_wav.py -q -p no:cacheprovider --basetemp <unique OS temp directory>`. Targeted retry: `tests/test_local_clone.py::test_no_absolute_windows_paths_in_tracked_source`.
- Restored working server with 10-step environment override; launcher PID 21308 saved in logs/demo_server.pid. No startup synthesis. Source settings/profile are persisted; local .env is never staged.
- Targeted commit scope: product/backend/config.py, product/README.md, tests/test_local_clone.py, tests/test_route_b_profile.py, WORK_STATUS.md. Prior experiment/quality evidence in this document relates directly to choosing this profile. No secret, model, audio, runtime/replay files or owner's original untracked sources staged. Expected agent-created commit total after this adoption: four.
- Remaining MVP limitations: paid STT/translation prohibited; final full microphone voice pipeline with accepted profile not re-run; detailed physical/acoustic barge-in evidence still preliminary; Kazakh local cloning unsupported; no load-only warm-up or guarantee of stopping running GPU computation; cold start and tight memory headroom persist. User's acceptance applies subjectively to listened baseline/seedvc10 samples, not every possible text. No external changes or push.

## Minimal voice-tool frontend, separate from TTS optimization
- Branch `codex/minimal-voice-interface`, based on accepted profile commit 8648e27. Backend/API/STT/TTS semantics, external projects, 10 steps and Sayro bfloat16 unchanged. No dependencies/framework added, no paid API or model synthesis in this frontend stage.
- Inspected routers/turn.py and voice.py and existing microphone/VAD/stream/player implementation. Current backend supports audio-based chat/dubbing, provider status/switch and enrollment; there is NO direct text-to-speech endpoint. Frontend explicitly says text input is unavailable rather than showing a nonfunctional textarea. Minimal future separate change would be a text/language endpoint invoking the existing TTS service and reporting actual provider; not implemented here.
- Replaced decorative hero/video/entrance effects, external font imports, gradients/glow/glass cards with a light, system-font interface, gray neutrals, dark text and one restrained green action accent. Immediate English dubbing screen, Uzbek default, accessible language/voice toggle labels, one recording action, explicit Stop. Existing hands-free/microphone/barge-in/VAD/stream/queue functions retained.
- Pre-action cost notice remains visible; cold model-load notice does not claim loaded readiness. Kazakh selects standard voice presentation and disables unavailable Uzbek-only local voice; no Kazakh clone claim. Provider details/timings are in result details; MOCK and fallback badges remain visible. Fallback comparison records requested selection per request rather than using a later changed selection. Live session explicitly separated from frozen benchmark.
- Completed results provide native WAV controls, Play again and direct Download WAV blob link. Native controls share current playback ownership and Stop cleanup; result URLs reclaimed on unload. Existing streaming audio starts before later parts, and existing cancellation guards retained.
- Browser found and repaired a new native-player lifecycle bug: Stop detached onended/onerror, so native replay could remain speaking after audio ended. Reattach ownership-guarded callbacks on each native play. Regression proves Stop→native replay→end returns idle. Browser verified ended=true, paused=true, no error, current audio cleared and UI idle after this sequence.

### Verification and boundaries
- Free replay on 8002 serves the actual frontend with labeled saved-audio fixture. Ignored fixture expanded with delay, long-text, error and synthetic fallback cases; it imports no product/cloud services. Its fixed output does not recognize/translate recordings. These cases are UI tests, not new model-quality or latency measurements.
- Real browser: delayed processing Stop, next request, stream playback, native replay, Stop and natural playback completion; error→Dismiss→successful result; synthetic fallback badge and MOCK badge; collapsible diagnostics; download.
- Downloaded `birovoz-1.wav` in local Downloads: valid 16.776 s PCM WAV (saved sample repeated for cancellation window), no API involved. CDP download-event wait timed out, but actual download file existed and was verified; switched UI to a stable direct download link rather than transient anchor. Regression verifies link MIME/source/filename.
- Long replay response ~3915 displayed characters, including literal `<not markup>` safely escaped. At 390px viewport, app/result widths stayed within viewport. An initial whole-page overflow was confined to fixture debug pre; fixture wrapping fixed, production page confirmed innerWidth 390 / document width 375 (scrollbar excluded), no horizontal overflow.
- Keyboard: Tab moved from language to voice control with visible solid focus outline; Return changed Kazakh/Uzbek on the real app without making speech/API requests. Kazakh local voice disabled, standard selected; Uzbek restored. Native controls use browser keyboard behavior. Physical microphone/acoustic barge-in not re-tested; existing deterministic VAD/recorder tests retained.
- Final 83 relevant regressions passed (10.57 s): `tests/test_frontend_voice_ui.py`, `test_frontend_cancel_race.py`, `test_frontend_dub4.py`, `test_dub4_continuous.py`, `test_dub4_recorder_fix.py`, `test_dub3.py`, `test_dub2_stream.py`, `test_voice_clone.py`. No paid/model calls in tests. Four existing FastAPI deprecation warnings. `git diff --check` passes.
- Actual application inspected via GET on 8000 only. Screenshot artifacts (ignored): `logs/frontend_refresh/desktop.png` (1280px), `mobile.png` (390px), `mobile-result.png` (replay result). Temporary viewport overrides reset. UI verification is not a new full paid microphone pipeline acceptance.
- Changes to save: product/frontend/index.html, tests/test_frontend_voice_ui.py, WORK_STATUS.md only. Original untracked files, .env, WAVs, screenshots, runtime logs/fixture code and models excluded. Separate frontend branch/local commit; no push.
- Remaining: direct text TTS needs a separate backend task; real microphone/paid dubbing acceptance needs explicit API permission; running GPU work is not interrupted by Stop; cold startup and memory limitations remain. Frontend work is complete within these boundaries.

## User-approved VoiceLab-inspired workspace composition
- User approved the reference direction and explicitly requested rewriting the frontend. Reworked layout on the separate frontend branch: neutral light workspace, compact BirOvoz header, language/real voice options in the left sidebar, English dubbing/status/session results on the right, recording/Stop controls at the bottom. At <=700px settings move above the workspace. No copied VoiceLab branding, sample voices, gradient backdrop, hero, agents, fake text input or unsupported features.
- Existing microphone/VAD, streaming/queue, cancellation, playback/download, provider/MOCK/fallback logic preserved byte-for-byte as the existing script. Only HTML/CSS composition changed; backend and accepted 10-step/bfloat16 profile untouched. Unsupported text TTS notice, visible paid API notice, cold-start disclosure and frozen-benchmark separation retained.
- Browser verified saved-WAV delayed processing Stop, next replay result, playback Stop, native player/Download link availability. Desktop 1280px and mobile 390px checked: no horizontal overflow (390 viewport / 375 document including scrollbar allocation). Real working tab reloaded while idle; no mic/Send/Retry or speech/API call on live app.
- Thirty targeted regressions passed in 7.56 s: frontend UI/native-player regression, cancellation races, VAD, continuous recording, recorder validity and JS syntax. Script identity assertion additionally confirms logic unchanged. `git diff --check` passes.
- Ignored screenshot artifacts: logs/studio_layout/desktop.png, mobile.png, desktop-replay.png, mobile-replay.png. Temporary viewport reset. No audio/model generation, paid API, external edits or dependencies.
- Local commit scope: product/frontend/index.html and WORK_STATUS.md only; no runtime screenshots/replay/scripts, secrets, models, audio or original untracked files. No push. Current capability limits remain unchanged.
