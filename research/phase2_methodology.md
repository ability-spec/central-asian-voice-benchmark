# Phase 2 Benchmark Methodology
**Date:** 2026-08-24
**Status:** Design proposal only. No data collected. No tests run.
**Builds on:** `methodology_proposal.md` (STEP 2, Revision 2) — all Phase 1 methodology constraints apply unchanged.

---

## Evaluation Tracks

Phase 2 uses two parallel evaluation tracks. Results from the two tracks are never merged or averaged. They are reported in separate leaderboard tables.

### Track A — Public Benchmark (FLEURS)
**Purpose:** External comparability with academic literature and reproducibility by independent researchers.
**Dataset:** FLEURS (`google/fleurs`), test splits `uz_uz` and `kk_kz`
**Dataset version:** Pin HuggingFace commit SHA before download
**Size:** ~650–862 utterances per language (verify exact count after download)
**Contamination risk:** MEDIUM — same label as all public corpora per project methodology
**License:** CC BY 4.0
**Why FLEURS:** The only established public multilingual ASR benchmark with confirmed Uzbek and Kazakh splits, CC BY 4.0 license, and presence in the published ASR literature. Common Voice is not used for Track A because our Track B Uzbek corpus already derives from Common Voice (overlap would reduce comparability value).

### Track B — Frozen Benchmark (Our Corpus)
**Purpose:** Controlled, reproducible evaluation on our pre-audited corpus. Results are directly comparable to Phase 1 results.
**Dataset:** Frozen 600-utterance corpus — 300 Uzbek (USC), 300 Kazakh (ISSAI KSC). Manifests are immutable.
**Manifests:**
- `research/uzbek_benchmark_manifest.csv` SHA-256: `61b235f0d33ea57ad8696dfae5146117ddde4965db589762ae48c0c2f0565c70`
- `research/kazakh_benchmark_manifest.csv` SHA-256: `a068cd81c958c687b8239a1bdc73b55586fe98f7a218b8ca51b3fda517c89507`
- `research/audio_benchmark_manifest.csv` SHA-256: `d01408af2e04d048a44600138ac878f97b2a2372f62b9a42f2f7d0b161f34924`

**The frozen benchmark is immutable. No utterances will be added, removed, or modified.**

---

## Phase 2 Providers

### Included in Phase 2

| Provider | Model(s) | Track A | Track B |
|---|---|---|---|
| ElevenLabs | `scribe_v2` | Yes | Yes |
| Google Cloud STT | `chirp_2` (primary), `chirp_3` (eu region) | Yes | Yes |
| Azure Speech | Fast Transcription (`uz-UZ`, `kk-KZ`) | Yes | Yes |
| Google Gemini | `gemini-2.5-flash` (conditional on smoke test) | Yes (if smoke test passes) | Yes (if smoke test passes) |

**Gemini is conditional:** Language support for Uzbek/Kazakh is not documented in official API docs. Gemini requires a smoke test before pilot inclusion. If the smoke test confirms Uzbek and Kazakh transcription capability, Gemini proceeds to the pilot.

### Excluded from Phase 2
- **Deepgram:** Confirmed no Uzbek or Kazakh support
- **Amazon Transcribe:** Not subscribed (carry-forward from Phase 1 exclusion)
- **AssemblyAI:** Language support unverified — candidate for Phase 3 pending verification

---

## Language Conditions

Two mandatory conditions per provider/model/utterance pair, reported separately. Never averaged.

| Condition | Definition | Notes |
|---|---|---|
| `auto` | No language parameter supplied | Provider auto-detects |
| `hint` | Correct language code or name explicitly supplied | Provider-specific mechanism per table below |

### Hint Mechanisms by Provider

| Provider | Model | Uzbek hint | Kazakh hint | Evidence |
|---|---|---|---|---|
| ElevenLabs | scribe_v2 | `language_code="uz"` | `language_code="kk"` | CONFIRMED from API docs |
| Google Cloud STT | chirp_2 | `language_codes=["uz-UZ"]` | `language_codes=["kk-KZ"]` | CONFIRMED from language table (V2 API uses array, not scalar) |
| Azure Speech | Fast Transcription | `language="uz-UZ"` | `language="kk-KZ"` | CONFIRMED from language support table |
| Google Gemini | gemini-2.5-flash | `prompt="Transcribe in Uzbek"` | `prompt="Transcribe in Kazakh"` | CLAIMED — no formal language parameter |

**Note on Gemini:** The absence of a formal language parameter means the Gemini `hint` condition is not structurally equivalent to other providers' hint conditions. This asymmetry must be disclosed in all published results. Gemini AUTO and HINT results must carry an additional note: "Hint delivered via prompt instruction, not language parameter."

---

## Phase 2 Pilot Design

Before any full Phase 2 run, a 40-utterance pilot verifies provider integration and identifies failures early.

### Pilot Corpus
| Language | Utterances | Source |
|---|---|---|
| Uzbek | 20 | Stratified sample from frozen Track B Uzbek manifest (300 utterances) |
| Kazakh | 20 | Stratified sample from frozen Track B Kazakh manifest (300 utterances) |
| **Total** | **40** | |

**Stratification:** Sample proportionally from duration tiers (short: 3–10 s, medium: 10–30 s) to match the full manifest distribution. Select speaker-diverse items where possible. Record the exact utterance IDs used in the pilot manifest.

### Pilot Conditions
All providers tested under both AUTO and HINT conditions: 40 utterances × 2 conditions = **80 requests per provider**.

For Gemini: additionally test with no prompt (silent AUTO), prompt-only AUTO ("Transcribe this audio"), and explicit HINT ("Transcribe in Uzbek") as three sub-conditions to characterise the prompt-language-hint mechanism.

