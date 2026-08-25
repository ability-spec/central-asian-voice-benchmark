# Phase 3A Execution Plan — Central Asian STT Benchmark

**Status:** APPROVED 2026-08-25  
**Scope:** ElevenLabs Scribe v2 only. 200 new held-out utterances (100 Uzbek + 100 Kazakh). Routing evaluated analytically. No GCS, Azure, or Gemini in Phase 3A.  
**Phase 2 checkpoint:** `b7c9e84`

---

## A. Source Datasets and Selection Method

### Uzbek — `murodbek/uzbek-speech-corpus`, HuggingFace test split

Pool: 3,837 utterances, 38 speakers. Phase 2 consumed 300 utterances via `indices = [i * n // 12 for i in range(12)]` per speaker (n = speaker pool size, cap = 12).

**Phase 3A selection algorithm:**

1. Load Phase 2 frozen manifest (`research/uzbek_benchmark_manifest.csv`) to build excluded utterance-ID set.
2. Stream USC test split from HuggingFace. For each of the 38 speakers, collect all utterances not in excluded set, sorted in stable utterance-ID order.
3. Apply deterministic even-spacing to select up to `ceil(100 / 38)` = 3 utterances per speaker from the remaining pool. For the 26 speakers with the most remaining utterances, take 3; for the remaining 12, take 2. Confirm total = 100. Fallback: if any speaker has < 2 non-Phase-2 utterances, redistribute their slot to the speaker with the most remaining candidates.
4. Convert FLAC → WAV 16 kHz mono 16-bit PCM via ffmpeg (same command as `prepare_benchmark_audio.py`).

**Speaker-overlap acknowledgment:** All 38 USC speakers are also in Phase 2. Phase 3A uses different utterances from the same speakers. Disclose in all results; routing decisions operate per-utterance, but speaker-level bias cannot be ruled out.

### Kazakh — ISSAI KSC 335RS v1.1 FLAC archive

Pool: 3,034 non-Phase-2 test utterances with confirmed transcription files at  
`data/ksc/extracted/ISSAI_KSC_335RS_v1.1_flac/Transcriptions/<uttID>.txt`.  
Metadata: `data/ksc/extracted/ISSAI_KSC_335RS_v1.1_flac/Meta/test.csv` (space-delimited; fields: uttID, deviceID, Gender, Age, Region, Device_Type, Headphones).

**Phase 3A selection algorithm:**

1. Load Phase 2 Kazakh manifest (`research/kazakh_benchmark_manifest.csv`) to build excluded set (300 IDs).
2. From the 3,034 remaining KSC test entries, filter to those with confirmed transcription files (all 3,034 confirmed present).
3. Build stratification table: sort candidates by (Region, Gender, deviceID) for deterministic ordering.
4. Select 100 utterances by systematic sampling: every `floor(3034/100)` = 30th entry starting at index 0. Swap any selected entry below 0.5s duration with nearest neighbor.
5. Extract selected FLAC files from `data/ksc/ISSAI_KSC_335RS_v1.1_flac.tar.gz` in a single-pass batch scan. Convert each FLAC → WAV 16 kHz mono 16-bit PCM via ffmpeg.

---

## B. 200-Utterance Selection Strategy

**100 Uzbek**, duration-stratified to approximate Phase 2 Uzbek distribution:
- Short (<5s): target ~46 utterances
- Medium (5–10s): target ~44 utterances
- Long (>10s): target ~10 utterances

**100 Kazakh**, duration-stratified to approximate Phase 2 Kazakh distribution:
- Short (<5s): target ~20 utterances
- Medium (5–10s): target ~55 utterances
- Long (>10s): target ~25 utterances

**Zero-overlap assertion:** No utterance may appear in `research/audio_benchmark_manifest.csv` (SHA-256 `d01408af2e04d048a44600138ac878f97b2a2372f62b9a42f2f7d0b161f34924`). Assert at manifest build time that the intersection is empty.

**Split:**
- 40-utterance pilot: selected first (see Section C).
- 160-utterance evaluation set: remaining 60 Uzbek + 100 Kazakh. Pilot utterances are NOT repeated in evaluation. Total unique utterances = 200.

---

## C. 40-Utterance Pilot Selection

The pilot is a proper subset of the 200 evaluation utterances (not a separate corpus). Pilot stratum assignments:

| Stratum | Language | Count | Duration criterion | Selection rule |
|---|---|---|---|---|
| `uz_short` | Uzbek | 15 | duration_s < 5 | First 15 Uzbek utterances with duration_s < 5, in manifest order |
| `uz_medium` | Uzbek | 10 | 5 ≤ duration_s < 10 | First 10 Uzbek utterances with 5 ≤ duration_s < 10, in manifest order |
| `uz_control` | Uzbek | 5 | any duration | 5 Uzbek utterances from speakers whose Phase 2 AUTO detection accuracy was 100% (provider_detected_language == "uzb" on both Phase 2 AUTO calls for that speaker). Fill from highest Phase 2 AUTO detection rate speakers if fewer than 5 qualify. |
| `kk_short` | Kazakh | 5 | duration_s < 5 | First 5 Kazakh utterances with duration_s < 5, in manifest order |
| `kk_medium` | Kazakh | 5 | 5 ≤ duration_s < 10 | First 5 Kazakh utterances with 5 ≤ duration_s < 10, in manifest order |

**Total: 40 pilot utterances × 2 conditions = 80 ElevenLabs calls.**

The `uz_control` stratum is the sanity-check signal: if control utterances show high confusion or error, it indicates a provider regression or environment problem.

Non-pilot utterances: 160 rows with `pilot_stratum = ""` and `is_pilot = false`. These are the held-out evaluation set. No routing thresholds may be tuned on these 160 utterances.

---

## D. Manifest Format and SHA-256 Procedure

### `research/phase3a_uzbek_manifest.csv` (100 rows)

| Field | Type | Notes |
|---|---|---|
| utterance_id | string | USC format: `SPEAKERID_CHANNEL_CLIPID_SEGMENT` |
| speaker_id | string | Numeric speaker ID |
| transcript | string | Reference transcript (raw) |
| split | string | Always `test` |
| source_type | string | `UNKNOWN` (matches Phase 2) |
| pilot_stratum | string | `uz_short`, `uz_medium`, `uz_control`, or empty |

### `research/phase3a_kazakh_manifest.csv` (100 rows)

| Field | Type | Notes |
|---|---|---|
| utterance_id | string | Hex hash format |
| speaker_id | string | deviceID from KSC metadata |
| transcript | string | Reference transcript (raw) |
| split | string | Always `test` |
| language | string | Always `kk` |
| source_type | string | `studio_crowdsourced` |
| gender | string | From KSC metadata |
| age | string | From KSC metadata |
| region | string | From KSC metadata |
| device_type | string | From KSC metadata |
| headphones | string | From KSC metadata |
| pilot_stratum | string | `kk_short`, `kk_medium`, or empty |

### `research/phase3a_audio_manifest.csv` (200 rows)

Same schema as `research/audio_benchmark_manifest.csv` plus two new columns:

| Field | Type | Notes |
|---|---|---|
| utterance_id | string | |
| language | string | `uz` or `kk` |
| speaker_id | string | |
| reference_transcript | string | |
| canonical_audio_path | string | Absolute path to converted WAV |
| duration_seconds | float | Measured from actual WAV after conversion |
| source_dataset | string | `ISSAI_USC_v1_murodbek_hf` or `ISSAI_KSC_v1.1_SLR102` |
| pilot_stratum | string | Stratum label or empty string |
| is_pilot | boolean | `true` for 40 pilot rows, `false` for 160 evaluation rows |

### SHA-256 procedure

1. After writing `research/phase3a_audio_manifest.csv`, compute SHA-256 of the file bytes.
2. Hardcode the digest as `MANIFEST_SHA256` in `run_phase3a_trackb.py`.
3. At script startup, recompute SHA-256 and assert equality — abort if mismatch.
4. Per-utterance audio SHA-256 computed at submission time, stored in `audio_sha256` result field.

---

## E. API Request Matrix

**Provider:** ElevenLabs only. Model: `scribe_v2`.

| Call type | SDK call |
|---|---|
| AUTO | `client.speech_to_text.convert(file=audio_file, model_id="scribe_v2")` |
| HINT (Uzbek) | `client.speech_to_text.convert(file=audio_file, model_id="scribe_v2", language_code="uz")` |
| HINT (Kazakh) | `client.speech_to_text.convert(file=audio_file, model_id="scribe_v2", language_code="kk")` |

**Total API calls:** 200 × 2 = 400.

Response extraction:
- `result.text` → `raw_transcription` (raises `AttributeError` with diagnostics if field missing; no `str(result)` fallback)
- `getattr(result, 'language_code', None)` → `provider_detected_language`

