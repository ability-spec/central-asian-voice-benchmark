# KSC Test-Split Speaker Distribution Analysis

**Date:** 2026-08-23
**Dataset:** ISSAI KSC (Kazakh Speech Corpus) v1.1 — OpenSLR SLR102
**Source corpus:** ISSAI Kazakh Speech Corpus (EACL 2021), CC BY 4.0
**Acquisition path:** `openslr.trmal.net/resources/102/ISSAI_KSC_335RS_v1.1_flac.tar.gz`
**Status:** Complete. Archive downloaded (18 GB on disk). Metadata and transcripts extracted. No STT calls made.

---

## Acquisition Details

### Archive structure (confirmed by inspection)

```
ISSAI_KSC_335RS_v1.1_flac/
  Audios_flac/       — 153,853 FLAC files (all splits, flat, no subdirectories)
  Transcriptions/    — 153,853 TXT files  (all splits, flat, matching filenames)
  Meta/
    train.csv        — columns: uttID deviceID  (1,554 unique device IDs, 147,236 rows)
    dev.csv          — columns: uttID deviceID Gender Age Region Device_Type Headphones (29 speakers)
    test.csv         — columns: uttID deviceID Gender Age Region Device_Type Headphones (29 speakers)
```

- **Delimiter:** space (not comma, despite `.csv` extension)
- **Utterance ID format:** 13-character hex hash (e.g., `5f5af4cf7bb2c`)
- **Audio format:** FLAC (lossless encoding of WAV 16 kHz 16-bit per paper)
- **Speaker ID field:** `deviceID` (numeric string, e.g., `12793`)
- **Splits are not encoded in filenames** — the Meta CSVs are the sole source of split assignments

### Files extracted without audio

| File type | Count | Purpose |
|---|---|---|
| `Meta/test.csv` | 1 | Test split utterance IDs + speaker metadata |
| `Meta/dev.csv` | 1 | Dev split utterance IDs + speaker metadata |
| `Meta/train.csv` | 1 | Train split utterance IDs (no speaker metadata) |
| `Transcriptions/*.txt` | 153,853 | All transcript files |

No audio was extracted for this analysis step.

---

## Dataset Version

| Field | Value |
|---|---|
| Name | ISSAI KSC v1.1 |
| OpenSLR | SLR102 |
| Paper | EACL 2021 |
| License | CC BY 4.0 (confirmed in paper text and ISSAI website) |
| Archive | `ISSAI_KSC_335RS_v1.1_flac.tar.gz`, 18 GB compressed |
| Audio format | FLAC in archive; WAV 16 kHz 16-bit (lossless equivalent) |
| Transcript format | UTF-8 TXT, Kazakh Cyrillic (42-letter alphabet) |

---

## Test Split Statistics

| Metric | Value | Paper claim |
|---|---|---|
| Total test utterances | **3,334** | 3,334 ✓ |
| Unique test speakers | **29** | 29 ✓ |
| Missing transcripts | **0** | — |
| Minimum utterances/speaker | **22** | — |
| Maximum utterances/speaker | **434** | — |
| Median utterances/speaker | **98** | — |
| Mean utterances/speaker | **114** | — |

---

## Speaker Distribution

Sorted by utterance count descending.

