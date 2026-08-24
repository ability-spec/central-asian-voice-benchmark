# USC Test-Split Speaker Distribution Analysis

**Date:** 2026-08-23
**Dataset:** murodbek/uzbek-speech-corpus, split=test
**Source corpus:** ISSAI Uzbek Speech Corpus (arXiv:2107.14419)
**Status:** Metadata only — no audio downloaded, no STT calls.

---

## Summary Statistics

| Metric | Value |
|---|---|
| Total test utterances | 3,837 |
| Unique speakers | 38 |
| Minimum utterances/speaker | 1 |
| Maximum utterances/speaker | 1,467 |
| Median utterances/speaker | 11 |
| Mean utterances/speaker | 100 |

---

## Full Speaker Distribution

Sorted by utterance count descending.

| Rank | Speaker ID | Utterances | % of test split | Category |
|---|---|---|---|---|
| 1 | 1187023182 | 1467 | 38.2% | dominant (audiobook) |
| 2 | 1571110404 | 720 | 18.8% | dominant (audiobook) |
| 3 | 909734087 | 661 | 17.2% | dominant (audiobook) |
| 4 | 818938633 | 228 | 5.9% | dominant (audiobook) |
| 5 | 1289864764 | 216 | 5.6% | dominant (audiobook) |
| 6 | 265773029 | 107 | 2.8% | large |
| 7 | 709378413 | 79 | 2.1% | large |
| 8 | 709790549 | 60 | 1.6% | large |
| 9 | 1131474547 | 33 | 0.9% | medium |
| 10 | 972644779 | 33 | 0.9% | medium |
| 11 | 961149717 | 31 | 0.8% | medium |
| 12 | 467174862 | 21 | 0.5% | medium |
| 13 | 1428043076 | 20 | 0.5% | medium |
| 14 | 382004286 | 20 | 0.5% | medium |
| 15 | 351600865 | 17 | 0.4% | medium |
| 16 | 1229529100 | 16 | 0.4% | medium |
| 17 | 752598988 | 12 | 0.3% | medium |
| 18 | 807286871 | 12 | 0.3% | medium |
| 19 | 1276148457 | 11 | 0.3% | medium |
| 20 | 1569018008 | 9 | 0.2% | sparse |
| 21 | 712562200 | 9 | 0.2% | sparse |
| 22 | 1442646174 | 8 | 0.2% | sparse |
| 23 | 58016741 | 7 | 0.2% | sparse |
| 24 | 700747446 | 7 | 0.2% | sparse |
| 25 | 723788365 | 6 | 0.2% | sparse |
| 26 | 736041917 | 5 | 0.1% | sparse |
| 27 | 994543446 | 5 | 0.1% | sparse |
| 28 | 1450478900 | 3 | 0.1% | sparse |
| 29 | 1367046665 | 2 | 0.1% | sparse |
| 30 | 292385089 | 2 | 0.1% | sparse |
| 31 | 562907008 | 2 | 0.1% | sparse |
| 32 | 786373932 | 2 | 0.1% | sparse |
| 33 | 1126542829 | 1 | 0.0% | sparse |
| 34 | 1303352089 | 1 | 0.0% | sparse |
| 35 | 1489104080 | 1 | 0.0% | sparse |
| 36 | 668279160 | 1 | 0.0% | sparse |
| 37 | 705417050 | 1 | 0.0% | sparse |
| 38 | 795967678 | 1 | 0.0% | sparse |

---

## Speakers with Fewer Than 10 Utterances

**19 speakers** have fewer than 10 test utterances.

| Speaker ID | Utterances |
|---|---|
| 1126542829 | 1 |
| 1303352089 | 1 |
| 1489104080 | 1 |
| 668279160 | 1 |
| 705417050 | 1 |
| 795967678 | 1 |
| 1367046665 | 2 |
| 292385089 | 2 |
| 562907008 | 2 |
| 786373932 | 2 |
| 1450478900 | 3 |
| 736041917 | 5 |
| 994543446 | 5 |
| 723788365 | 6 |
| 58016741 | 7 |
| 700747446 | 7 |
| 1442646174 | 8 |
| 1569018008 | 9 |
| 712562200 | 9 |

---

## Sampling Feasibility Assessment

**Target:** 300 utterances, ≥10 speakers, no single speaker dominating.

With an uncapped draw, the dominant speaker would contribute:
- Speaker 1187023182: 1467 utterances (38.2% of test split)

**Capped sampling simulation (cap = 50 utterances/speaker):**
- Total available utterances at cap 50: 699
- Speakers with ≥1 utterance: 38
- A 300-utterance sample is feasible with this cap: YES

## Recommended Sampling Strategy

**Step 1 — Assign per-speaker quota.**
Sort speakers by utterance count ascending. Assign each speaker a quota of
min(actual_count, ceil(300 / remaining_speakers_with_quota)) utterances,
distributing any remainder to larger speakers. This ensures every speaker
with ≥1 utterance is represented while capping the dominant speaker's share.

**Step 2 — Deterministic row selection.**
Within each speaker's pool, select utterances at evenly-spaced indices
(not random) using `sorted_indices[::step]` where step = len(pool) // quota.
This makes the sample reproducible without a random seed.

**Step 3 — Verify speaker count.**
After sampling, confirm ≥10 distinct speaker IDs are present.
If any speaker contributes 0 utterances (quota rounds to 0), redistribute
that speaker's slot to the next-largest speaker.

**Step 4 — Record the sample manifest.**
Save the selected `id` values as a flat list in a manifest file.
The manifest pins the exact 300 utterances before any API call is made.
SHA-256 of the manifest file is recorded as part of benchmark metadata.