Inner loop order: manifest row order; AUTO first, then HINT per utterance.

`benchmark_version`: `"phase3a_trackb_v1"` — hardcoded constant, written to every result record.

---

## F. Cost Estimate and Hard Cap

**Billing formula (ElevenLabs):**
```
cost_usd = (duration_s / 60.0) * 0.00367
```

**Estimated total (using Phase 2 duration distributions as proxy):**

| Segment | Count | Avg duration (s) | Conditions | Billed minutes | Estimated cost |
|---|---|---|---|---|---|
| Uzbek | 100 | 4.4 | 2 | 14.67 | $0.054 |
| Kazakh | 100 | 7.4 | 2 | 24.67 | $0.091 |
| **Total** | 200 | | | **39.33** | **$0.145** |

**Hard cap formula (from actual manifest durations, computed at prep time):**
```
pilot_budget   = sum(duration_s for pilot rows) * 2 / 60.0 * 0.00367
eval_budget    = sum(duration_s for non-pilot rows) * 2 / 60.0 * 0.00367
exact_estimate = pilot_budget + eval_budget
HARD_CAP       = max(round(exact_estimate * 2.5, 2), 0.50)
```

The 2.5× safety multiplier covers retries, duration measurement error, and minor rate changes. $0.50 floor prevents an absurdly low cap on unusually short audio. Print HARD_CAP at script startup; operator confirms before first API call.

---

## G. Retry, Restart, and Deduplication Design

**Deduplication key:** `(utterance_id, provider, language_condition)` — same as Phase 2.

**load_state() at startup:**
1. If `results/phase3a/phase3a_trackb_results.jsonl` exists, read all records.
2. Build `done` set: `{(r['utterance_id'], r['provider'], r['language_condition']) for r in records}`.
3. Accumulate `committed_spend`: sum `cost_usd` for records where `error_type` is null.
4. Skip any tuple already in `done`.

**Retry logic:**
- `MAX_RETRIES = 3` (attempts 0, 1, 2)
- Backoff: `time.sleep(2 ** attempt)` between attempts
- `AttributeError` on `result.text` → diagnostics, no retry, write error record
- Any other `Exception` → log, retry, then write error record after exhausting retries

**Cap enforcement (check_and_reserve):**
```python
projected = (duration_s / 60.0) * EL_RATE_PER_MIN
if committed_spend + projected > HARD_CAP:
    raise CapExceeded(...)
committed_spend += projected
```

On `CapExceeded`: write one abort record (`error_type="CapAborted"`, `cost_usd=0`), then exit.

**Progress logging:** every 25 utterances, print committed spend, cap, and completion percentage.

---

## H. Statistical Analysis Plan

Analysis is performed on the **160 held-out evaluation utterances** (`is_pilot = false`). Pilot utterances are reported separately but excluded from the primary hypothesis test.

### Step 1 — Baseline WER
For each of the 160 evaluation utterances: extract `wer_auto[i]` and `wer_hint[i]`.  
Report mean WER and 95% bootstrap CI for Always-AUTO and Always-HINT.

### Step 2 — Routing simulation (analytic, no additional API calls)

For each routing rule, compute `route[i] ∈ {AUTO, HINT}`:

**R1 (detected-language mismatch):**  
`route[i] = HINT if provider_detected_language[i] ≠ expected_iso3[language[i]] else AUTO`  
- expected_iso3: `{"uz": "uzb", "kk": "kaz"}`  
- null `provider_detected_language` → treat as mismatch (route to HINT)

**R2 (transcript script mismatch):**  
`route[i] = HINT if dominant_script_of(auto_transcript[i]) ≠ expected_script[language[i]] else AUTO`  
- expected scripts: Uzbek → Latin, Kazakh → Cyrillic  
- Script detection: if empty → HINT; if >50% alphabetic chars are Cyrillic → Cyrillic, else Latin  
- Null/empty auto transcript → HINT

**R1+R2 combined:**  
`route[i] = HINT if R1_triggers[i] OR R2_triggers[i] else AUTO`

**R3 (duration-based, exploratory only):**  
`route[i] = HINT if duration_s[i] < 5 else AUTO`  
R3 is reported for exploration; NOT used in the primary hypothesis test.

### Step 3 — Routing WER per rule
```
wer_routed[i] = wer_hint[i] if route[i] == HINT else wer_auto[i]
mean_wer_routed = mean(wer_routed)
```

