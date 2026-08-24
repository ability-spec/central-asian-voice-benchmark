# Central Asian Voice Benchmark
## STEP 2 — Benchmark Methodology Proposal

**Date:** 2026-08-24 | **Revision:** 2 | **Status:** Design proposal only. No data collected. No tests run. | **Scope:** STT only. Translation and TTS methodology follow separately.

---

## A. TEST DATASET

### A1. Corpus size

| Language | Utterances | Speakers | Audio (~10 s avg) |
|---|---|---|---|
| Uzbek | 300 | ≥ 10 | ~50 min |
| Kazakh | 300 | ≥ 10 | ~50 min |

300 utterances is the minimum defensible count for a published result. WER stabilises at ~100–200 utterances for a homogeneous speaker pool; 300 provides margin for per-speaker sub-analysis. The bottleneck is ground-truth transcription effort, not API cost. Begin with a 100-utterance pilot and expand to 300 before publishing if WER estimates are unstable across providers.

### A2. Corpus sources

**Mozilla Common Voice test split — CONTAMINATION-RISK: MEDIUM.** Use only the official `test` split of a pinned version. Never use `train` or `dev` splits. All results from this source carry the `MEDIUM` label.

**Own recordings — CONTAMINATION-RISK: LOW.** Used as a contamination-detection canary alongside the public corpus. The two existing recordings are smoke-test items only and do not qualify as benchmark items. Own recordings qualify when ≥5 speakers are represented, each transcript is independently verified by a second native speaker, and recordings follow the audio protocol in Section B.

The two sources are never merged in the same result row.

### A3. Sample duration

Mix: ~60% short (3–10 s), ~40% medium (10–30 s). Cap individual segments at 60 s. Audio longer than 60 s triggers provider-specific chunking behaviour that is not the subject of this benchmark.

### A4. Ground-truth transcripts

Every item requires a human-verified reference transcript before any model is run on it.

Process: (1) For Common Voice, use the existing validated transcript and conduct a spot-check. (2) For own recordings, a fluent native speaker produces a first-pass transcript. (3) A second independent native speaker reviews and flags disagreements. (4) Disagreements are resolved by a documented rule and transcripts are locked before testing begins.

Script convention: Uzbek references in modern Latin (UZ-Latn). Kazakh references in Cyrillic (KZ-Cyrl). If Latin-script Kazakh (KZ-Latn) is also required, maintain a separate reference set. Never mix scripts within a reference set.

---

## B. FAIR TESTING PROTOCOL

### B1. Audio format

| Parameter | Value |
|---|---|
| Container | WAV (PCM, 16-bit, little-endian) |
| Sample rate | 16 000 Hz |
| Channels | Mono |
| Max segment duration | 60 s |

MP3 robustness testing runs as a separately labelled condition and is never mixed with WAV primary results.

### B2. Preprocessing

No loudness normalisation, noise reduction, or pitch/speed adjustment. Trim leading/trailing silence only if it exceeds 1 s. A model that handles variable recording conditions is better than one that requires preprocessing; the benchmark should reveal that difference, not hide it.

### B3. Language hint conditions

Every item is submitted under two mandatory conditions, reported separately and never averaged together:

| Condition | Parameter |
|---|---|
| `lang=auto` | None — provider auto-detects |
| `lang=hint` | ISO 639-1 code if accepted; language name via `prompt` field if ISO code rejected |

Provider-specific hint handling is documented before testing begins:

| Provider | `lang=hint` mechanism | Note |
|---|---|---|
| OpenAI | `prompt="Uzbek"` | ISO `uz` rejected on all three tested models |
| Google Cloud STT | `languageCode: "uz-UZ"` | Not yet tested |
| Azure STT | `language: "uz-UZ"` | Not yet tested |

### B4. Prompting policy

The `prompt` field may contain the language name only. No vocabulary, phonetic hints, or expected phrases. The exact prompt string is recorded in every call's metadata.

### B5. Retries and failures

| Scenario | Action |
|---|---|
| HTTP 5xx | Retry ≤3 times; backoff 1 s, 2 s, 4 s; record retry count |
| HTTP 429 | Retry after `Retry-After` header or 60 s; max 5 retries |
| HTTP 4xx (not 429) | Do not retry; record as error |
| Empty or malformed response | Retry once; if still malformed, record as error |
| Timeout > 120 s | Record as timeout; do not retry |

