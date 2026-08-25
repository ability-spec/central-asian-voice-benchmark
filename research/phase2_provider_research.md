# Phase 2 STT Provider Research
**Date:** 2026-08-24
**Status:** Research only. No API calls made. No money spent.
**Source:** Official documentation fetched 2026-08-24. Prices and language support subject to change.

Evidence labels: CONFIRMED = verified from official docs this date. CLAIMED = provider assertion not yet tested. NEEDS_VERIFICATION = documentation was unclear or inaccessible.

---

## Candidate Evaluation Summary

| Provider | Uzbek | Kazakh | AUTO | HINT | Verdict |
|---|---|---|---|---|---|
| Google Gemini API | NEEDS_VERIFICATION | NEEDS_VERIFICATION | Prompt-only | Prompt-only | CONDITIONAL |
| ElevenLabs Scribe v2 | CONFIRMED listed | CONFIRMED listed | CONFIRMED | CONFIRMED | INCLUDE |
| Deepgram Nova-3 | CONFIRMED NOT supported | CONFIRMED NOT supported | N/A | N/A | REJECT |
| Google Cloud STT (Chirp) | CONFIRMED uz-UZ | CONFIRMED kk-KZ | CLAIMED | CONFIRMED | INCLUDE |
| Azure Speech Services | CONFIRMED uz-UZ | CONFIRMED kk-KZ | CLAIMED | CONFIRMED | INCLUDE |

---

## Provider 1: Google Gemini API

### Model IDs
Documentation examples use `gemini-3.7-flash` as the current model. Also available: `gemini-2.5-flash`, `gemini-2.5-flash-lite`, `gemini-2.5-pro`. Model `gemini-2.0-flash` is listed as deprecated.

### Language Support
**Uzbek:** NEEDS_VERIFICATION — the audio API documentation lists no supported language inventory. No language codes are documented.
**Kazakh:** NEEDS_VERIFICATION — same reason.

The API does not have a formal language parameter. Language instructions are passed as free-text in the prompt (e.g. "Transcribe this audio in Uzbek"). Whether the model reliably honours this for low-resource languages is untested.

### AUTO / HINT Mechanism
No dedicated `language` API parameter exists. Both AUTO (no instruction) and HINT (explicit language name in prompt) are prompt-level, not parameter-level. This asymmetry must be documented in benchmark conditions.

### Audio Format Requirements
- Supported: WAV (`audio/wav`), MP3 (`audio/mp3`), AIFF (`audio/aiff`), AAC (`audio/aac`), OGG Vorbis (`audio/ogg`), FLAC (`audio/flac`)
- Token rate: 32 tokens per second of audio (1 minute = 1,920 tokens)
- Downsampled internally to 16 kbps
- Multi-channel combined to mono
- Max duration: 9.5 hours per prompt
- Max inline size: 20 MB total request (use File API for larger files)

### Pricing
Audio billed per input token at 32 tokens/second.

| Model | Audio input price | Effective per audio-minute |
|---|---|---|
| gemini-2.5-flash | $1.00 / 1M tokens | ~$0.00192 / min |
| gemini-2.5-flash-lite | $0.30 / 1M tokens | ~$0.000576 / min |
| gemini-3.1-flash-lite | $0.50 / 1M tokens | ~$0.00096 / min |

*Note: model naming convention from pricing page may differ from API parameter names. Verify model IDs against current `https://ai.google.dev/gemini-api/docs/models` before any call.*

### Rate Limits
Not published on the documentation pages. Dynamic per account tier. Must be checked at `aistudio.google.com/rate-limit` after account setup.

### Research Use / Output Storage
Terms do not prohibit publishing benchmark results derived from API outputs. No claim of ownership over generated content. Standard caution applies: do not submit reference audio as training data.

### Benchmark Risk
MEDIUM. Language support for Uzbek/Kazakh is unverified from official documentation — the audio docs list no language inventory. The prompt-only language mechanism makes HINT condition non-standard and not comparable to providers with formal language parameters. Requires a smoke test before pilot inclusion.

---

## Provider 2: ElevenLabs Scribe v2

