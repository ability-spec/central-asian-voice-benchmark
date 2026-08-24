# STT Benchmark Run Configuration

**Date:** 2026-08-23
**Status:** Configuration only. No API calls made. No models run. No benchmark results exist.
**Methodology reference:** `methodology_proposal.md` (STEP 2, Revision 2) — do not modify.
**Scope:** STT only. Translation and TTS phases follow separately.

---

## Frozen Inputs

| Asset | File | SHA-256 | Rows |
|---|---|---|---|
| Uzbek utterance manifest | `research/uzbek_benchmark_manifest.csv` | `61b235f0d33ea57ad8696dfae5146117ddde4965db589762ae48c0c2f0565c70` | 300 |
| Kazakh utterance manifest | `research/kazakh_benchmark_manifest.csv` | `a068cd81c958c687b8239a1bdc73b55586fe98f7a218b8ca51b3fda517c89507` | 300 |
| Audio + transcript master manifest | `research/audio_benchmark_manifest.csv` | `d01408af2e04d048a44600138ac878f97b2a2372f62b9a42f2f7d0b161f34924` | 600 |
| Uzbek WAV files | `benchmark_audio/uzbek/<id>.wav` | — | 300 files |
| Kazakh WAV files | `benchmark_audio/kazakh/<id>.wav` | — | 300 files |

These manifests and audio files are immutable. No utterance may be added, removed, or modified after this point.

---

## Mandatory Benchmark Conditions

Two conditions are required for every provider/model, per STEP 2 Section B3. They are never averaged together and never substituted for one another.

| Condition ID | Description | Language parameter |
|---|---|---|
| `auto` | No language supplied — provider auto-detects | None |
| `hint` | Correct language explicitly supplied | Provider-specific (see Section 4) |

If a provider cannot support `auto` (i.e., requires a language parameter), the `auto` condition is recorded as `N/A — language parameter required` and is excluded from the auto leaderboard. It is never silently dropped.

If a provider cannot support `hint` (i.e., the language code is rejected), the hint mechanism falls back to `prompt="<Language>"` (the language name in English). The exact fallback used is recorded in `language_hint` per-call.

---

## Input Protocol

All models receive identical inputs per STEP 2 Sections B1 and B2.

| Parameter | Value |
|---|---|
| Format | WAV (PCM, 16-bit little-endian) |
| Sample rate | 16,000 Hz |
| Channels | 1 (mono) |
| Max segment duration | 60 s (all 600 utterances already verified under this limit) |
| Loudness normalisation | NONE — prohibited by methodology |
| Preprocessing | NONE — no trimming, noise reduction, or pitch/speed changes |
| File naming | `<utterance_id>.wav` |
| Reference identity | `utterance_id` matches manifest; SHA-256 per file tracked in master manifest |

---

## Provider Registry

### Phase 1 (Ready to run — credentials required)

#### OpenAI — gpt-4o-transcribe

| Field | Value |
|---|---|
| Provider | OpenAI |
| Model ID | `gpt-4o-transcribe` |
| API endpoint | `POST https://api.openai.com/v1/audio/transcriptions` |
| SDK | `openai` Python SDK (installed) |
| Uzbek support | **CONFIRMED WORKING** — both smoke test recordings returned correct Uzbek Latin |
| Kazakh support | **CONFIRMED WORKING** — Kazakh smoke test (2026-08-23): both AUTO and hint returned correct Kazakh Cyrillic |
| Auto-detect | **CONFIRMED** — omitting `language` param triggers auto-detect |
| Language hint — Uzbek | **CONFIRMED** — `prompt="Uzbek"` works; ISO `uz` rejected (HTTP 400 `invalid_value`) |
| Language hint — Kazakh | `prompt="Kazakh"` — **CONFIRMED WORKING** (AUTO had one-word error "Қазіргі"; hint corrected to exact match "Қазір") |
| Timestamps available | **CONFIRMED** — word-level timestamps NOT available (verbose_json rejected by API with HTTP 400); segment-level via whisper-1 only |
| response_format | **CONFIRMED** — `verbose_json` is **REJECTED** (HTTP 400 `unsupported_value`); must use `json` or `text`. Internal model version: `gpt-4o-transcribe-api-ev3`. |
| provider_detected_language | **UNAVAILABLE** — `json` format does not return a `language` field; will be NULL for all gpt-4o-transcribe calls |
| Pricing | **CONFIRMED** — $0.006/min (audio) + $10.00/1M output tokens; 87 audio_tokens ≈ 8.8s audio (source: developers.openai.com/api/docs/pricing, 2026-08-23) |
| Evidence source | `uzbek_stt_smoke_test.md`, `kazakh_stt_smoke_test.md` |