Failed calls are never discarded. Each produces a record with `raw_transcription = null` and is included in error rates, latency distributions, and cost accounting.

### B6. Fairness confounds

| Confound | Management |
|---|---|
| Language hint interface asymmetry | `auto` and `hint` reported in separate columns; never combined |
| Response-format metadata differences | Noted per model; does not affect transcription text or scoring |
| Prompt interface asymmetry | Language name only in prompt; absence noted but not penalised |
| Audio-level sensitivity | No normalisation applied; raw audio submitted |
| Chunking differences | 60 s segment cap prevents provider chunking from becoming a confound |
| Network latency variation | Client region recorded in every call |
| Training data opacity | Contamination-risk labels attached to all results (Section F) |
| Open-source hardware dependency | Separate leaderboard from commercial APIs (Section G) |

---

## C. EVALUATION METRICS

### C1. WER

`WER = (S + D + I) / N` where S = substitutions, D = deletions, I = insertions, N = reference word count. Computed with standard Levenshtein alignment (e.g., `jiwer`). Applied to normalised text only (see C6). Cross-script outputs are included, not excluded; a near-100% WER on wrong-script output correctly reflects that failure.

### C2. CER

Same formula applied at the Unicode code-point level after normalisation. CER is particularly informative for morphologically rich languages where one morpheme error produces a full-word substitution in WER but a smaller penalty in CER.

### C3. Script accuracy

Classify the dominant script of each **raw** output (before normalisation) by Unicode block. A script is dominant if ≥70% of non-whitespace alphabetic characters belong to that block.

Labels: `latin`, `cyrillic`, `arabic`, `mixed`, `other`, `empty`.

`Script_accuracy = outputs with correct script label / total non-null outputs`

Expected script is defined by the reference transcript. Script accuracy identifies the writing system only — it does not identify the language. Uzbek Cyrillic and Kazakh Cyrillic both classify as `cyrillic`. Language accuracy is a separate metric (C4).

### C4. Language accuracy

Two sub-metrics, always reported separately:

**Provider LID accuracy** — only when the API returns `detected_language`:
`Provider_LID_accuracy = (detected_language matches reference language) / (calls with non-null detected_language)`
Reported for `lang=auto` only. Providers that never return `detected_language` receive `N/A`, not zero.

**Output language accuracy** — always available, from our own LID tool applied to raw output:
`Output_language_accuracy = (independent LID matches reference language) / (non-null, non-empty outputs)`
Outputs below 10 words are excluded or flagged separately; short texts are unreliable for automatic language identification.

### C5. Language confusion

For `lang=auto`, report a per-model confusion matrix showing what language the model produced when given audio in each reference language. A single accuracy figure is insufficient; the whisper-1 Uzbek→Kazakh confusion in the smoke test is exactly what this matrix captures.

### C6. Deterministic normalisation

Raw output is always preserved and immutable. A normalised copy (`normalized_transcription`) is derived for scoring only. Applied identically to both reference and hypothesis, in this exact order:

1. Unicode NFC normalisation
2. Unicode-aware casefold (`str.casefold()`)
3. Apostrophe normalisation: map U+02BB, U+2018, U+2019, U+0060, U+00B4 → U+0027
4. Punctuation removal: period, comma, question mark, exclamation mark, colon, semicolon, ellipsis, em-dash, en-dash at word boundaries
5. Whitespace normalisation: collapse all Unicode whitespace to a single ASCII space; strip leading/trailing
6. No cross-script transliteration: Cyrillic output against a Latin reference scores a correctly high WER

Validate on a test suite of known input/output pairs before any benchmark run.

### C7. Hallucination taxonomy

| Type | Signal | Detection |
|---|---|---|
| Silence hallucination | Non-empty output when audio is near-silent | Automatic — RMS energy below a calibrated threshold |
| Excessive output | Output word count > 3× expected for audio duration (at 2.5 words/s) | Automatic flag only; requires human review to confirm |
| Unrelated-language output | Output in a language outside the Turkic family for Central Asian audio | Semi-automatic — Output_language_accuracy returns a non-Turkic language |
| Semantic hallucination | Correct language/script but content does not correspond to the audio | Human review required — sample items where WER > 80% and script is correct |

Report each type's rate separately. Do not aggregate into a single hallucination rate.

### C8. Latency

Measure wall-clock time client-side from request send to full response receipt. Report p50, p95, min, max. Primary metric: **ms per second of audio submitted**. Record request timestamp and client region in every call.