### Model IDs
- `scribe_v2` — batch (asynchronous)
- `scribe_v2_realtime` — streaming (not applicable for this benchmark)

### Language Support
**Uzbek:** CONFIRMED listed. Accuracy tier: "Good" (>10–≤20% WER on internal evaluation).
**Kazakh:** CONFIRMED listed. Accuracy tier: "High Accuracy" (>5–≤10% WER on internal evaluation).

Full supported language list (90+ languages) includes: Uzbek, Kazakh, Russian, Kyrgyz, Turkish, and all major European languages. Accuracy tiers are provider-claimed, not independently verified.

### AUTO / HINT Mechanism
- Parameter name: `language_code`
- Format: ISO-639-1 (two-letter) or ISO-639-3 (three-letter)
- Uzbek hint: `language_code="uz"` (ISO-639-1) or `language_code="uzb"` (ISO-639-3)
- Kazakh hint: `language_code="kk"` (ISO-639-1) or `language_code="kaz"` (ISO-639-3)
- AUTO: omit `language_code` (null default triggers auto-detection)
- CONFIRMED: both AUTO and HINT are supported via formal parameter

### Audio Format Requirements
- Accepted format code: `pcm_s16le_16` (16-bit PCM, 16 kHz, mono, little-endian) or `other`
- Minimum duration: 100 ms
- Maximum file size: 5.0 GB (upload), 2 GB (cloud_storage_url)
- WAV/PCM at 16 kHz mono is directly compatible with our frozen benchmark format

### Pricing
API usage is billed in USD, not credits. The credit system applies to bundled plan allowances only.

| Tier | Rate | Evidence |
|---|---|---|
| PAYG and all subscription tiers | **$0.22/hour = $0.00367/min** | CONFIRMED from `elevenlabs.io/pricing/api` 2026-08-24 |
| Entity detection add-on | +$0.07/hr | CONFIRMED |
| Keyterm prompting add-on | +$0.05/hr | CONFIRMED |

*Prior estimate of $0.054/min was based on a credit-cost calculation and was incorrect by ~15×.*

### Rate Limits
Concurrency for `scribe_v2` batch: `min(4, ceil(audio_duration_secs / 480))`. Files over 8 minutes are chunked into up to 4 parallel segments.

### Output Storage
Default: ElevenLabs logs requests and transcripts. To disable: `enable_logging=false` (zero retention mode — enterprise customers only). For non-enterprise use, outputs are logged server-side. This must be disclosed in the benchmark.

### Research Use / Output Storage
No documented prohibition on publishing transcription results. Terms NEEDS_VERIFICATION for research use clause.

### Benchmark Risk
LOW for inclusion. Language support is confirmed. Standard API parameter for language hint. Zero-retention limitation affects data handling policy (must be noted in published results).

---

## Provider 3: Deepgram

### Models
Nova-3 (current), Nova-3-general, Nova-3-medical; Nova-2 (legacy variants).

### Language Support
**Uzbek:** CONFIRMED NOT SUPPORTED. Not present in any model documentation, language list, or API docs.
**Kazakh:** CONFIRMED NOT SUPPORTED. Same finding.

Nova-3 multilingual mode covers: English, Spanish, French, German, Hindi, Russian, Portuguese, Japanese, Italian, Dutch. Neither Uzbek nor Kazakh is listed.

### Pricing (for reference)
- Nova-3 pre-recorded (PAYG): $0.0043/min
- Nova-3 pre-recorded (Growth plan): $0.0036/min

### Verdict: REJECT
Deepgram does not support Uzbek or Kazakh. Including it would require testing in a language the model does not support, producing no useful benchmark data. Do not include in Phase 2.

---

## Provider 4: Google Cloud Speech-to-Text (Chirp)

### Model IDs
Three active Chirp models with regional availability:

| Model | Region(s) | uz-UZ | kk-KZ |
|---|---|---|---|
| `chirp` | asia-southeast1, europe-west4 | CONFIRMED | CONFIRMED |
| `chirp_2` | asia-southeast1, europe-west4 | CONFIRMED | CONFIRMED |
| `chirp_3` | eu | CONFIRMED | CONFIRMED |

No `latest_long`, `latest_short`, `telephony`, or standard model variants support uz-UZ or kk-KZ.