#### OpenAI — gpt-4o-mini-transcribe

| Field | Value |
|---|---|
| Provider | OpenAI |
| Model ID | `gpt-4o-mini-transcribe` |
| API endpoint | Same as gpt-4o-transcribe |
| Uzbek support | **CONFIRMED INCONSISTENT** — Recording 1 PASS (correct Uzbek Latin), Recording 2 FAIL (Uyghur Arabic script). Not suitable as primary; include as comparison baseline. |
| Kazakh support | **CONFIRMED FAIL (Kazakh)** — Kazakh smoke test (2026-08-23): both AUTO and hint returned Kyrgyz Cyrillic, not Kazakh. Kyrgyz-specific forms ("Азыр", "болгон", "кызмат") vs. expected Kazakh ("Қазір", "болған", "қызмет"). Hint has no effect on language confusion. |
| Auto-detect | **CONFIRMED** — same mechanism as gpt-4o-transcribe |
| Language hint — Uzbek | `language="uz"` rejected (HTTP 400 `invalid_value`); `prompt="Uzbek"` tested but produced inconsistent results |
| Language hint — Kazakh | `prompt="Kazakh"` — **CONFIRMED SENT, CONFIRMED INEFFECTIVE** — hint accepted (no API error) but output remains Kyrgyz |
| response_format | **CONFIRMED** — `verbose_json` REJECTED (HTTP 400 `unsupported_value`); must use `json` or `text`. Internal model version: `gpt-4o-mini-transcribe-api-ev3`. |
| provider_detected_language | **UNAVAILABLE** — same as gpt-4o-transcribe; NULL for all calls |
| Pricing | **CONFIRMED** — $0.003/min (audio) + $5.00/1M output tokens (source: developers.openai.com/api/docs/pricing, 2026-08-23) |
| Evidence source | `uzbek_stt_smoke_test.md`, `kazakh_stt_smoke_test.md` |
| Benchmark phase | Phase 1 — include as comparison baseline; CONFIRMED FAIL on both Uzbek (inconsistent) and Kazakh (wrong language) |

#### OpenAI — whisper-1

| Field | Value |
|---|---|
| Provider | OpenAI |
| Model ID | `whisper-1` |
| API endpoint | Same as gpt-4o-transcribe |
| Uzbek support | **CONFIRMED FAIL** — both recordings returned Kazakh Cyrillic |
| Kazakh support | **CONFIRMED WORKING** — Kazakh smoke test (2026-08-23): all three conditions returned correct Kazakh Cyrillic; `language="kk"` accepted |
| Auto-detect | **CONFIRMED** — omitting `language` triggers auto-detect; correctly identifies and transcribes Kazakh |
| Language hint — Uzbek | `language="uz"` rejected (HTTP 400 `unsupported_language`) |
| Language hint — Kazakh | `language="kk"` — **CONFIRMED ACCEPTED** — no HTTP 400; detected="kazakh"; identical transcript to AUTO |
| response_format | **CONFIRMED** — `verbose_json` supported and returns `language`, `segments`, `duration`, `usage` |
| provider_detected_language | **AVAILABLE** via `verbose_json` — returns `"kazakh"` for Kazakh audio |
| Pricing | **CONFIRMED** — $0.006/min audio, no per-token rate (source: developers.openai.com/api/docs/pricing, 2026-08-23) |
| Evidence source | `uzbek_stt_smoke_test.md`, `kazakh_stt_smoke_test.md` |
| Benchmark phase | Phase 1 — negative baseline for Uzbek; CONFIRMED WORKING for Kazakh |

### Phase 2 (Credentials not yet configured)

#### Google Cloud STT — Chirp 2 / Chirp 3

