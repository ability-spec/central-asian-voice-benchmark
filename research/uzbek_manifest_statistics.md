# Uzbek Benchmark Manifest — Selection Rationale and Statistics

**Date:** 2026-08-23
**Manifest file:** `research/uzbek_benchmark_manifest.csv`
**Manifest SHA-256:** `61b235f0d33ea57ad8696dfae5146117ddde4965db589762ae48c0c2f0565c70`
**Status:** Manifest only. No audio downloaded. No STT calls made.

---

## Selection Rationale

### Source

Dataset: `murodbek/uzbek-speech-corpus`, split=`test`
Corpus: ISSAI Uzbek Speech Corpus, arXiv:2107.14419, CC BY 4.0
Test split: 3,837 utterances, 38 speakers

### Problem

The raw test split has extreme speaker imbalance due to two data sources
(audiobook narrators + crowdsourced volunteers):

- Top 3 speakers hold 74.2% of all test utterances.
- The single dominant speaker has 1,467 utterances (38.2%).
- Without a cap, a naive 300-utterance sample would be dominated by
  2–3 audiobook narrators and contain no representation from the other 35 speakers.

### Solution: Flat per-speaker cap of 12

A flat cap of **12 utterances per speaker** was chosen because:

1. It produces **exactly 300 utterances** with no rounding or adjustment:
   - 18 speakers have ≥12 utterances → each contributes exactly 12 (216 total).
   - 20 speakers have <12 utterances → each contributes their full count (84 total).
   - 216 + 84 = 300.

2. It represents **all 38 speakers** (every speaker contributes at least 1 utterance).

3. The dominant speaker's share drops from **38.2% → 4.0%** (12/300).
   No single speaker contributes more than 4.0%.

4. The rule is simple and transparent: no adaptive formula, no random seed.

### Deterministic selection within each speaker's pool

For speakers contributing their full pool (quota = actual count): all rows taken.

For speakers capped at 12 (quota < actual count): 12 rows are selected at
evenly-spaced positions in the speaker's row order:

```
indices = [i * len(pool) // 12 for i in range(12)]
```

This spreads the selection across the speaker's full contribution range
(avoiding clustering at the start) and is fully reproducible from the manifest ID list alone.

---

## Verification Results

| Check | Result |
|---|---|
| Total utterances | **300** (target: 300) |
| Unique speakers | **38** (target: ≥10) |
| Duplicate utterance IDs | **0** |
| All IDs in USC test split | **YES** |
| Minimum utterances/speaker | **1** |
| Maximum utterances/speaker | **12** |
| Median utterances/speaker | **11** |
| Manifest SHA-256 | `61b235f0d33ea57ad8696dfae5146117ddde4965db589762ae48c0c2f0565c70` |

---

## Speaker Distribution in Manifest

| Rank | Speaker ID | Utterances | % of benchmark | Utterances in raw test |
|---|---|---|---|---|
| 1 | 1131474547 | 12 | 4.0% | 33 |
| 2 | 1187023182 | 12 | 4.0% | 1467 |
| 3 | 1229529100 | 12 | 4.0% | 16 |
| 4 | 1289864764 | 12 | 4.0% | 216 |
| 5 | 1428043076 | 12 | 4.0% | 20 |
| 6 | 1571110404 | 12 | 4.0% | 720 |
| 7 | 265773029 | 12 | 4.0% | 107 |
| 8 | 351600865 | 12 | 4.0% | 17 |
| 9 | 382004286 | 12 | 4.0% | 20 |
| 10 | 467174862 | 12 | 4.0% | 21 |
| 11 | 709378413 | 12 | 4.0% | 79 |
| 12 | 709790549 | 12 | 4.0% | 60 |
| 13 | 752598988 | 12 | 4.0% | 12 |
| 14 | 807286871 | 12 | 4.0% | 12 |
| 15 | 818938633 | 12 | 4.0% | 228 |
| 16 | 909734087 | 12 | 4.0% | 661 |
| 17 | 961149717 | 12 | 4.0% | 31 |
| 18 | 972644779 | 12 | 4.0% | 33 |
| 19 | 1276148457 | 11 | 3.7% | 11 |
| 20 | 1569018008 | 9 | 3.0% | 9 |
| 21 | 712562200 | 9 | 3.0% | 9 |
| 22 | 1442646174 | 8 | 2.7% | 8 |
| 23 | 58016741 | 7 | 2.3% | 7 |
| 24 | 700747446 | 7 | 2.3% | 7 |
| 25 | 723788365 | 6 | 2.0% | 6 |
| 26 | 736041917 | 5 | 1.7% | 5 |
| 27 | 994543446 | 5 | 1.7% | 5 |
| 28 | 1450478900 | 3 | 1.0% | 3 |
| 29 | 1367046665 | 2 | 0.7% | 2 |
| 30 | 292385089 | 2 | 0.7% | 2 |
| 31 | 562907008 | 2 | 0.7% | 2 |
| 32 | 786373932 | 2 | 0.7% | 2 |
| 33 | 1126542829 | 1 | 0.3% | 1 |
| 34 | 1303352089 | 1 | 0.3% | 1 |
| 35 | 1489104080 | 1 | 0.3% | 1 |
| 36 | 668279160 | 1 | 0.3% | 1 |
| 37 | 705417050 | 1 | 0.3% | 1 |
| 38 | 795967678 | 1 | 0.3% | 1 |

---

## Source Type

All utterances are labelled `source_type = UNKNOWN`.

The paper describes two collection methods: (a) crowdsourcing via Telegram bot,
and (b) audiobooks (20 narrators, 30-min excerpts each). However, the released
dataset does not include a source-type field. Speaker IDs are Telegram user IDs
(numeric) for both sources. The audiobook speakers likely correspond to the
high-utterance-count speakers in the distribution, but this mapping is not
documented in the dataset card, paper, or GitHub repo. Assigning source_type
from utterance count alone would be speculation; UNKNOWN is the correct label.

---

## Contamination Risk

All selected utterances: **CONTAMINATION-RISK: MEDIUM**

The USC was published in 2021 and has been publicly available since.
Commercial model training data may include USC audio. This label applies
to every row in the manifest and must appear in all published result tables.

---

*No audio has been downloaded. No STT calls have been made.*
*This manifest pins the exact 300 utterances for the Uzbek STT benchmark.*