### AUTO / HINT Mechanism
- Language hint parameter: `language_codes` (array, BCP-47 format) — V2 API
- Uzbek hint: `language_codes=["uz-UZ"]`
- Kazakh hint: `language_codes=["kk-KZ"]`
- AUTO (language): `language_codes=["auto"]` — NEEDS_VERIFICATION for uz-UZ/kk-KZ
- `auto_decoding_config` (`AutoDetectDecodingConfig()`): audio format detection only — not language detection

### Audio Format
Standard Google Cloud STT accepts WAV, FLAC, MP3, OGG, and others. WAV PCM 16 kHz mono is supported. NEEDS_VERIFICATION of exact format requirements for Chirp models specifically.

### Pricing
- Chirp models: $0.00035/second = **$0.021/minute**
- Standard models (non-Chirp): $0.006/minute (not applicable — Chirp only for uz-UZ/kk-KZ)
- Free tier: 60 minutes/month for standard models only. Chirp is NOT included in free tier.
- Billing: 15-second increments (minimum 15 seconds per request)

### Rate Limits
NEEDS_VERIFICATION. Not found in fetched documentation.

### Output Storage
Standard GCP terms apply. No documented prohibition on publishing benchmark results.

### Benchmark Risk
LOW-MEDIUM. Language support is confirmed from official language table. `auto_decoding_config` behavior for low-resource languages needs smoke test verification. Regional endpoint selection affects latency and must be consistent across benchmark runs.

---

## Provider 5: Microsoft Azure Speech Services

### Service Name
Azure Cognitive Services — Speech-to-Text (STT)
REST API version: 2024-11-15 (for Fast Transcription)
REST API version: V3.2 (for Batch Transcription)
SDK: `azure-cognitiveservices-speech` (Python) — NOT currently installed in this environment

### Language Support
| Locale | Language | Fast Transcription | Post-stream Refinement | MAI Transcribe-1 |
|---|---|---|---|---|
| `uz-UZ` | Uzbek (Latin, Uzbekistan) | CONFIRMED | Not supported | Not supported |
| `kk-KZ` | Kazakh (Kazakhstan) | CONFIRMED | Not supported | Not supported |

Custom speech for both: plain text customization only (no acoustic model customization).

### AUTO / HINT Mechanism
- Language hint parameter: `speech_recognition_language` (SDK) or `language` (REST)
- Uzbek hint: `speech_recognition_language="uz-UZ"`
- Kazakh hint: `speech_recognition_language="kk-KZ"`
- AUTO detection: Available but requires a candidate language list — true unconstrained auto-detect is CLAIMED, NEEDS_VERIFICATION for whether it works without specifying candidates

### Audio Format
WAV PCM 16 kHz mono is standard Azure Speech input. NEEDS_VERIFICATION of exact supported formats for Fast Transcription endpoint.

### Pricing
- Free tier (F0): 5 audio hours/month (real-time transcription)
- Pay-as-you-go (S1): billed per hour, exact USD amount not rendered in fetched documentation
- Standard real-time: NEEDS_VERIFICATION (approximately $1.00/hour = $0.0167/min based on known historical pricing — verify before use)
- Fast Transcription: NEEDS_VERIFICATION (separate rate)
- Batch: NEEDS_VERIFICATION, not available on free tier

### Rate Limits
NEEDS_VERIFICATION.

### Output Storage
Standard Azure terms. No documented prohibition on publishing benchmark results.

### Benchmark Risk
LOW for inclusion. Language support confirmed. SDK not yet installed — setup required before pilot. Pricing verification required. Auto-detect behavior without candidate list needs confirmation.

---

## Rejected Provider: Deepgram

Deepgram Nova-3 and all legacy models lack Uzbek and Kazakh support. Confirmed from models overview and language documentation. No further evaluation warranted.

---

## Potential Sixth Provider: AssemblyAI

AssemblyAI (Universal-2 model) claims broad multilingual support. Uzbek and Kazakh support: NEEDS_VERIFICATION — not researched in this phase. If the pilot budget allows, a preliminary check is low-cost. Not recommended for inclusion until language support is verified.