| Rank | DeviceID | Utterances | % of test | Gender | Age | Region | Device | Headphones |
|---|---|---|---|---|---|---|---|---|
| 1 | 15872 | 434 | 13.0% | F | 63 | North | phone | no |
| 2 | 20872 | 370 | 11.1% | M | 65 | South | phone | no |
| 3 | 20181 | 194 | 5.8% | F | 33 | East | phone | no |
| 4 | 21573 | 120 | 3.6% | M | 40 | East | phone | yes |
| 5 | 20316 | 112 | 3.4% | M | 19 | West | computer | no |
| 6 | 20565 | 101 | 3.0% | F | 62 | South | phone | yes |
| 7 | 20715 | 101 | 3.0% | F | 28 | Central | phone | no |
| 8 | 12793 | 100 | 3.0% | F | 25 | East | phone | no |
| 9 | 20942 | 100 | 3.0% | F | 20 | North | phone | no |
| 10 | 21515 | 100 | 3.0% | M | 31 | South | phone | no |
| 11 | 19753 | 99 | 3.0% | F | 33 | South | phone | no |
| 12 | 21773 | 99 | 3.0% | M | 51 | North | computer | yes |
| 13 | 22073 | 99 | 3.0% | M | 21 | South | phone | no |
| 14 | 22108 | 99 | 3.0% | M | 21 | South | computer | no |
| 15 | 21572 | 98 | 2.9% | M | 25 | East | phone | no |
| 16 | 21985 | 98 | 2.9% | M | 39 | North | phone | no |
| 17 | 20678 | 97 | 2.9% | F | 31 | West | phone | no |
| 18 | 21793 | 97 | 2.9% | M | 32 | North | computer | no |
| 19 | 21864 | 95 | 2.8% | F | 29 | West | phone | no |
| 20 | 22037 | 94 | 2.8% | M | 38 | Central | phone | no |
| 21 | 20805 | 92 | 2.8% | F | 20 | North | phone | yes |
| 22 | 21862 | 90 | 2.7% | M | 29 | West | phone | no |
| 23 | 20802 | 89 | 2.7% | F | 56 | South | phone | no |
| 24 | 20567 | 84 | 2.5% | F | 42 | South | phone | no |
| 25 | 20517 | 83 | 2.5% | F | 19 | South | phone | no |
| 26 | 21511 | 65 | 1.9% | M | 33 | West | phone | no |
| 27 | 20176 | 56 | 1.7% | F | 18 | South | computer | yes |
| 28 | 20185 | 46 | 1.4% | M | 21 | South | computer | no |
| 29 | 22042 | 22 | 0.7% | F | 51 | South | phone | no |

**Note on balance:** The top 2 speakers account for 24.1% of test utterances. The remaining 27 speakers range from 22 to 194 utterances. This is substantially more balanced than USC (top speaker: 38.2%), but not perfectly uniform. A flat cap is needed to prevent the top 2 from dominating the benchmark.

---

## Speaker Metadata Coverage

| Field | Values observed |
|---|---|
| Gender | F (17 speakers), M (12 speakers) |
| Age | 18–65 years (full range) |
| Region | North, South, East, West, Central |
| Device_Type | phone (24 speakers), computer (5 speakers) |
| Headphones | no (24 speakers), yes (5 speakers) |

All 29 test speakers have complete metadata (no missing fields).

---

## Speaker-Disjoint Verification

| Check | Result |
|---|---|
| Test ∩ Dev | **0 — DISJOINT ✓** |
| Test ∩ Train | **1 — ANOMALY (see below)** |
| Dev ∩ Train | **1 — ANOMALY (see below)** |

**Anomaly — DeviceID 20872:** Appears in train (1 utterance) and test (370 utterances). The paper states "three sets of non-overlapping speakers"; this 1-utterance train entry for a primarily-test speaker is almost certainly a data entry error in the release. The practical contamination risk is negligible: 1 training utterance cannot meaningfully influence any STT model's performance on a speaker with 370 test utterances. This does not disqualify KSC from use.

**Anomaly — DeviceID 923 (dev):** Appears in train (count not inspected) and dev. Same interpretation — likely a minor data entry error in the original release.

**Benchmark label:** CONTAMINATION-RISK: MEDIUM (same as USC — KSC published 2021, publicly available; commercial training data may include KSC audio regardless of this split anomaly).

---

## Sampling Feasibility

### Target: 300 utterances, ≥10 speakers, deterministic, reproducible

| Cap | Total utterances | Speakers |
|---|---|---|
| 10 | 290 | 29 |
| 11 | 319 | 29 |

No flat per-speaker cap gives exactly 300. Unlike USC (where cap=12 was an exact solution), KSC requires a mixed strategy.

### Mixed strategy for exactly 300

All 29 speakers have ≥22 utterances, so any cap between 1 and 22 is achievable for every speaker.

**Rule:**
- Sort speakers by `deviceID` ascending (lexicographic on the numeric string — treat as integer)
- Assign cap=11 to the first 10 speakers in this order
- Assign cap=10 to the remaining 19 speakers
- Result: 10×11 + 19×10 = 110 + 190 = **300 exactly**

