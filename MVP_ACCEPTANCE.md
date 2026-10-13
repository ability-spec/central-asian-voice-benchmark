# BirOvoz local MVP acceptance

## Scope completed in this checkpoint

A single-machine FastAPI/static HTML demo with English-to-Uzbek/Kazakh dubbing,
optional Uzbek local voice clone, prompted recording benchmarks and a frozen
leaderboard. No new dataset training, public hosting, authentication or
multi-user production system is included.

- Microphone capture: manual and hands-free, existing voice barge-in.
- English recording upload: same streamed dubbing contract as the microphone.
- Streaming: ordered audio parts, truncated/error response detection,
  cancellation, finite browser request lifetime and recovery.
- Stop and New session: recording/playback stop; new turn counter, history and
  replay data cleared. Server inference already running may finish after abort.
- Completed dub: replay and WAV download.
- Benchmark: language-specific reference prompts, upload, WER/CER, latency,
  provider/mock labels, cancellation and JSON result download without audio.
- Leaderboard: frozen source data; absent values are not displayed as zero.
- Audio: duration from real WAV headers, upload/length limits, ffmpeg timeout,
  cleanup and empty-speech rejection before downstream provider calls.
- Offline preflight and launcher; visible mock/live configuration/tool status.

## Evidence from this environment

- Linux/Python 3.12 automated provider/model substitutes; complete suite run.
- JavaScript syntax checked with Node; delayed-response and stream lifecycle
  behaviours exercised under Node substitutes, not a real browser DOM.
- Real ffmpeg normalization of 48 kHz stereo PCM to 16 kHz mono PCM.
- Real FastAPI TestClient + ffmpeg end-to-end in MOCK mode: served frontend,
  health/tools, 100 prompts for each language, streaming dubbing for both
  languages, playable WAV containers, scored benchmark for both languages,
  frozen leaderboard, overlong rejection and empty upload directory afterwards.
- Offline preflight also launched from a directory outside the checkout.
- FastAPI lifespan replaces deprecated startup/shutdown event decorators.

## Final owner acceptance — still pending

1. Import the local branch, activate your Windows backend environment and run
   `python product/run_local.py --check`, then `python product/run_local.py`.
2. Confirm actual browser rendering, microphone permissions, recording,
   autoplay/replay, Stop/New session, English file upload and downloaded WAV.
3. Configure live keys; verify real English -> Uzbek and English -> Kazakh
   transcript, translation and spoken result. Live configuration is not proof
   of API-key validity or speech quality.
4. With your reference WAV and models, verify Uzbek local clone. Measure cold
   and warm time, voice preservation, GPU memory and daemon reuse. Kazakh local
   clone remains unsupported.
5. Cancel during model inference, start another turn, and close the server.
   Confirm no stale audio, eventual file cleanup and subprocess shutdown.
6. Run one live prompted benchmark; inspect reference/transcript, WER/CER,
   provider and exported JSON. Keep frozen research scores separate.

These checks are acceptance work, not a numerical guarantee that only 10% of
engineering remains. A GPU/provider defect may require additional fixes. No
real-provider quality, GPU compatibility or public deployment is claimed.

## Local delivery

Commits are on `local/birovoz-completion`; no PR or push. A self-contained Git
bundle preserves the branch and its history. To import into an existing checkout:

```bash
git fetch /path/to/birovoz-mvp-local.bundle local/birovoz-completion:review/birovoz-mvp
git switch review/birovoz-mvp
```

Review against your own current master before merging. No force push is needed
for these development changes. Removing historical contributor attribution is a
separate history-rewrite task and has not been performed.

## Follow-up reliability changes (uncommitted)

Session history is bounded to 1000 sessions, expires after one hour of idle
time and is protected across worker threads. Unknown-session reads allocate no
storage; returned histories are detached snapshots. The browser finishes on
the terminal stream event without waiting for server EOF. Full suite: 258 passed.
See `PUBLICATION_PLAN.md` for three reviewable patches and gradual publication.

Decoded WAV duration is now rechecked before STT in both endpoints, including uploads whose original container has no duration metadata.

Media cancellation follow-up: obsolete playback callbacks and microphone permission results are ignored after Stop/replacement. Stream cancellation immediately unlocks the next request while old cleanup cannot clear the new request. Full CPU/Node suite: 269 passed; real-browser and live GPU/provider acceptance remains pending.