| Field | Value |
|---|---|
| Provider | Google Cloud |
| Model IDs | `chirp_2`, `chirp_3` |
| API | Google Cloud Speech-to-Text v2 |
| SDK | `google-cloud-speech` (installed, no credentials) |
| Uzbek support | **CLAIMED** — Google documentation claims Chirp supports 100+ languages including Uzbek |
| Kazakh support | **CLAIMED** — same documentation claim |
| Language hint | `languageCode: "uz-UZ"` / `"kk-KZ"` — NEEDS VERIFICATION (exact codes for Chirp v2) |
| Auto-detect | **CLAIMED** — `auto_decoding_config` available in v2 API |
| Pricing | **NEEDS VERIFICATION** |
| Blocker | No GCP credentials configured (`GOOGLE_APPLICATION_CREDENTIALS` not set) |

#### Azure Speech Services

| Field | Value |
|---|---|
| Provider | Microsoft Azure |
| Service | Cognitive Services Speech-to-Text |
| SDK | `azure-cognitiveservices-speech` — NOT installed |
| Uzbek support | **CLAIMED** — NEEDS VERIFICATION against current Azure language list |
| Kazakh support | **CLAIMED** — NEEDS VERIFICATION |
| Language hint | `speech_config.speech_recognition_language = "uz-UZ"` / `"kk-KZ"` — NEEDS VERIFICATION |
| Auto-detect | **CLAIMED** — Azure supports multi-language auto-detect with a candidate list |
| Pricing | **NEEDS VERIFICATION** |
| Blocker | No Azure subscription key; SDK not installed |

### Excluded from Phase 1 (Confirmed Fail)

| Provider | Model | Reason | Re-test in later phase? |
|---|---|---|---|
| AWS Bedrock | `mistral.voxtral-mini-3b-2507` | CONFIRMED FAIL (Uzbek, smoke test) | Optional — if Mistral releases a Turkic-language update |
| AWS Bedrock | `mistral.voxtral-small-24b-2507` | CONFIRMED FAIL (Uzbek, smoke test) | Optional — same condition |

Both Voxtral models may be re-included if Mistral announces explicit Uzbek/Kazakh support, or as confirmed-negative baselines in a supplementary table.

### Phase 3 (Open-source / local — not yet scheduled)

| Model | Source | Uzbek | Kazakh | Blocker |
|---|---|---|---|---|
| Whisper large-v3 | HuggingFace (OpenAI) | CLAIMED | CLAIMED | GPU required; checkpoint SHA must be pinned |
| Faster-Whisper large-v3 | HuggingFace (Systran) | CLAIMED | CLAIMED | Same weights as above; different runtime |
| Meta MMS | HuggingFace (Meta) | **CLAIMED** (explicit Uzbek + Kazakh) | **CLAIMED** | GPU preferred; pip install required |
| Wav2Vec2 fine-tunes | HuggingFace (community) | UNKNOWN (survey required) | UNKNOWN | Must identify and pin specific checkpoint SHAs |
| NVIDIA NeMo | NVIDIA NGC | CLAIMED | CLAIMED | GPU required; framework verification needed |

Open-source models run on a separate leaderboard per methodology Section G2. Hardware spec and checkpoint SHA are mandatory metadata per run.

---

## Language Hint Mechanisms (Confirmed and Provisional)

| Provider | Model | HINT mechanism — Uzbek | HINT mechanism — Kazakh | Evidence |
|---|---|---|---|---|
| OpenAI | gpt-4o-transcribe | `prompt="Uzbek"` (ISO `uz` rejected) | `prompt="Kazakh"` — **CONFIRMED WORKING** | Kazakh smoke test 2026-08-23: hint corrected AUTO error |
| OpenAI | gpt-4o-mini-transcribe | `prompt="Uzbek"` (ISO `uz` rejected) | `prompt="Kazakh"` — **CONFIRMED SENT, INEFFECTIVE** | Kazakh smoke test: hint accepted but Kyrgyz output unchanged |
| OpenAI | whisper-1 | ISO `uz` rejected; no working hint | `language="kk"` — **CONFIRMED ACCEPTED** | Kazakh smoke test: HTTP 200; detected="kazakh"; identical to AUTO |
| Google Cloud STT | chirp_2 / chirp_3 | `languageCode="uz-UZ"` | `languageCode="kk-KZ"` | NEEDS VERIFICATION |
| Azure | Speech STT | `speech_recognition_language="uz-UZ"` | `speech_recognition_language="kk-KZ"` | NEEDS VERIFICATION |