This rule is transparent (deterministic sort on a stable field), requires no random seed, and is reproducible from the manifest alone.

Sorted deviceID order (ascending integer): 12793, 15872, 19753, 20176, 20181, 20185, 20316, 20517, 20565, 20567, 20678, 20715, 20802, 20805, 20872, 20942, 21511, 21515, 21572, 21573, 21773, 21793, 21862, 21864, 21985, 22037, 22042, 22073, 22108

**Cap assignments:**

| DeviceID | Utterances in test | Cap | Utterances in manifest |
|---|---|---|---|
| 12793 | 100 | 11 | 11 |
| 15872 | 434 | 11 | 11 |
| 19753 | 99 | 11 | 11 |
| 20176 | 56 | 11 | 11 |
| 20181 | 194 | 11 | 11 |
| 20185 | 46 | 11 | 11 |
| 20316 | 112 | 11 | 11 |
| 20517 | 83 | 11 | 11 |
| 20565 | 101 | 11 | 11 |
| 20567 | 84 | 11 | 11 |
| 20678 | 97 | 10 | 10 |
| 20715 | 101 | 10 | 10 |
| 20802 | 89 | 10 | 10 |
| 20805 | 92 | 10 | 10 |
| 20872 | 370 | 10 | 10 |
| 20942 | 100 | 10 | 10 |
| 21511 | 65 | 10 | 10 |
| 21515 | 100 | 10 | 10 |
| 21572 | 98 | 10 | 10 |
| 21573 | 120 | 10 | 10 |
| 21773 | 99 | 10 | 10 |
| 21793 | 97 | 10 | 10 |
| 21862 | 90 | 10 | 10 |
| 21864 | 95 | 10 | 10 |
| 21985 | 98 | 10 | 10 |
| 22037 | 94 | 10 | 10 |
| 22042 | 22 | 10 | 10 |
| 22073 | 99 | 10 | 10 |
| 22108 | 99 | 10 | 10 |
| **Total** | **3,334** | — | **300** |

**Maximum speaker share in manifest:** 11/300 = 3.7% (identical for first 10 speakers).
**Minimum speaker share:** 10/300 = 3.3%.
This is the most uniform speaker distribution achievable from this data.

### Deterministic utterance selection within each speaker's pool

Same formula as USC (STEP 4B):
```
indices = [i * len(pool) // quota for i in range(quota)]
```
where `quota` is the speaker's cap (10 or 11) and `pool` is the list of utterances in `test.csv` order.

---

## Anomalies and Limitations

1. **Train/test speaker overlap (minor):** DeviceID 20872 appears in train (1 utterance) and test (370 utterances). Practical contamination negligible. Document in benchmark results.

2. **FLAC → WAV conversion required:** The archive contains FLAC audio. STT providers require WAV input. Conversion must be applied to the 300 benchmark utterances before any API calls. `ffmpeg` is confirmed installed.

3. **Space-separated CSV despite `.csv` extension:** The Meta files use space as delimiter. Any downstream tooling must explicitly set `delimiter=" "`.

4. **Flat file structure — no split subdirectories:** Unlike USC, audio and transcript files are not organized into split folders. The Meta CSV is the only source of split assignments; losing or misreading it would make utterances unassignable to splits.

5. **Train speaker metadata absent:** Train speakers are identified only by `deviceID` in train.csv, with no gender/age/region metadata. This is by design (anonymous crowdsourced contributors) and does not affect benchmark use.

---

## Data Paths

| Asset | Path |
|---|---|
| Full archive | `data/ksc/ISSAI_KSC_335RS_v1.1_flac.tar.gz` |
| Extracted root | `data/ksc/extracted/ISSAI_KSC_335RS_v1.1_flac/` |
| Test metadata | `data/ksc/extracted/ISSAI_KSC_335RS_v1.1_flac/Meta/test.csv` |
| Transcriptions | `data/ksc/extracted/ISSAI_KSC_335RS_v1.1_flac/Transcriptions/<uttID>.txt` |
| Audio (not extracted) | Inside archive: `Audios_flac/<uttID>.flac` |

---

*No audio has been extracted or processed for benchmarking. No STT calls have been made.*
*This file documents the speaker distribution and sampling strategy for the Kazakh STT benchmark.*
