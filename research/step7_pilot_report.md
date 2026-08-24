# STT Benchmark — STEP 7 Pilot Report

**Date:** 2026-08-23
**Run ID:** pilot_001
**Status:** Pilot complete. Full 3,360-request benchmark NOT started.
**Scope:** 20 Uzbek + 20 Kazakh utterances × 3 models × 2 conditions = 240 requests

**Note on request count:** The task specification stated '120 requests' but the correct arithmetic is (20 uz + 20 kk) × 3 models × 2 conditions = 240 requests. All 240 ran successfully. The remaining full benchmark is 3,600 − 240 = 3,360 requests.

---

## Preflight Results

- **[PASS]** `uzbek_manifest_sha256`: actual=61b235f0d33ea57a...
- **[PASS]** `kazakh_manifest_sha256`: actual=a068cd81c958c687...
- **[PASS]** `audio_manifest_sha256`: actual=d01408af2e04d048...
- **[PASS]** `utterance_counts`: uz=300 kk=300
- **[PASS]** `wav_files_600`: uz=300 kk=300
- **[FAIL]** `fasttext_wheel_installed`: BLOCKED: C++ build tools required; using custom_lid substitute
- **[FAIL]** `lid176bin_present`: NOT DOWNLOADED — fasttext build failed; download manually when MSVC available
- **[FAIL]** `lid176bin_sha256_recorded`: pending download
- **[PASS]** `phase1_configs_consistent`: 3 Phase 1 providers, all have pricing and response_format
- **[PASS]** `retry_policy_defined`: timeout=120s, max_5xx=3
- **[PASS]** `raw_responses_saved`: every API response written to raw/<request_id>_raw.json
- **[PASS]** `no_overwrite_protection`: dedup: skip if records/<request_id>.json already exists
- **[PASS]** `deterministic_request_ids`: format: pilot_001_{model_abbrev}_{condition}_{utterance_id}
- **[PASS]** `cost_tracked_per_request`: cost_usd = duration_s / 60 * price_per_min stored in every record
- **[PASS]** `failed_calls_recorded`: errors stored as records with http_status != 200, raw_transcription=null

**Preflight summary:** 12 PASS, 3 FAIL

### Critical preflight note

> **fasttext-wheel==0.9.2 BLOCKED**: The planned independent LID tool cannot be installed on Python 3.14 / Windows without Microsoft C++ Build Tools (MSVC 14.0+). Neither `gcld3`, `pycld2`, nor `fasttext-langdetect` have pre-built wheels for Python 3.14. `langid` does not support Uzbek (`uz`). A custom Unicode-character-based LID (`custom_script_based_v1`) is used for this pilot. **The `independent_detected_language` metric is provisional and should be re-run with fasttext `lid.176.bin` once build tools are available.**

---

## Pilot Utterance Selection

- **Rule**: First 20 utterances per language in `audio_benchmark_manifest.csv` order
- **Uzbek utterance IDs**: 1126542829_1_33727_1 … 1187023182_2_37068_1
- **Kazakh utterance IDs**: 5f5af4cf7bb2c … 5f59c07c44250
- Manifests unchanged: SHA-256 verified in preflight

---

## API Results Summary

| Metric | Value |
|---|---|
| Total requests | 240 |
| HTTP 200 success | 240 |
| HTTP error | 0 |
| API success rate | 100.0% |
| Total estimated cost | $0.1449 |

---

## Per-Model / Per-Condition / Per-Language Metrics

**Note:** AUTO and HINT are never averaged. Reported separately per methodology.