### Step 4 — Oracle WER (upper bound)
```
wer_oracle[i] = min(wer_auto[i], wer_hint[i])
```
Reported as a reference; not used in hypothesis testing.

### Step 5 — Primary hypothesis test (per routing rule)
- H₀: mean(wer_routed) ≥ mean(wer_hint)
- H₁: mean(wer_routed) < mean(wer_hint)
- Test: paired Wilcoxon signed-rank, large-sample normal approximation (scipy.stats.wilcoxon, `alternative='less'`)
- Significance threshold: p < 0.05

### Step 6 — Bootstrap confidence intervals
- 5,000 resamples with replacement on the 160-length difference vector `d[i] = wer_routed[i] − wer_hint[i]`
- Report 95% CI: [2.5th, 97.5th] percentile

### Step 7 — Primary success criterion
Both must hold simultaneously for a routing rule to be declared successful:
1. mean(wer_routed) − mean(wer_hint) ≤ −0.030 (WER improvement ≥ 0.030 absolute)
2. Wilcoxon p < 0.05

### Step 8 — Subgroup breakdowns
Report mean WER (routed vs HINT vs AUTO) for:
- Uzbek evaluation utterances (60)
- Kazakh evaluation utterances (100)
- Short duration (<5s)
- Medium duration (5–10s)
- By pilot stratum (representativeness check)

### Step 9 — Routing trigger rate analysis
For each rule:
- Count utterances that triggered the rule (route = HINT)
- Among triggered: mean WER(HINT) vs mean WER(AUTO)
- Among untriggered: mean WER(AUTO)

---

## I. Pilot Go/No-Go Criteria

Pilot (80 calls) must complete before the remaining 160 evaluation utterances are submitted. Human review required before proceed decision.

**Automatic ABORT (any single condition):**

| Condition | Threshold |
|---|---|
| Call error rate (error_type not null) | > 20% (> 16 of 80) |
| All Uzbek HINT calls return non-Latin script | 40 of 40 (zero correct script output) |
| HTTP 4xx on ≥ 5 calls | Unsupported language or format rejection |
| Actual pilot cost > 2× pilot_budget | Cap enforcement failure |

**Flagged for human review (explicit decision required before proceeding):**

| Condition | Flag |
|---|---|
| Error rate 10–20% (8–16 of 80) | High error rate — investigate |
| Uzbek AUTO detection accuracy < 30% (< 12 of 40) | Unusually low detection |
| uz_control stratum: > 1 of 5 calls error | Possible environment regression |
| retry_count = 2 on > 5 calls | Latency or connectivity issues |
| Pilot mean WER differs from Phase 2 EL overall by > 0.10 | Corpus quality or format issue |

**PROCEED conditions (all required):**

1. Error rate < 10% (< 8 of 80 calls)
2. ≥ 20 of 40 Uzbek AUTO calls return Latin-script output
3. ≥ 35 of 40 Kazakh AUTO calls return Cyrillic-script output (Phase 2 baseline: 97%)
4. No HTTP 4xx authentication or format error
5. Actual pilot cost within 2× of pilot_budget estimate

**Pilot report before go/no-go decision:**
- Detection accuracy by language and condition (4 cells: uz/kk × auto/hint)
- Mean WER by stratum
- Latency p50/p95 (ms)
- Actual cost vs estimate
- List any records with error_type not null

---

## J. Files That Will Be Created

### Preparation phase (no API calls)

| File | Description |
|---|---|
| `research/phase3a_uzbek_manifest.csv` | 100-row Uzbek utterance manifest |
| `research/phase3a_kazakh_manifest.csv` | 100-row Kazakh utterance manifest |
| `research/phase3a_audio_manifest.csv` | 200-row combined audio manifest; SHA-256 hardcoded before first run |
| `data/audio/phase3a/uz/<uttID>.wav` | 100 converted Uzbek WAV files (16 kHz mono PCM) |
| `data/audio/phase3a/kk/<uttID>.wav` | 100 converted Kazakh WAV files (16 kHz mono PCM) |

### Execution phase

| File | Description |
|---|---|
| `results/phase3a/run_phase3a_trackb.py` | Execution script based on `run_phase2_trackb.py`; BENCHMARK_VERSION="phase3a_trackb_v1"; ElevenLabs only |
| `results/phase3a/phase3a_trackb_results.jsonl` | 400 result records written incrementally during run |

### Analysis phase