**ISO code reference:**
- Uzbek: ISO 639-1 `uz`, BCP-47 `uz-UZ` (Latin script used in modern Uzbekistan)
- Kazakh: ISO 639-1 `kk`, BCP-47 `kk-KZ` (Cyrillic script used in Kazakhstan)

Script note: Both benchmark reference sets use their canonical scripts (Uzbek Latin, Kazakh Cyrillic). A model that produces correct output in the wrong script scores 100% WER on cross-script comparison. Script accuracy is tracked separately (Section 7).

---

## Output Schema

One JSON record per API call. Field names are identical to `methodology_proposal.md` Section E1. All fields are required; `null` is valid for unavailable optional fields.

```
{
  "run_id":                     string (UUID),
  "call_id":                    string (UUID),
  "timestamp_utc":              string (ISO 8601),
  "provider":                   string,
  "model":                      string,
  "model_version":              string | null,
  "client_region":              string,
  "api_region":                 string | null,
  "audio_id":                   string,
  "audio_sha256":               string,
  "audio_duration_s":           float,
  "audio_format":               "wav_16k_mono_pcm16",
  "corpus_source":              string,
  "contamination_risk":         "MEDIUM",
  "language_condition":         "auto" | "hint",
  "language_hint":              string | null,
  "prompt":                     string | null,
  "response_format":            string,
  "raw_transcription":          string | null,
  "normalized_transcription":   string | null,
  "provider_detected_language": string | null,
  "independent_detected_language": string | null,
  "dominant_script":            string | null,
  "latency_ms":                 integer,
  "http_status":                integer,
  "error_type":                 string | null,
  "error_message":              string | null,
  "retry_count":                integer,
  "cost_usd":                   float | null,
  "cost_list_price_usd":        float | null,
  "sdk_version":                string,
  "benchmark_version":          "1.0"
}
```

**Immutability rule (from methodology E2):** A written record is never modified. Corrections produce new records with `supersedes_call_id` pointing to the original.

**Raw output preservation:** The full provider JSON response is stored alongside the flat record (see directory structure below). The `raw_transcription` field contains the transcript text only. The `provider_response_raw` file contains the complete response object.

---

## Evaluation Metrics

All metrics are calculated post-transcription on stored results. No metric is computed during the API call.

### WER and CER (methodology C1, C2)

```
WER = (S + D + I) / N
CER = same formula at Unicode code-point level
```

Applied to `normalized_transcription` only (see normalisation below). Tool: `jiwer`.
Cross-script outputs are included and score near 100% WER — that is the correct result.

### Normalisation pipeline (methodology C6 — exact order, no deviation)

1. Unicode NFC normalisation
2. Unicode-aware casefold (`str.casefold()`)
3. Apostrophe normalisation: U+02BB, U+2018, U+2019, U+0060, U+00B4 → U+0027
4. Punctuation removal: period, comma, question mark, exclamation mark, colon, semicolon, ellipsis, em-dash, en-dash at word boundaries
5. Whitespace normalisation: collapse all Unicode whitespace to single ASCII space; strip leading/trailing
6. **No cross-script transliteration** — Cyrillic output against Latin reference scores high WER as designed

Reference transcripts are also normalised through the same pipeline before scoring. Original reference transcripts are never modified.

### Script accuracy (methodology C3)

Dominant script classification of raw output by Unicode block. Script is dominant if ≥70% of non-whitespace alphabetic characters belong to that block. Labels: `latin`, `cyrillic`, `arabic`, `mixed`, `other`, `empty`.

```
Script_accuracy = outputs with correct script / total non-null outputs
```

Expected scripts: Uzbek → `latin`; Kazakh → `cyrillic`.

### Language accuracy — two separate sub-metrics (methodology C4)

**A. Provider LID accuracy** (`lang=auto` condition only):
```
Provider_LID_accuracy = (provider detected_language matches reference) / (calls with non-null detected_language)
```
Providers that never return `detected_language` receive `N/A`, not zero.

**B. Output language accuracy** (all conditions, independent LID tool):
```
Output_language_accuracy = (independent LID matches reference) / (non-null, non-empty outputs)
```
Outputs below 10 words are flagged separately; short texts are unreliable for automatic LID.