| Model | Cond | Lang | N_ok | API% | WER | CER | Script% | IndepLID% | ProvLID% | p50ms | p95ms | Cost$ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gpt-4o-transcribe | auto | uz | 20 | 100% | 0.491 | 0.283 | 85% | 85% | N/A | 861 | 1943 | 0.0110 |
| gpt-4o-transcribe | auto | kk | 20 | 100% | 0.190 | 0.084 | 95% | 95% | N/A | 904 | 1183 | 0.0180 |
| gpt-4o-transcribe | hint | uz | 20 | 100% | 0.309 | 0.107 | 100% | 100% | N/A | 675 | 1098 | 0.0110 |
| gpt-4o-transcribe | hint | kk | 20 | 100% | 0.161 | 0.033 | 100% | 100% | N/A | 840 | 1169 | 0.0180 |
| gpt-4o-mini-transcribe | auto | uz | 20 | 100% | 0.791 | 0.578 | 50% | 50% | N/A | 597 | 842 | 0.0055 |
| gpt-4o-mini-transcribe | auto | kk | 20 | 100% | 0.425 | 0.141 | 100% | 80% | N/A | 694 | 1287 | 0.0090 |
| gpt-4o-mini-transcribe | hint | uz | 20 | 100% | 0.504 | 0.245 | 85% | 85% | N/A | 617 | 818 | 0.0055 |
| gpt-4o-mini-transcribe | hint | kk | 20 | 100% | 0.311 | 0.086 | 100% | 100% | N/A | 731 | 1144 | 0.0090 |
| whisper-1 | auto | uz | 20 | 100% | 1.113 | 0.689 | 45% | 45% | 10% | 1194 | 2509 | 0.0110 |
| whisper-1 | auto | kk | 20 | 100% | 0.534 | 0.143 | 100% | 100% | 95% | 1628 | 2781 | 0.0180 |
| whisper-1 | hint | uz | 20 | 100% | 1.177 | 0.805 | 40% | 40% | 0% | 1377 | 7939 | 0.0110 |
| whisper-1 | hint | kk | 20 | 100% | 0.526 | 0.136 | 100% | 100% | 100% | 1504 | 3173 | 0.0180 |

---

## Model-Level Analysis

### gpt-4o-transcribe

**UZ AUTO:** WER=0.491  Script=0.85
**UZ HINT:** WER=0.309  Script=1.00
**KK AUTO:** WER=0.190  Script=0.95
**KK HINT:** WER=0.161  Script=1.00

- `verbose_json` rejected by API (HTTP 400 `unsupported_value`); using `json` format.
- `provider_detected_language` is NULL for all calls — not returned in `json` format.
- Kazakh: CONFIRMED WORKING in smoke test. Hint (`prompt="Kazakh"`) reduced one-word error in smoke test.

### gpt-4o-mini-transcribe

**UZ AUTO:** WER=0.791  Script=0.50
**UZ HINT:** WER=0.504  Script=0.85
**KK AUTO:** WER=0.425  Script=1.00
**KK HINT:** WER=0.311  Script=1.00

- Kazakh: CONFIRMED FAIL in smoke test — produces Kyrgyz output, hint ineffective.
- Uzbek: CONFIRMED INCONSISTENT in smoke test — expect high WER and/or wrong script on some utterances.
- `provider_detected_language` NULL (json format).

### whisper-1

**UZ AUTO:** WER=1.113  Script=0.45  ProvLID=0.10
**UZ HINT:** WER=1.177  Script=0.40  ProvLID=0.00
**KK AUTO:** WER=0.534  Script=1.00  ProvLID=0.95
**KK HINT:** WER=0.526  Script=1.00  ProvLID=1.00

- Uzbek AUTO: CONFIRMED FAIL — outputs Kazakh Cyrillic for Uzbek audio.
- Uzbek HINT (`prompt="Uzbek"`): CLAIMED — ISO `uz` rejected; this is the fallback (untested before pilot).
- Kazakh AUTO: CONFIRMED WORKING. `language="kk"` CONFIRMED ACCEPTED.
- `verbose_json` supported; `provider_detected_language` available.

---

## Issues Found During Pilot

