# Kazakh Benchmark Manifest — Selection Rationale and Statistics

**Date:** 2026-08-23
**Manifest file:** `research/kazakh_benchmark_manifest.csv`
**Manifest SHA-256:** `a068cd81c958c687b8239a1bdc73b55586fe98f7a218b8ca51b3fda517c89507`
**Status:** Manifest only. No audio downloaded. No STT calls made.

---

## Source

Dataset: ISSAI KSC v1.1 — OpenSLR SLR102
Corpus: ISSAI Kazakh Speech Corpus (EACL 2021), CC BY 4.0
Test split: 3,334 utterances, 29 speakers
Metadata: `Meta/test.csv` (space-separated: uttID deviceID Gender Age Region Device_Type Headphones)
Audio: `Audios_flac/<uttID>.flac` (FLAC lossless, WAV 16 kHz 16-bit equivalent)

---

## Sampling Rule

### Why a cap is needed

The raw test split has moderate speaker imbalance:
- Top speaker (deviceID 15872): 434 utterances (13.0% of test split)
- Top 2 speakers: 804 utterances (24.1% of test split)
- Without a cap, a 300-utterance sample would over-represent these 2 speakers
  (e.g., speaker 15872 alone would contribute ~39 utterances at proportional sampling)

### Cap calculation

Unlike USC (where a flat cap of 12 gave exactly 300), KSC requires a mixed strategy:

| Cap | Total utterances |
|---|---|
| 10 | 290 (10 short) |
| 11 | 319 (19 over) |

**Solution:** Give 10 speakers cap=11 and 19 speakers cap=10.
10×11 + 19×10 = 110 + 190 = **300 exactly**.

### Which speakers get cap=11

Sort speakers by `deviceID` ascending (as integer).
Assign cap=11 to the first 10 in this order; cap=10 to the remaining 19.
This rule is transparent (deterministic sort on a stable numeric field),
requires no random seed, and is reproducible from the manifest alone.

### Utterance selection within each speaker's pool

Pool = all test.csv rows for that speaker, in file order.
For speaker with pool size `n` and quota `q`:

```
indices = [i * n // q for i in range(q)]
```

This spreads selection across the speaker's full row range deterministically.
(Same formula used in the Uzbek USC manifest, STEP 4B.)

---

## Anomaly: DeviceID 20872 Train/Test Overlap

DeviceID 20872 appears in both `train.csv` (1 utterance) and `test.csv` (370 utterances).
The paper states 'three sets of non-overlapping speakers'; this is a minor data release error.

**Mitigation applied:**
Before finalizing selection for speaker 20872, the single train uttID was identified.
All 10 selected utterances for this speaker were checked against the train set.

**Result: No anomaly hit.** None of the 10 evenly-spaced indices for speaker 20872
landed on the single train uttID. The 10 selected utterances are all test-only.
The manifest is free of train contamination for this speaker.

The selected 300 utterances have been verified to contain no train uttIDs.

---

## Verification Results

| Check | Result |
|---|---|
| Total utterances | **300** (target: 300) |
| Unique speakers | **29** (target: 29) |
| Duplicate utterance IDs | **0** |
| All IDs in KSC test split | **YES** |
| Any ID in KSC train split | **NO** |
| Missing transcripts | **0** |
| Missing required fields | **0** |
| Speaker cap compliance | **YES** — all speakers match intended cap |
| Minimum utterances/speaker | **10** |
| Maximum utterances/speaker | **11** |
| Median utterances/speaker | **10** |
| Manifest SHA-256 | `a068cd81c958c687b8239a1bdc73b55586fe98f7a218b8ca51b3fda517c89507` |

---

## Speaker Distribution in Manifest