### C9. Cost per audio minute

`Cost_per_audio_minute = total_billed_usd / total_audio_minutes_submitted`

Report for successful and failed calls separately. For free-tier calls, record both actual cost ($0.00) and list price. Open-source models report `$0.00 (compute cost not included)`.

---

## D. PROVIDERS

No tests are authorised by this document.

### D1. Commercial APIs

| Provider | Models | Uzbek status | Kazakh status |
|---|---|---|---|
| OpenAI | whisper-1, gpt-4o-mini-transcribe, gpt-4o-transcribe | whisper-1: FAIL; mini: INCONSISTENT; transcribe: CONFIRMED WORKING | Not tested |
| Google Cloud STT | chirp, chirp_2, chirp_3 | CLAIMED | CLAIMED |
| Azure | Batch + real-time STT | CLAIMED | CLAIMED |
| Amazon Transcribe | Standard | CLAIMED — not subscribed | CLAIMED — not subscribed |
| ElevenLabs / AssemblyAI / Deepgram | TBD | UNKNOWN | UNKNOWN |

### D2. Open-source / local models

| Model | Notes |
|---|---|
| OpenAI Whisper large-v3 | Pin HuggingFace commit SHA; distinct from whisper-1 API |
| Faster-Whisper large-v3 | Same weights, different runtime |
| Meta MMS | Explicitly supports Uzbek and Kazakh; strong candidate |
| Wav2Vec2 Uzbek/Kazakh fine-tunes | Survey HuggingFace; pin SHA before testing |
| NVIDIA NeMo multilingual | GPU required; verify language support before scheduling |

Record checkpoint hash, framework version, and hardware spec in every open-source run.

### D3. AWS Bedrock

| Model | Status |
|---|---|
| mistral.voxtral-mini-3b-2507 | CONFIRMED FAIL — Uzbek (smoke test; raw output not preserved) |
| mistral.voxtral-small-24b-2507 | CONFIRMED FAIL — Uzbek (smoke test; raw output not preserved) |
| amazon.nova-2-sonic-v1:0 | Not tested; requires a different test harness |

---

## E. REPRODUCIBILITY

### E1. Per-call metadata schema

One record per API call, stored as flat JSON or a Parquet row:

| Field | Type | Description |
|---|---|---|
| `run_id` | string | UUID for the benchmark run |
| `call_id` | string | UUID for this individual call |
| `timestamp_utc` | ISO 8601 | Time request was sent |
| `provider` | string | e.g. `openai`, `google`, `local` |
| `model` | string | Model name as sent in the request |
| `model_version` | string | API-returned version or checkpoint SHA; `null` if unavailable |
| `client_region` | string | Client machine location |
| `api_region` | string | API endpoint region; `null` if not specifiable |
| `audio_id` | string | Stable item identifier |
| `audio_sha256` | string | SHA-256 of audio file bytes |
| `audio_duration_s` | float | Duration in seconds |
| `audio_format` | string | e.g. `wav_16k_mono_pcm16` |
| `corpus_source` | string | e.g. `common_voice_v18`, `own_recordings` |
| `contamination_risk` | string | `LOW`, `MEDIUM`, or `HIGH` |
| `language_condition` | string | `auto` or `hint` |
| `language_hint` | string | Exact value passed; `null` if auto |
| `prompt` | string | Exact prompt string; `null` if none |
| `response_format` | string | e.g. `json`, `verbose_json` |
| `raw_transcription` | string | Verbatim API output; **never overwritten**; `null` on error |
| `normalized_transcription` | string | Scoring copy derived from raw |
| `provider_detected_language` | string | From API metadata; `null` if not returned |
| `independent_detected_language` | string | From our LID tool applied to raw output |
| `dominant_script` | string | Script classification result |
| `latency_ms` | integer | Wall-clock ms, client-side |
| `http_status` | integer | HTTP response code |
| `error_type` | string | API error code; `null` on success |
| `error_message` | string | Full error text; `null` on success |
| `retry_count` | integer | Retries before this result |
| `cost_usd` | float | Actual billed amount |
| `cost_list_price_usd` | float | List price regardless of free tier |
| `sdk_version` | string | Client library version |
| `benchmark_version` | string | This document's revision number |

### E2. Immutability rule

A written record is never modified. Corrections are new records with a `supersedes_call_id` field pointing to the original.

---

## F. DATA CONTAMINATION