| File | Description |
|---|---|
| `research/kaggle_phase3a_analysis.ipynb` | Analysis notebook: routing simulation, Wilcoxon test, bootstrap CIs, subgroup breakdowns |

### Files NOT touched by Phase 3A

- `research/audio_benchmark_manifest.csv` — frozen
- `research/uzbek_benchmark_manifest.csv` — frozen
- `research/kazakh_benchmark_manifest.csv` — frozen
- `results/phase2_full/` — not modified
- `results/phase2_micropilot/` — not modified
- No GitHub push during Phase 3A
- No Kaggle publish during Phase 3A

---

## K. Risks and Possible Failure Modes

**1. USC audio download latency**  
HuggingFace streaming for 100 Uzbek utterances, no local cache. Mitigation: batch download with per-file retry; verify SHA-256 of each WAV after conversion; do not start API calls until all 200 WAV files are present and verified.

**2. USC speaker overlap (limitation, not a failure)**  
All 38 USC speakers are in Phase 2. Phase 3A routing evaluation is sensitive to speaker-level variation already seen in Phase 2. Mitigation: disclose prominently; include per-speaker analysis; acknowledge generalization to unseen speakers is unverified.

**3. KSC batch extraction performance**  
Extracting 100 FLAC files from an 18.2 GB tar requires a single sequential scan. Mitigation: extract all 100 Kazakh files in one pass, matching by `ISSAI_KSC_335RS_v1.1_flac/Audios_flac/<uttID>.flac`. Confirm all 100 files extracted before any API calls.

**4. Low R1/R2 trigger rate on Kazakh**  
Phase 2: Kazakh AUTO detection was 97% correct. R1 and R2 will trigger on very few Kazakh utterances. Routing benefit will be concentrated in Uzbek. Mitigation: report language-level subgroup analysis explicitly; do not aggregate if one language dominates the routing signal.

**5. Routing improves WER but misses the 0.030 threshold**  
Valid informative null result — establishes signal is real but below pre-registered minimum effect size. Report point estimate and CI regardless of threshold outcome; do not post-hoc adjust the threshold.

**6. Hard cap underestimate**  
If Phase 3A audio is systematically longer than Phase 2 proxy. Mitigation: the 2.5× HARD_CAP formula and $0.50 floor; cap is enforced per-call and halts safely. Partial results are valid for completed utterances; raise cap before resuming.

**7. `result.text` field missing on EL SDK schema change**  
Mitigation: identical `AttributeError` guard as Phase 2; pin ElevenLabs SDK version in `requirements-phase3a.txt`; verify version before run.

**8. Circularity — routing threshold contamination**  
R1 and R2 are purely binary (no free threshold to tune on Phase 3A data). R3 uses the Phase 2 empirically-determined <5s threshold — acceptable as Phase 2 motivated the hypothesis and Phase 3A is the held-out test. What is NOT acceptable: any adjustment to threshold, detection-language codes, or script-detection criterion after examining Phase 3A results. All rules must be locked before any Phase 3A data is seen.

**9. Pilot fails at authentication step**  
All 80 pilot calls fail immediately. Zero billing impact. Resolve credentials; `load_state()` restart ensures no re-billing.

**10. Phase 3A results identical to Phase 2**  
Positive scientific result (reproducibility). Routing hypothesis may still be confirmed or rejected on the 160-utterance evaluation set.

---

## Tomorrow's Preparation Checklist

Before any API calls:

- [ ] Build `research/phase3a_uzbek_manifest.csv` (100 rows, no Phase 2 overlap verified)
- [ ] Build `research/phase3a_kazakh_manifest.csv` (100 rows, no Phase 2 overlap verified)
- [ ] Download/stream 100 Uzbek WAV files from HuggingFace; verify each SHA-256
- [ ] Extract 100 Kazakh FLAC files from tar in single batch pass; convert to WAV; verify each SHA-256
- [ ] Build `research/phase3a_audio_manifest.csv` (200 rows); compute and record its SHA-256
- [ ] Compute HARD_CAP from actual manifest durations; confirm it is printed at script startup
- [ ] Write `results/phase3a/run_phase3a_trackb.py`; static validation (imports, constants, manifest hash check)
- [ ] Confirm ELEVENLABS_API_KEY is set in environment (do not paste value into any file or conversation)
- [ ] Dry-run script with `--dry-run` flag (or equivalent) to verify all audio paths resolve
- [ ] Run 40-utterance pilot (80 calls); collect pilot report
- [ ] STOP for human go/no-go review before submitting remaining 160 utterances