- **API failures**: None
- **Null transcripts (HTTP 200)**: None
- **Wrong script outputs**: 40
  - gpt-4o-transcribe auto uz 1131474547_2_29212_1: script=arabic expected=latin
  - gpt-4o-transcribe auto uz 1131474547_2_30670_1: script=arabic expected=latin
  - gpt-4o-transcribe auto uz 1187023182_2_35150_1: script=arabic expected=latin
  - gpt-4o-transcribe auto kk 5f5af6725f6f5: script=arabic expected=cyrillic
  - gpt-4o-mini-transcribe auto uz 1131474547_2_29207_1: script=cyrillic expected=latin
  - gpt-4o-mini-transcribe auto uz 1131474547_2_29212_1: script=arabic expected=latin
  - gpt-4o-mini-transcribe auto uz 1131474547_2_29215_1: script=arabic expected=latin
  - gpt-4o-mini-transcribe auto uz 1131474547_2_30667_1: script=arabic expected=latin
  - gpt-4o-mini-transcribe auto uz 1131474547_2_30670_1: script=arabic expected=latin
  - gpt-4o-mini-transcribe auto uz 1131474547_2_30673_1: script=cyrillic expected=latin
  - gpt-4o-mini-transcribe auto uz 1131474547_2_30676_1: script=arabic expected=latin
  - gpt-4o-mini-transcribe auto uz 1187023182_2_35150_1: script=cyrillic expected=latin
  - gpt-4o-mini-transcribe auto uz 1187023182_2_35614_1: script=cyrillic expected=latin
  - gpt-4o-mini-transcribe auto uz 1187023182_2_36933_1: script=arabic expected=latin
  - gpt-4o-mini-transcribe hint uz 1131474547_2_29212_1: script=arabic expected=latin
  - gpt-4o-mini-transcribe hint uz 1131474547_2_30670_1: script=arabic expected=latin
  - gpt-4o-mini-transcribe hint uz 1187023182_2_35150_1: script=cyrillic expected=latin
  - whisper-1 auto uz 1131474547_2_29207_1: script=cyrillic expected=latin
  - whisper-1 auto uz 1131474547_2_29209_1: script=cyrillic expected=latin
  - whisper-1 auto uz 1131474547_2_29212_1: script=cyrillic expected=latin
  - whisper-1 auto uz 1131474547_2_29215_1: script=cyrillic expected=latin
  - whisper-1 auto uz 1131474547_2_29222_1: script=cyrillic expected=latin
  - whisper-1 auto uz 1131474547_2_30667_1: script=arabic expected=latin
  - whisper-1 auto uz 1131474547_2_30670_1: script=cyrillic expected=latin
  - whisper-1 auto uz 1131474547_2_30676_1: script=arabic expected=latin
  - whisper-1 auto uz 1187023182_2_34561_1: script=empty expected=latin
  - whisper-1 auto uz 1187023182_2_35150_1: script=cyrillic expected=latin
  - whisper-1 auto uz 1187023182_2_36933_1: script=arabic expected=latin
  - whisper-1 hint uz 1131474547_2_29209_1: script=cyrillic expected=latin
  - whisper-1 hint uz 1131474547_2_29212_1: script=cyrillic expected=latin
  - whisper-1 hint uz 1131474547_2_29215_1: script=cyrillic expected=latin
  - whisper-1 hint uz 1131474547_2_29219_1: script=cyrillic expected=latin
  - whisper-1 hint uz 1131474547_2_29222_1: script=cyrillic expected=latin
  - whisper-1 hint uz 1131474547_2_30667_1: script=cyrillic expected=latin
  - whisper-1 hint uz 1131474547_2_30670_1: script=cyrillic expected=latin
  - whisper-1 hint uz 1131474547_2_30679_1: script=cyrillic expected=latin
  - whisper-1 hint uz 1187023182_2_34561_1: script=empty expected=latin
  - whisper-1 hint uz 1187023182_2_35150_1: script=cyrillic expected=latin
  - whisper-1 hint uz 1187023182_2_35332_1: script=cyrillic expected=latin
  - whisper-1 hint uz 1187023182_2_36933_1: script=cyrillic expected=latin
- **No additional issues found.**

### Uzbek Arabic-script outputs (new finding)

Several Uzbek utterances from speaker `1131474547` produced Arabic-script output from gpt-4o-transcribe (AUTO condition) and gpt-4o-mini-transcribe. Inspection of one example:

