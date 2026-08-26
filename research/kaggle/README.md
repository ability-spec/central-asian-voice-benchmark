# Central Asian AI Voice Benchmark

**Languages:** Uzbek (uz-UZ) · Kazakh (kk-KZ)  
**Phase:** 2 (multi-provider) + Phase 3A (routing study)  
**Status:** Analysis complete — no production deployment recommendation

---

## Research Objective

Benchmark existing automatic speech recognition (ASR) systems for Uzbek and Kazakh, with a focus on whether providing an explicit language hint (`hint` condition) improves recognition accuracy over relying on the model's automatic language detection (`auto` condition). Phase 3A additionally tests whether a post-hoc routing rule (R1) can selectively apply the hint only when auto-detection fails, achieving the accuracy of always-hint at lower operational cost.

This is a **research benchmark only**. No product recommendation is made.

---

## Languages Evaluated

| Language | ISO 639-1 | BCP-47 | Script | Corpus |
|---|---|---|---|---|
| Uzbek | uz | uz-UZ | Latin | ISSAI USC v1 (Murodbek subset, HuggingFace) |
| Kazakh | kk | kk-KZ | Cyrillic | ISSAI KSC 335RS |

Both corpora are ISSAI (Institute of Smart Systems and Artificial Intelligence) collections. ISSAI USC is sourced from multiple recording sessions; the Kazakh corpus is drawn from ISSAI KSC 335RS. Contamination risk for USC is rated MEDIUM (web-sourced data may overlap with provider training sets); this is a known limitation.

---

## Providers and Models Evaluated

| Phase | Provider | Model | Conditions |
|---|---|---|---|
| Phase 2 | ElevenLabs | Scribe v2 | auto, hint |
| Phase 2 | Google Cloud STT | Chirp 2 | auto, hint |
| Phase 3A | ElevenLabs | Scribe v2 | auto, hint |

Phase 3A covers ElevenLabs Scribe v2 only. Google Cloud STT Chirp 2 was not re-evaluated in Phase 3A.

---

## Dataset Scope

### Phase 2

- **Track:** B (frozen corpus; disjoint from public FLEURS benchmarks)
- **Utterances:** 300 Uzbek + 300 Kazakh (600 total per provider)
- **Records:** 2 providers × 2 conditions × 600 utterances = **2,400 records**
- **Spend:** ElevenLabs $0.433, GCS $6.363 — total **$6.796**

### Phase 3A

- **Utterances:** 200 total (separate from Phase 2, disjoint)
  - 40-utterance pilot (30 Uzbek + 10 Kazakh)
  - 160-utterance evaluation (**70 Uzbek + 90 Kazakh**)
- **Records:** 200 utterances × 2 conditions = 400 successful (+ 68 historical errors excluded)
- **Spend:** ElevenLabs Scribe v2 only — **$0.150**

The execution plan anticipated 60 Uzbek + 100 Kazakh in evaluation. The actual split is 70 + 90 because the pilot stratum composition (30 Uzbek + 10 Kazakh) differed from the planned equal split. All analyses use the actual counts.

---

## Evaluation Methodology

### Text normalisation