### Pilot Goals
The pilot must answer these questions before the full run is authorised:

| Question | Method |
|---|---|
| Does the provider accept our WAV format? | Confirm HTTP 200 on first call |
| Does the provider return Uzbek Latin output for Uzbek audio? | Script accuracy classification |
| Does the provider return Kazakh Cyrillic output for Kazakh audio? | Script accuracy classification |
| Does the language hint change output language? | Compare AUTO vs HINT script accuracy |
| Does the provider return non-null transcription? | Null rate on 40 items |
| Is there evidence of language confusion (e.g. Kyrgyz for Kazakh)? | Independent LID on outputs |
| Is WER broadly consistent with expected range? | Spot-check 5–10 items manually |
| Is latency within acceptable range? | p50 and p95 on 80 calls |
| Does the retry logic handle transient errors? | Log retry_count distribution |
| Is the cost within estimate? | Compare actual cost vs `phase2_cost_estimate.md` |

### Pilot Authorisation Gate
The pilot for each provider must pass before that provider proceeds to the full 600-utterance run:
- Null rate < 10% (fewer than 4 of 40 calls return null transcription)
- At least one AUTO condition returns correct script output
- No HTTP 4xx error pattern indicating unsupported language or unsupported format
- Actual pilot cost within 2× of estimate

---

## Audio Protocol (unchanged from Phase 1)

| Parameter | Value |
|---|---|
| Format | WAV (PCM, 16-bit, little-endian) |
| Sample rate | 16,000 Hz |
| Channels | Mono |
| Max segment duration | 60 s |
| Preprocessing | None |
| Loudness normalisation | None |

**Track A (FLEURS):** FLAC audio must be converted to WAV 16 kHz mono PCM before submission. Conversion command to be recorded in run metadata. All converted files must pass SHA-256 verification against a pre-conversion manifest.

---

## Result Schema

### Additions for Phase 2

The Phase 1 schema (defined in `methodology_proposal.md` Section E1 and `stt_benchmark_config.md`) is extended with three new fields. All Phase 1 fields are preserved unchanged. Phase 1 records are not modified.

| Field | Type | Description |
|---|---|---|
| `track` | string | `"A"` (FLEURS public) or `"B"` (frozen benchmark) |
| `fleurs_id` | string | FLEURS utterance ID (e.g. `"10001743192833749979"`) — `null` for Track B records |
| `fleurs_subset` | string | `"uz_uz"` or `"kk_kz"` — `null` for Track B records |

No other schema changes. No existing fields are renamed, removed, or retyped.

### Fields already in Phase 1 schema that cover Phase 2 needs

All of the following are already defined and no changes are required:

- `provider`, `model`, `language_condition`, `language_hint`, `prompt`
- `utterance_id`, `audio_id`, `audio_sha256`, `audio_duration_s`
- `raw_transcription`, `normalized_transcription`
- `provider_detected_language`, `independent_detected_language`, `dominant_script`
- `latency_ms`, `http_status`, `error_type`, `error_message`, `retry_count`
- `cost_usd`, `cost_list_price_usd`
- `contamination_risk`, `corpus_source`
- `run_id`, `call_id`, `timestamp_utc`, `benchmark_version`

---

## Evaluation Metrics (unchanged from Phase 1)

All metrics defined in `methodology_proposal.md` Sections C1–C9 apply to Phase 2 without modification:
WER, CER, script accuracy, provider LID accuracy, output LID accuracy, language confusion matrix, hallucination taxonomy (4 types), latency (p50/p95/min/max in ms/s audio), cost per audio-minute.

**Known WER limitation — numeric/word-form equivalence:** WER treats digit renderings and their spelled-out equivalents as errors even when semantically identical (e.g. `97 км` vs `тоқсан жеті километр`; `1` vs `bir`). The normalisation pipeline does not convert between forms. Affected records will show inflated WER without reflecting intelligibility failure. Analysts should flag such cases in the per-utterance review rather than treating them as unexplained high-error items. This limitation is common to all standard WER implementations and is not corrected here.

---

## Leaderboard Design for Phase 2

### Track A leaderboard (one per language)
Identical structure to the Phase 1 commercial leaderboard (methodology Section G1), with an additional `Track` column (`A`) and `Dataset` column (`FLEURS`).

### Track B leaderboard (one per language)
Identical structure to Phase 1 leaderboard. Phase 1 and Phase 2 providers appear together for cross-phase comparison.

### Combined Phase 1 + Phase 2 leaderboard
All providers (Phase 1 + Phase 2) on Track B, sorted by WER (auto), with `phase` column.

### Cross-track comparison
A summary table showing each provider's Track A vs Track B WER for each language. This reveals whether performance on public FLEURS data predicts performance on our controlled corpus.

---

## Pre-Run Checklist (Phase 2)

Before the first Phase 2 API call:

- [ ] Gemini smoke test completed and result recorded
- [ ] ElevenLabs SDK/API key configured and verified
- [ ] Google Cloud STT credentials configured; region selected
- [ ] Azure Speech SDK installed (`pip install azure-cognitiveservices-speech`); key configured
- [ ] FLEURS uz_uz and kk_kz test splits downloaded; HuggingFace commit SHA recorded
- [ ] FLEURS audio converted to WAV 16 kHz mono; SHA-256 manifest written
- [ ] Pilot utterance IDs selected and recorded
- [ ] Pricing verified for all providers (see `phase2_cost_estimate.md`)
- [ ] Pre-run cost estimate reviewed and spending cap confirmed
- [ ] Duplicate-prevention cache logic verified
- [ ] Retry logic tested
- [ ] `run_id` generated before first call

---

*No API calls have been made. No benchmark has been run. This is a planning document only.*