| Rank | DeviceID | Utterances | % of benchmark | Cap | Gender | Age | Region | Device | Headphones |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 12793 | 11 | 3.7% | 11 | F | 25 | East | phone | no |
| 2 | 15872 | 11 | 3.7% | 11 | F | 63 | North | phone | no |
| 3 | 19753 | 11 | 3.7% | 11 | F | 33 | South | phone | no |
| 4 | 20176 | 11 | 3.7% | 11 | F | 18 | South | computer | yes |
| 5 | 20181 | 11 | 3.7% | 11 | F | 33 | East | phone | no |
| 6 | 20185 | 11 | 3.7% | 11 | M | 21 | South | computer | no |
| 7 | 20316 | 11 | 3.7% | 11 | M | 19 | West | computer | no |
| 8 | 20517 | 11 | 3.7% | 11 | F | 19 | South | phone | no |
| 9 | 20565 | 11 | 3.7% | 11 | F | 62 | South | phone | yes |
| 10 | 20567 | 11 | 3.7% | 11 | F | 42 | South | phone | no |
| 11 | 20678 | 10 | 3.3% | 10 | F | 31 | West | phone | no |
| 12 | 20715 | 10 | 3.3% | 10 | F | 28 | Central | phone | no |
| 13 | 20802 | 10 | 3.3% | 10 | F | 56 | South | phone | no |
| 14 | 20805 | 10 | 3.3% | 10 | F | 20 | North | phone | yes |
| 15 | 20872 | 10 | 3.3% | 10 | M | 65 | South | phone | no |
| 16 | 20942 | 10 | 3.3% | 10 | F | 20 | North | phone | no |
| 17 | 21511 | 10 | 3.3% | 10 | M | 33 | West | phone | no |
| 18 | 21515 | 10 | 3.3% | 10 | M | 31 | South | phone | no |
| 19 | 21572 | 10 | 3.3% | 10 | M | 25 | East | phone | no |
| 20 | 21573 | 10 | 3.3% | 10 | M | 40 | East | phone | yes |
| 21 | 21773 | 10 | 3.3% | 10 | M | 51 | North | computer | yes |
| 22 | 21793 | 10 | 3.3% | 10 | M | 32 | North | computer | no |
| 23 | 21862 | 10 | 3.3% | 10 | M | 29 | West | phone | no |
| 24 | 21864 | 10 | 3.3% | 10 | F | 29 | West | phone | no |
| 25 | 21985 | 10 | 3.3% | 10 | M | 39 | North | phone | no |
| 26 | 22037 | 10 | 3.3% | 10 | M | 38 | Central | phone | no |
| 27 | 22042 | 10 | 3.3% | 10 | F | 51 | South | phone | no |
| 28 | 22073 | 10 | 3.3% | 10 | M | 21 | South | phone | no |
| 29 | 22108 | 10 | 3.3% | 10 | M | 21 | South | computer | no |

---

## Speaker Metadata Coverage in Manifest

| Field | Distribution |
|---|---|
| Gender | F: 15, M: 14 |
| Age range | 18–65 years (median 31) |
| Region | Central: 2, East: 4, North: 6, South: 12, West: 5 |
| Device type | computer: 6, phone: 23 |
| Headphones | no: 24, yes: 5 |

---

## Source Type

All utterances: `source_type = studio_crowdsourced`

KSC v1.1 was collected via a mobile application deployed to crowdsourced volunteers.
Speakers read prompted text in a controlled (studio-quality) mobile-recording environment.
This is READ speech (prompted text), not spontaneous conversational speech.
The source type applies uniformly to all 29 test speakers.

---

## Contamination Risk

All selected utterances: **CONTAMINATION-RISK: MEDIUM**

KSC was published in 2021 and has been publicly available since.
Commercial model training data may include KSC audio. This label applies
to every row in the manifest and must appear in all published result tables.

---

## License

**CC BY 4.0** — confirmed in EACL 2021 paper text and ISSAI website.
Attribution required. Commercial and research use permitted.
The HuggingFace card for `issai/kazakh_speech_corpus` incorrectly states MIT;
the authoritative license is CC BY 4.0 from the ISSAI website and paper.

---

*No audio has been downloaded for benchmarking. No STT calls have been made.*
*This manifest pins the exact 300 utterances for the Kazakh STT benchmark.*