Applied identically to reference and hypothesis:
1. Unicode NFC normalisation
2. Casefold (Unicode-aware lowercase)
3. Apostrophe unification (`'` `'` `ʼ` `` ` `` → `'`)
4. Punctuation stripped (non-word, non-space, non-apostrophe characters → space)
5. Whitespace collapse

### Metrics

- **WER** (Word Error Rate): Levenshtein edit distance at word level ÷ reference word count
- **CER** (Character Error Rate): Levenshtein edit distance at character level ÷ reference character count

Stored values in the JSONL files are authoritative. The notebook recomputes from stored values to verify.

### Conditions

- `auto`: No language specified. Provider detects language automatically.
- `hint`: Explicit language code passed in the API request (`uz-UZ` or `kk-KZ`).
- `routed` (Phase 3A, derived): Applies the R1 rule post-hoc to the stored AUTO and HINT results.

---

## Primary Routing Test

**Pre-specified primary test** (execution plan, Section H, Steps 5–7):

Define `d[i] = wer_routed[i] − wer_hint[i]` for each evaluation utterance.

**R1 routing rule:** If the AUTO call's `provider_detected_language` ≠ expected ISO 639-3 code (`uzb` for Uzbek, `kaz` for Kazakh), use the HINT WER; otherwise use the AUTO WER.

**H₁:** mean(d) < 0 — routing beats always-HINT.

**Success criterion (both required):**
1. mean(d) ≤ −0.030
2. Wilcoxon signed-rank p < 0.05

| Population | n | mean(d) | Wilcoxon W⁺ | p (H₁: less) |
|---|---|---|---|---|
| Overall | 160 | **+0.0005** | 106.5 | **0.820** |
| Uzbek | 70 | **−0.0043** | 6.0 | **0.642** |
| Kazakh | 90 | **+0.0042** | 63.5 | **0.755** |

**Result: Neither success condition is met.** The mean difference is +0.0005 overall — routing is essentially equivalent to always-HINT, not better. The threshold mean(d) ≤ −0.030 is not approached.

---

## Secondary AUTO vs HINT Analysis

**Not the primary criterion.** Defined as `d[i] = wer_auto[i] − wer_hint[i]`. H₁: mean(d) > 0 (HINT is better than AUTO).

| Population | n | nonzero pairs | mean(d) | Wilcoxon W⁺ | p (H₁: greater) |
|---|---|---|---|---|---|
| Overall | 160 | 30 | +0.0130 | 302.5 | **0.075** |
| Uzbek | 70 | 16 | +0.0243 | 92.5 | **0.103** |
| Kazakh | 90 | 14 | +0.0042 | 63.5 | **0.245** |

The overall p=0.075 is below α=0.10 but does not reach α=0.05. HINT is directionally better for Uzbek; for Kazakh the difference is negligible.

---

## Key Findings

All findings below are descriptive or statistically supported; none constitute a production recommendation.

**Phase 2 WER (evaluation corpus, mean):**

| Provider | Model | Uzbek AUTO | Uzbek HINT | Kazakh AUTO | Kazakh HINT |
|---|---|---|---|---|---|
| ElevenLabs | Scribe v2 | 0.3416 | 0.2446 | 0.0534 | 0.0510 |
| GCS | Chirp 2 | 0.4227 | 0.2602 | 0.2666 | 0.2112 |

ElevenLabs Scribe v2 outperforms GCS Chirp 2 on both languages under both conditions, at approximately 15× lower cost per call.

**Phase 3A detection accuracy (AUTO condition):**
- Uzbek: 19/70 utterances correctly detected (27.1%) — 73% misdetected, primarily as Turkish (18), English (12), Russian (3)
- Kazakh: 89/90 utterances correctly detected (98.9%)

The low Uzbek detection rate is the primary driver of the AUTO vs HINT accuracy gap. Kazakh detection is highly reliable; the hint provides negligible benefit for Kazakh.

**R1 routing rates:**
- Uzbek: 73% of utterances routed to HINT
- Kazakh: 1% routed to HINT
- Overall: 32.5% routed to HINT

**Routing vs AUTO (secondary observation):**
R1 routing reduces Uzbek WER from 0.2906 (AUTO) to 0.2620 (−10% relative). Overall reduction: 0.1664 → 0.1539 (−7.5%). However, routing produces results nearly identical to always-HINT (0.1539 vs 0.1534 overall), providing no incremental benefit over simply passing the hint unconditionally.

---

## Limitations

1. **Sample size:** 70 Uzbek + 90 Kazakh evaluation utterances in Phase 3A. Small sample; individual effect variance dominates.
2. **Single provider (Phase 3A):** Routing findings apply to ElevenLabs Scribe v2 only.
3. **Apostrophe confound:** 7 of 70 Uzbek HINT records have elevated WER due to apostrophe stripping in normalisation.
4. **Cross-phase comparability:** Phase 2 and Phase 3A use disjoint utterance sets from the same corpus. WER comparisons between phases are indicative, not directly comparable.
5. **Uzbek duration skew:** Uzbek Phase 3A is skewed toward short utterances (71% short vs 46% planned), inflating WER relative to a balanced sample.
6. **Corpus contamination:** ISSAI USC is rated MEDIUM contamination risk. Provider training data may overlap with this corpus.
7. **Phase 3B deferred:** Azure Speech Fast Transcription benchmarking was deferred; no Azure results are included.

---

## Cost

| Phase | Provider | Spend |
|---|---|---|
| Phase 2 | ElevenLabs Scribe v2 | $0.4332 |
| Phase 2 | GCS Chirp 2 | $6.3630 |
| Phase 3A | ElevenLabs Scribe v2 | $0.1497 |
| **Total** | | **$9.12** |

All cost figures are per-call USD at published list prices as recorded in the benchmark JSONL files. No cost estimation or interpolation was performed.

---

## Reproducibility

This publication package performs **analysis only** and does **not** make API calls, run new benchmark evaluations, or modify source data files.

**Requirements:**
```
python >= 3.9
pandas
numpy
matplotlib
```

No `scipy` is required — the Wilcoxon test is implemented in pure Python (validated against scipy 1.18.1 to within ±0.00003 on p-values).

**Running locally:**
```bash
cd research/kaggle   # this directory
jupyter notebook central_asian_voice_benchmark.ipynb
```

**Running on Kaggle:**
1. Upload `phase2_trackb_results.jsonl` and `phase3a_trackb_results.jsonl` as a Kaggle dataset.
2. Attach the dataset to the notebook.
3. Run all cells.

The notebook auto-detects whether it is running on Kaggle (checks for `/kaggle/input/`) and adjusts data paths accordingly.

**Validation:** The final cell of the notebook runs 21 explicit numerical checks against the frozen benchmark report. All 21 must show `PASS` for a valid reproduction.

---

## Data License and Attribution

The JSONL result files in this package include `reference_transcript` fields containing verbatim text from two publicly released speech corpora. Both are licensed under **Creative Commons Attribution 4.0 International (CC BY 4.0)**, which permits redistribution for any purpose with attribution. Reference transcripts are used verbatim and unmodified.

### ISSAI Uzbek Speech Corpus (USC)

| Field | Detail |
|---|---|
| Corpus | ISSAI USC v1 |
| Dataset | `murodbek/uzbek-speech-corpus` (HuggingFace, split: test) |
| Paper | arXiv:2107.14419 |
| License | **CC BY 4.0** |
| Attribution | Institute of Smart Systems and Artificial Intelligence (ISSAI), Nazarbayev University |

### ISSAI Kazakh Speech Corpus (KSC)

| Field | Detail |
|---|---|
| Corpus | ISSAI KSC v1.1 (335RS) |
| Dataset | OpenSLR SLR102 — openslr.org/102 |
| Paper | Khassanov et al., EACL 2021 |
| License | **CC BY 4.0** (confirmed in EACL 2021 paper text and ISSAI website; the HuggingFace card for `issai/kazakh_speech_corpus` erroneously states MIT — the paper and ISSAI website are authoritative) |
| Attribution | Institute of Smart Systems and Artificial Intelligence (ISSAI), Nazarbayev University |

**License text:** https://creativecommons.org/licenses/by/4.0/

---

## Repository

Source repository (not required for reproduction): benchmark runners, manifest preparation scripts, and methodology documentation are included in the source repo. This publication package contains only the files required to reproduce the analysis.

**Frozen data files included:**
- `data/phase2_trackb_results.jsonl` — Phase 2 benchmark results (2,400 records)
- `data/phase3a_trackb_results.jsonl` — Phase 3A benchmark results (400 successful + 68 historical errors)

These files are read-only research artifacts. Do not modify them.