Independent LID tool: **CONFIRMED SELECTED — `fasttext` with lid.176.bin model**.
- pip package: `fasttext-wheel==0.9.2`
- Model: `lid.176.bin` (176-language model from dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.bin, ~128 MB)
- Both `uz` (Uzbek) and `kk` (Kazakh) confirmed present in lid.176 language list — source: fasttext.cc language identification docs, 2026-08-23
- `langdetect` DISQUALIFIED: insufficient language coverage (does not include both uz and kk)
- `lingua==2.2.0` DISQUALIFIED: Uzbek not supported (75 languages, kk included but uz absent)
- Model hash must be recorded in run metadata before first call (pin after download)

These two sub-metrics are always reported in separate columns. They are never collapsed into one score.

### Language confusion matrix (methodology C5)

Per model, `lang=auto` condition only. Shows what language the model produced for each reference language. Minimum useful matrix: rows = {Uzbek, Kazakh}, columns = {Uzbek, Kazakh, Other}. The whisper-1 Uzbek→Kazakh conflation in the smoke test is exactly what this matrix reveals.

### Hallucination taxonomy (methodology C7 — four types, exact definitions preserved)

| Type | Signal | Detection method |
|---|---|---|
| Silence hallucination | Non-empty output when audio is near-silent | Automatic: RMS energy below calibrated threshold (threshold NEEDS CALIBRATION on a pilot set) |
| Excessive output | Word count > 3× expected for duration (at 2.5 words/s) | Automatic flag; human review required to confirm |
| Unrelated-language output | Output in non-Turkic language for Central Asian audio | Semi-automatic: Output LID returns a non-Turkic language |
| Semantic hallucination | Correct language/script but content does not correspond to audio | Human review: sample items where WER > 80% and script is correct |

Each type's rate is reported separately. No aggregate hallucination rate.

### Latency (methodology C8)

Wall-clock client-side from request send to full response receipt. Report p50, p95, min, max.
Primary metric: **ms per second of audio submitted.**
Request timestamp and client region recorded in every call.

### Cost (methodology C9)

```
Cost_per_audio_minute = total_billed_usd / total_audio_minutes_submitted
```

Reported separately for successful and failed calls.
Free-tier calls: record actual cost ($0.00) AND list price.
Open-source models: `$0.00 (compute cost not included)`.

---

## Request Counts

### Phase 1 scope (OpenAI models only)

| Model | Conditions | Languages | Utterances/lang | Total requests |
|---|---|---|---|---|
| gpt-4o-transcribe | auto + hint | uz + kk | 300 each | 300×2×2 = **1,200** |
| gpt-4o-mini-transcribe | auto + hint | uz + kk | 300 each | **1,200** |
| whisper-1 | auto + hint | uz + kk | 300 each | **1,200** |
| **Phase 1 total** | — | — | — | **3,600** |

Total audio submitted per Phase 1:
- Uzbek: 1,307.8 s × 3 models × 2 conditions = 7,846.8 s ≈ **130.8 min**
- Kazakh: 2,233.6 s × 3 models × 2 conditions = 13,401.6 s ≈ **223.4 min**
- Combined: ≈ **354.2 audio-minutes** per Phase 1

Pricing for this total: **CONFIRMED** — see `stt_benchmark_cost_estimate.md` for full breakdown.

---

## Cost Control

### Pre-run estimate

Before any run begins, the estimated cost is calculated as:

```
estimated_cost = sum(audio_duration_s / 60 * list_price_per_min)  for all utterances × conditions
```

Pricing for OpenAI gpt-4o-transcribe: **CONFIRMED** $0.006/min audio + $10.00/1M output tokens.
Pricing for OpenAI gpt-4o-mini-transcribe: **CONFIRMED** $0.003/min audio + $5.00/1M output tokens.
Pricing for OpenAI whisper-1: **CONFIRMED** $0.006/min audio, no per-token rate.
See `stt_benchmark_cost_estimate.md` for full Phase 1 calculation.

No run is authorised until pricing is confirmed and the pre-run estimate is reviewed.

### Rate limiting and retries (methodology B5)