- **Utterance**: `1131474547_2_29212_1`
- **Reference** (Uzbek Latin): `sobiq boshlig'ining gaplari u qulog'idan kirib bu qulog'idan chiqmaydi`
- **gpt-4o-transcribe AUTO output**: `سابق باشلىقىنىڭ گەپلىرى بۇ قۇلاقتىن كىرىپ بۇ قۇلاقتىن چىقمايدۇ.` (Uyghur Arabic script)

This is **Uyghur Perso-Arabic script** — phonetically equivalent text in the Uyghur writing system. The utterance speaker likely has a voice/accent that the model auto-detects as Uyghur rather than Uzbek. The HINT condition (`prompt="Uzbek"`) prevents this: gpt-4o-transcribe HINT Uzbek achieves 100% Latin script, confirming the hint steers the model away from Uyghur.

**Impact**: 3/20 Uzbek utterances (15%) produce Uyghur Arabic output in AUTO condition for gpt-4o-transcribe. These are classified as WER=1.0 after normalisation (cross-script, as designed). The hallucination type is: `unrelated_language_output` (Uyghur instead of Uzbek).

**whisper-1 Uzbek LID confusion**: whisper-1 auto-detects Uzbek audio as 13 different languages across 40 calls: kazakh (10), turkish (7), tajik (6), azerbaijani (4), georgian (3), persian (3), mongolian (2), uzbek (2), arabic (1), pashto (1), tatar (1). Only 2/40 calls correctly return 'uzbek'. This is a severe LID failure for Uzbek audio, independent of the transcript quality.

---

## LID Tool Issues

### Custom LID limitations (fasttext unavailable)

The `custom_script_based_v1` LID uses Unicode character analysis:
- Kazakh identified by Kazakh-specific chars (қ, ğ, ụ, i, ä, ḥ)
- Kyrgyz identified by shared chars (ң, ö, ü) without Kazakh-specific ones
- **Standard-Cyrillic-only output** (e.g. gpt-4o-mini Kazakh→Kyrgyz) classified as `ru` — not `ky`
  This is incorrect for the actual content but correctly flags it as NOT Kazakh (`kk`).
- Uzbek Latin identified by heuristic (q/x frequency, o' g' patterns, English stopword exclusion)
- Short texts (<10 words) have lower LID reliability

**Action required**: Install MSVC Build Tools, then `pip install fasttext-wheel==0.9.2`, download `lid.176.bin`, re-run LID on all pilot records before scaling to 3,600.

---

## Cost Summary

| Item | Value |
|---|---|
| Total pilot cost (est.) | $0.1449 |
| Per-request average | $0.00060 |
| Phase 1 full run projection (×15, 3600/240) | $2.17 |
| Phase 1 estimate from config | $1.77–$2.13 |

---

## Reproducibility

- **Run ID**: `pilot_001`
- **Utterance selection**: first 20 per language in manifest order — deterministic
- **Request IDs**: `pilot_001_{model_abbrev}_{condition}_{utterance_id}` — deterministic
- **Audio manifest SHA-256**: `d01408af2e04d048a44600138ac878f97b2a2372f62b9a42f2f7d0b161f34924`
- **Dedup**: records written once, never overwritten; resume via skip-if-cached
- **Raw responses**: saved to `pilot_results/pilot_001/raw/`
- **Records**: `pilot_results/pilot_001/records/` — one JSON per request

---

## Pipeline Validation Verdict

The pilot validates that the benchmark pipeline is functional end-to-end:
- Audio files load and are accepted by all three OpenAI models
- Response parsing works for both `json` and `verbose_json` formats
- Normalization pipeline runs without errors on both Latin (Uzbek) and Cyrillic (Kazakh) text
- WER/CER computed correctly via `jiwer`
- Script detection works deterministically
- Per-request records and raw responses saved correctly
- Cost tracking per request is functional
- Dedup prevention verified (re-running the script skips existing records)

**Remaining blocker before full benchmark**: fasttext `lid.176.bin` LID tool must be installed.
All other pipeline components are validated.

---

*Pilot complete. Full 3,480-request benchmark NOT started.*
*No Phase 2 (GCP, Azure) calls made.*