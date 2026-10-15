# Local Chrome extension — implementation and verification

## Delivered scope

`product/chrome-extension` is a dependency-free Manifest V3 local side-panel
client for the existing English → Uzbek/Kazakh dubbing API. It provides manual
microphone capture, audio upload, explicit live-API consent, ordered NDJSON
playback, Stop, replay, full WAV download, truthful provider/MOCK/fallback labels
and a built-in demo that never calls the backend. UI is Russian, neutral and
responsive. Backend/model files are unchanged by this contribution.

Reference API inspected at master `78c932cfeda680429d6538bd991ccc42c13a9776`.
No direct text-to-speech, page reading, tab audio capture, acoustic barge-in,
public hosting, Google OAuth or Web Store publication is included in this stage.
The README documents setup, permissions, data retention, shared provider state,
cloud cost, cold start and limitations of cancelling already-running GPU work.

## Automated results

- **11 Node protocol/manifest/worker tests passed**, run with
  `node tests/test_chrome_extension.mjs`. Coverage includes split Unicode NDJSON,
  missing/duplicate/out-of-order parts, stream EOF/error handling, cancellation
  of a pending reader, WAV validity, loopback-only origins, actual multipart
  fields, truthful provider labels, minimal manifest permissions and worker
  registration on initial load/install/restart.
- **12 browser scenario groups passed** in Chromium **151.0.7922.173**:
  health and Kazakh limitation; network-free built-in demo and session reset;
  MediaRecorder/WebM capture without auto-upload; multipart/NDJSON playback and
  downloaded WAV bytes; 31-second input rejection; mock→live consent and fallback;
  Stop during processing followed by a new request with no stale callbacks;
  truncated/HTTP/provider error handling; remote URL rejection; settings
  persistence and disconnect gating; provider switching; 390px/300px layouts
  without horizontal overflow.
- No uncaught page errors. JavaScript syntax and Python harness syntax checked.
- **Zero model calls, zero paid API calls.** The test server returns deterministic
  WAVs and fixed transcripts; it does not import STT/translation/TTS providers.

## Validation boundary

Native unpacked extension installation is disabled by the browser administrator
policy in the execution environment. The policy was not changed. Browser tests
therefore serve the actual panel files from loopback, apply the matching CSP and
provide a minimal Chrome storage/tabs API adapter. This does not prove native
side-panel installation, extension-origin networking or physical microphone
permissions on ASUS. Manifest/worker checks are separate Node checks, not a claim
that Chrome accepted the installed extension in this environment.

The user must finish these manual checks on ASUS:

1. Unzip the package; Load unpacked the folder containing `manifest.json`.
2. Click the extension icon: native side panel opens, with no installation errors.
3. Use the built-in demo first: playback, Stop and download, without paid calls.
4. Connect to the already configured localhost backend: health and voice status.
5. Grant microphone permission through the helper tab if necessary; record and
   preview without sending. Confirm microphone capture stops after completion.
6. Only with explicit paid-API authorization, send a short English phrase and
   verify actual provider, sound, Stop and next request. Real GPU/audio quality
   acceptance remains the user's Windows check; previous BirOvoz measurements
   are not presented as measurements of this extension.

## Package

`downloads/BirOvoz-Chrome-Local.zip` is a deliberate user distribution artifact,
not a model/audio/log archive. Its nine files come exclusively from the extension
source folder; no credentials or voice references are included. Regenerate with
`python tools/package_chrome_extension.py`. A SHA-256 checksum is supplied next
to the ZIP. Unpack before Chrome's Load unpacked.