| Scenario | Action |
|---|---|
| HTTP 5xx | Retry ≤3 times; backoff 1s, 2s, 4s; record retry count |
| HTTP 429 | Retry after `Retry-After` header or 60 s; max 5 retries |
| HTTP 4xx (not 429) | Do not retry; record as error |
| Empty/malformed response | Retry once; if still malformed, record as error |
| Timeout > 120 s | Record as timeout; do not retry |

### Duplicate prevention

Each (utterance_id, model, condition) triple is a unique key. Before submitting a request, the output cache is checked for an existing record with this key and a non-null `raw_transcription`. If found, the call is skipped (resume support). Partial runs can be resumed without duplicate billing.

### Failure recording

Failed calls are never discarded. Each produces a record with `raw_transcription = null`, `http_status` populated, and `error_type`/`error_message` filled. Failed calls are included in error rates and cost accounting.

### Output cache location

```
benchmark/raw/<run_id>/<provider>/<model>/<condition>/<language>/<utterance_id>.json
benchmark/raw/<run_id>/<provider>/<model>/<condition>/<language>/<utterance_id>_response_raw.json
```

The `_response_raw.json` file contains the full provider response object before any field extraction.

### Maximum requests (hard cap)

Phase 1 hard cap: **4,000 requests total** (3,600 planned + 400 headroom for retries).
Abort if request count exceeds cap. Investigate before resuming.

---

## Reproducibility Metadata

The following fields are recorded for every benchmark run (per methodology E1 and E2):