### F1. Problem

Commercial STT models are trained on internet-scraped audio that likely includes historical Common Voice releases. Using the Common Voice test split does not guarantee test items are unseen by any model. Low WER on public benchmark data may reflect memorisation rather than generalisation.

### F2. Risk labels

| Corpus | Label |
|---|---|
| Mozilla Common Voice (any version) | MEDIUM |
| Other published public corpora | MEDIUM |
| Own recordings made post-training-cutoff | LOW |
| Data confirmed in a model's training set | HIGH |

### F3. Mitigations

1. Use only the `test` split; pin the corpus version before data collection.
2. Include canary items (own recordings, LOW risk) in every run; report WER separately per source. A large gap between public-corpus WER and canary WER is a contamination signal.
3. Record provider training-data disclosures; absence of disclosure is itself noted.
4. Never use reference transcripts as prompt text.
5. Publish the full per-call dataset alongside summary tables so readers can assess risk independently.

### F4. Residual risk

No mitigation fully eliminates contamination risk for closed commercial models. All public-corpus results carry the MEDIUM label in every published table.

---

## G. FINAL OUTPUT — LEADERBOARD DESIGN

### G1. Commercial leaderboard (one per language)

| Model | Provider | WER auto | WER hint | CER auto | Script acc. | Provider LID | Output LID | p50 ms/s | $/min | Contam. |
|---|---|---|---|---|---|---|---|---|---|---|

### G2. Open-source leaderboard (one per language)

Same columns as G1; replace `$/min` with `Hardware`; add `Checkpoint SHA` column.

### G3. Combined comparison

A single table including both leaderboard types, sorted by WER (auto), with an explicit `type` column (`commercial_api` or `open_source_local`). For context only; primary leaderboards remain separate.

### G4. Failure modes table

| Model | Type | Error rate | Silence halluc. | Excessive output | Unrelated lang. | Semantic halluc. (sampled) |
|---|---|---|---|---|---|---|

### G5. Language confusion matrix

Per model, per language, `lang=auto` condition only. Shows what language the model produced when given audio in each reference language.

### G6. Publication format

Primary output: Parquet file of all per-call records (Section E schema). Secondary: Markdown summary tables. Contamination-risk labels appear in both. Stratified sub-results by duration tier, speaker, and corpus source accompany the main tables.

### G7. What the leaderboard is not

This benchmark covers Uzbek and Kazakh STT only, under the conditions defined here. Results must not be cited as a general-purpose STT ranking or as evidence of performance on other languages. It is not a product recommendation.

---

## STEP 2 READINESS

### Ready for implementation

- Audio protocol: WAV 16 kHz mono 16-bit, 60 s max segment
- Two mandatory language conditions (`auto` and `hint`) with separate reporting
- Deterministic normalisation pipeline: NFC → casefold → apostrophe → punctuation → whitespace → no cross-script transliteration
- Raw output immutability; `normalized_transcription` as separate derived field
- Complete metadata schema including `raw_transcription`, `normalized_transcription`, `provider_detected_language`, `independent_detected_language`, `dominant_script`, `contamination_risk`
- Contamination-risk labelling framework: LOW / MEDIUM / HIGH
- Four-type hallucination taxonomy with distinct detection method per type
- Script accuracy and language accuracy defined as separate metrics
- Separate commercial and open-source leaderboards
- Retry and failure recording policy
- Dual native-speaker ground-truth transcript verification process
- Fairness confound inventory (Section B6)

### Remaining decisions before data collection

- Confirm Common Voice data availability for Uzbek and Kazakh; pin the exact version number
- Decide whether to produce a KZ-Latn reference set or defer Latin-script Kazakh to a later phase
- Decide whether to expand own recordings to ≥5 speakers before Phase 1 or use Common Voice only
- Select and pin the independent language identification library (`langdetect`, `fasttext`, or `lingua`)
- Calibrate RMS silence threshold (Type 1 hallucination) and excessive-output word-rate ratio (Type 2 flag) on a small pilot set

### Can safely be deferred

- Exact Common Voice version number (pin at download time)
- Hardware specification for open-source model runs
- ElevenLabs, AssemblyAI, Deepgram inclusion (Uzbek/Kazakh support unconfirmed)
- Latin-script Kazakh testing
- MP3 robustness condition
- Preprocessing sensitivity study

---

No data has been collected. No benchmark has been run. All numerical targets are methodological recommendations, not experimental results.