| Field | Source |
|---|---|
| `run_id` | UUID generated at run start |
| `timestamp_utc` | Per-call, ISO 8601 |
| `provider` | Configured per model |
| `model` | Exact model string sent in API request |
| `model_version` | API-returned version; `null` if unavailable |
| `api_configuration` | Full API call parameters (response_format, temperature if applicable, etc.) |
| `language_condition` | `auto` or `hint` |
| `input_manifest_sha256` | SHA-256 of `audio_benchmark_manifest.csv` |
| `audio_sha256` | Per-file SHA-256 of each WAV |
| `audio_format` | `wav_16k_mono_pcm16` |
| `normalization_version` | `1.0` (this document's pipeline; any change increments this) |
| `sdk_version` | Exact client library version (e.g. `openai==1.x.x`) |
| `python_version` | Runtime Python version |
| `benchmark_version` | `1.0` |
| `temperature` | Provider-specific decoding temperature if applicable; `null` if not configurable |
| `retry_config` | Max retries, backoff policy as configured |
| `client_region` | Machine location identifier |

---

## Output Directory Structure

```
benchmark/
  config/
    stt_benchmark_config.md     ← this file (copy or symlink)
    stt_benchmark_config.json   ← machine-readable config
  raw/
    <run_id>/
      <provider>/
        <model>/
          <condition>/          (auto | hint)
            <language>/         (uz | kk)
              <utterance_id>.json              ← flat record
              <utterance_id>_response_raw.json ← full provider response
  normalized/
    <run_id>/
      <provider>_<model>_<condition>_<language>_normalized.csv
  results/
    <run_id>/
      summary.md
      leaderboard_uz.md
      leaderboard_kk.md
      leaderboard_combined.md
      confusion_matrices.md
      hallucination_report.md
      per_call_results.parquet  ← primary output: full per-call data
      per_call_results.csv      ← secondary: same data as CSV
  logs/
    <run_id>/
      run.log
      errors.log
      cost_estimate.txt         ← pre-run estimate written before first call
      cost_actual.txt           ← updated after run completion
```

No files in `benchmark/` are created by this configuration step. The directories are created at run-start.

---

## Known Confounds and Fairness Notes

These are documented per methodology B6 and do not invalidate the benchmark; they must appear in every published result table.

| Confound | Note |
|---|---|
| Duration distribution asymmetry | Uzbek mean 4.4 s; Kazakh mean 7.4 s. Per-language statistics reported separately. Latency metric (ms/s audio) corrects for duration. |
| Different corpus collection conditions | USC (crowdsourced Telegram + audiobook narrators); KSC (structured studio mobile recording). Speech naturalness and acoustic conditions differ. Cross-language WER comparisons are not valid without this caveat. |
| Speaker distribution differences | USC: 38 speakers, highly skewed (audiobook narrators dominate). KSC: 29 speakers, more balanced (min 10, max 11 per manifest). Per-speaker sub-analysis is recommended for USC. |
| Contamination risk | MEDIUM for both languages. Published public corpora may appear in commercial training data. All results carry this label. |
| Differential native support | Commercial providers may have substantially better training data for one language. A lower WER on one language does not imply a model is better overall — it may reflect training data imbalance. |
| AUTO vs HINT asymmetry | Providers differ in how they accept language hints. A provider that cannot accept ISO codes and falls back to `prompt="Uzbek"` may perform differently from one with native ISO support. This is documented per-provider; AUTO and HINT results are never averaged. |
| Smoke test scope limitation | Smoke test was Uzbek only, 2 recordings, 1 speaker. No Kazakh smoke test results exist. gpt-4o-transcribe Kazakh capability is CLAIMED but not confirmed by direct test. |
| Script vs language distinction | Uzbek Cyrillic and Kazakh Cyrillic are both `cyrillic`. Script accuracy does not prove language accuracy. Both metrics are always reported separately. |
| gpt-4o-mini Kazakh→Kyrgyz conflation | gpt-4o-mini-transcribe produces Kyrgyz output for Kazakh audio in both AUTO and hint conditions (confirmed smoke test 2026-08-23). This is the same category of error as whisper-1 producing Kazakh for Uzbek audio. The independent LID tool (`fasttext lid.176`) will detect this as `ky` (Kyrgyz). |
| gpt-4o-transcribe verbose_json unsupported | gpt-4o-transcribe and gpt-4o-mini-transcribe reject `verbose_json` with HTTP 400. Must use `json` or `text`. Consequence: `provider_detected_language` is NULL for all gpt-4o-variant calls. Only whisper-1 returns a detected language. |

---

## Remaining Pre-Run Decisions

These items must be resolved before any API call is made. They are inherited from methodology STEP 2 READINESS and from the current configuration:

| Decision | Status | Blocking? |
|---|---|---|
| Verify gpt-4o-transcribe pricing | **RESOLVED** — $0.006/min + $10.00/1M output tokens (2026-08-23) | ~~YES~~ |
| Verify gpt-4o-mini-transcribe pricing | **RESOLVED** — $0.003/min + $5.00/1M output tokens (2026-08-23) | ~~YES~~ |
| Verify whisper-1 current pricing | **RESOLVED** — $0.006/min, no per-token rate (2026-08-23) | ~~YES~~ |
| Kazakh hint mechanism for all three OpenAI models | **RESOLVED** — gpt-4o-transcribe/mini: `prompt="Kazakh"` (CLAIMED); whisper-1: `language="kk"` (CLAIMED, fallback `prompt="Kazakh"`) | ~~YES~~ |
| Select and pin independent LID tool | **RESOLVED** — `fasttext-wheel==0.9.2` + `lid.176.bin`; uz+kk confirmed in model | ~~YES~~ |
| Calibrate RMS silence threshold | NEEDS CALIBRATION | NO — can calibrate post-run on collected data |
| Decide on KZ-Latn reference set | DEFERRED | NO — Cyrillic-only for Phase 1 |
| Verify Google Cloud STT Chirp language codes | NEEDS VERIFICATION | NO — Phase 2 only |
| Set up GCP credentials | BLOCKED | NO — Phase 2 only |
| Set up Azure credentials + SDK | BLOCKED | NO — Phase 2 only |

---

## Pre-Run Checklist

Before running the first STT API call, confirm all of the following:

- [ ] Manifests verified: SHA-256 of `audio_benchmark_manifest.csv` = `d01408af2e04d048a44600138ac878f97b2a2372f62b9a42f2f7d0b161f34924`
- [ ] All 600 WAV files present, 16 kHz mono 16-bit verified
- [ ] `benchmark/` directory structure created
- [ ] Provider pricing confirmed and pre-run cost estimate documented
- [ ] OpenAI `language="kk"` parameter verified (accepted or rejected)
- [ ] Independent LID tool installed, version pinned
- [ ] Duplicate-prevention cache logic tested on 1 utterance
- [ ] Retry logic tested against a mock 429 response
- [ ] `run_id` generated and written to log before first call
- [ ] `input_manifest_sha256` written to run metadata before first call
- [ ] No benchmark has been run before this checklist is signed off

---

*No API calls have been made. No models have been run. No benchmark results exist.*
*This configuration is a planning document only.*
