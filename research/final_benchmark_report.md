# Central Asian STT Benchmark — Final Synthesis Report

**Project:** Central Asian AI Voice Benchmark
**Languages:** Uzbek (USC) · Kazakh (ISSAI KSC)
**Pipeline stage:** Speech-to-Text (Track B — frozen corpora)
**Phases covered:** Phase 1 · Phase 2 · Phase 3A
**Report date:** 2026-08-25
**Status:** FROZEN — all benchmark runs complete; no further API calls planned for this report

---

## 1. Executive Summary

This report synthesises three phases of speech-to-text benchmarking for Uzbek and Kazakh, covering five model configurations across two corpora. The central question throughout was whether explicitly supplying a language hint (HINT condition) improves transcription accuracy relative to automatic language detection (AUTO condition), and — in Phase 3A — whether a simple detection-mismatch routing rule can match the performance of always supplying the hint.

**Key findings:**

- ElevenLabs Scribe v2 is the strongest performer evaluated, achieving mean WER of 0.166 (AUTO) and 0.153 (HINT) on the Phase 3A held-out evaluation set.
- Kazakh is reliably detected by ElevenLabs Scribe v2 in AUTO mode (99% accuracy); language hints provide minimal benefit.
- Uzbek is unreliably detected in AUTO mode (27% accuracy); HINT directionally improves WER by −8.4% relative, but the improvement is not statistically significant at this sample size (SECONDARY: AUTO vs HINT, Uzbek, p=0.103).
- The pre-specified R1 routing rule (route to HINT when AUTO misdetects the language) does not outperform always-HINT on the Phase 3A evaluation set. The PRIMARY hypothesis test yields mean(wer\_routed − wer\_hint) = +0.0005 overall (p=0.820). The primary success criterion is not met.
- Always-HINT is the simplest condition supported by this benchmark. R1 routing did not demonstrate a statistically significant advantage over always-HINT.
- Phase 3B (Azure Speech Fast Transcription) was deferred and is not covered in this report.

**Cumulative spend:** Phase 1 $2.17 + Phase 2 $6.80 + Phase 3A $0.15 = **$9.12 total**.

---

## 2. Research Question

The benchmark addresses two questions for Uzbek and Kazakh:

1. **HINT effect:** Does supplying an explicit language hint improve STT word error rate relative to automatic language detection?
2. **Routing effectiveness (Phase 3A primary hypothesis):** Does a detection-mismatch routing rule — using HINT when the model misdetects the language, AUTO otherwise — outperform always using HINT?

These questions are answered independently for each language and in aggregate. No product recommendation follows from any finding; the benchmark establishes empirical baselines.

---

## 3. Benchmark Design

### Corpus

**Track B — frozen corpora (not FLEURS):**

| Corpus | Language | Source | License |
|---|---|---|---|
| ISSAI USC v1 (`murodbek/uzbek-speech-corpus`) | Uzbek | HuggingFace test split, 38 speakers | CC BY 4.0 |
| ISSAI KSC 335RS v1.1 | Kazakh | Local FLAC archive, 335 speakers | CC BY 4.0 |

Contamination risk is MEDIUM for all results — both corpora are publicly available and may appear in model training data. This limitation is inherent to the available Uzbek and Kazakh corpora and is disclosed throughout.

### Audio format

All audio: 16 kHz mono 16-bit PCM WAV, converted via ffmpeg. Duration range: 0.5 s – 30+ s.

### Experimental conditions

| Condition | Definition |
|---|---|
| AUTO | No language code supplied; model performs automatic detection |
| HINT | Explicit language code supplied for the correct language |

Language codes by provider:

| Provider | Uzbek HINT | Kazakh HINT |
|---|---|---|
| ElevenLabs Scribe v2 | `language_code="uz"` | `language_code="kk"` |
| Google Cloud STT Chirp 2 | `language_codes=["uz-UZ"]` | `language_codes=["kk-KZ"]` |
| GPT-4o-transcribe / gpt-4o-mini-transcribe | `prompt="Uzbek"` / `prompt="Kazakh"` | same |
| Whisper-1 | `prompt="Uzbek"` (ISO `language` rejected) | `prompt="Kazakh"` |

### Normalisation pipeline (identical across all phases)

Text is normalised before WER/CER computation:
1. NFC Unicode normalisation
2. Casefold
3. Apostrophe unification: `'`, `'`, `ʼ`, `` ` `` → `'`
4. Non-word, non-whitespace, non-apostrophe characters → space
5. Whitespace collapse and strip

WER and CER computed with `jiwer.wer()` and `jiwer.cer()` on the normalised pair.

---

## 4. Dataset and Evaluation Split

### Phase 2 corpus (frozen, shared across all Phase 2 providers)

| Language | Utterances | Total audio | Mean duration | Speakers |
|---|---|---|---|---|
| Uzbek | 300 | 21.8 min | 4.4 s | 38 |
| Kazakh | 300 | 37.2 min | 7.4 s | Multiple |
| **Total** | **600** | **59.0 min** | | |

Manifest SHA-256: `d01408af2e04d048a44600138ac878f97b2a2372f62b9a42f2f7d0b161f34924`

### Phase 3A corpus (held-out, disjoint from Phase 2)

| Split | Uzbek | Kazakh | Total |
|---|---|---|---|
| Pilot (`is_pilot=true`) | 30 | 10 | 40 |
| Evaluation (`is_pilot=false`) | 70 | 90 | 160 |
| **Total** | **100** | **100** | **200** |

Manifest SHA-256: `4e2ab89f7c30afebbb0fe756cc5deab2c171a9fbeefd65879bff5afd4ff6eddc`

**Note on evaluation split:** The execution plan anticipated 60 Uzbek + 100 Kazakh in evaluation, based on a hypothetical equal pilot split. The actual pilot contained 30 Uzbek + 10 Kazakh utterances (determined by the approved strata: uz\_short=15, uz\_medium=10, uz\_control=5, kk\_short=5, kk\_medium=5), resulting in 70 Uzbek + 90 Kazakh in evaluation. All analyses use the actual counts.

**Zero-overlap assertion (verified):** No Phase 3A utterance ID appears in the Phase 2 manifest.

---

## 5. Experimental Conditions

### Phase 1

Five configurations tested: gpt-4o-transcribe (AUTO, HINT), gpt-4o-mini-transcribe (AUTO, HINT), whisper-1 (AUTO, HINT). Whisper-1 Uzbek HINT was CLAIMED only — the ISO `language='uz'` parameter was rejected; `prompt='Uzbek'` was sent instead and its effectiveness is unconfirmed. Both whisper-1 Uzbek conditions therefore submit the same prompt and are effectively the same condition.

### Phase 2

Two providers, two conditions each: ElevenLabs Scribe v2 and Google Cloud STT Chirp 2.

### Phase 3A

ElevenLabs Scribe v2 only. Two conditions per utterance:
- AUTO: `client.speech_to_text.convert(file=audio, model_id="scribe_v2")`
- HINT: `client.speech_to_text.convert(file=audio, model_id="scribe_v2", language_code="uz" or "kk")`

Additionally, a post-hoc R1 routing simulation is computed analytically from the existing results — no additional API calls. R1 routing applies HINT for utterances where the AUTO call misdetected the language, AUTO otherwise.

---

## 6. Metrics

| Metric | Definition | Primary use |
|---|---|---|
| WER | `jiwer.wer(normalised_ref, normalised_hyp)` | Primary accuracy metric |
| CER | `jiwer.cer(normalised_ref, normalised_hyp)` | Secondary, character-level |
| Latency | Wall-clock ms from request send to response received | Engineering metric |
| Cost | Measured from API billing; see provider-specific formulas | Budget tracking |

**Cost formulas:**
- ElevenLabs Scribe v2: `(duration_s / 60.0) × $0.00367` (CONFIRMED: $0.22/hr)
- GCS Chirp 2: `(duration_s / 60.0) × $0.021` (CONFIRMED: $0.00035/s)
- GPT-4o-transcribe: audio tokens + output tokens (token-based billing)

---

## 7. Phase 2 Results

**Provider:** ElevenLabs Scribe v2 and Google Cloud STT Chirp 2
**Corpus:** 300 Uzbek + 300 Kazakh (Phase 2 frozen set)
**Records:** 2,400 successful (2 providers × 2 conditions × 600 utterances)
**Actual spend:** ElevenLabs $0.433 · GCS $6.363 · **Total $6.796**

### WER summary

| Provider | Language | AUTO WER | HINT WER | Δ (AUTO − HINT) |
|---|---|---|---|---|
| ElevenLabs Scribe v2 | Uzbek | 0.3416 | 0.2446 | −0.0970 |
| ElevenLabs Scribe v2 | Kazakh | 0.0534 | 0.0510 | −0.0024 |
| GCS Chirp 2 | Uzbek | 0.4227 | 0.2602 | −0.1625 |
| GCS Chirp 2 | Kazakh | 0.2666 | 0.2112 | −0.0554 |

See `plot_wer_by_model.png` and `plot_auto_vs_hint.png` for visual summaries.

**Findings:**

- ElevenLabs Scribe v2 outperforms GCS Chirp 2 across all four cells.
- For Uzbek, both providers show a large WER reduction when HINT is supplied. The GCS reduction (0.163 absolute) is larger in magnitude, but both start from a higher baseline.
- For Kazakh, ElevenLabs AUTO is already strong (WER 0.053); GCS Chirp 2 AUTO is weaker (0.267) and benefits substantially from the hint.
- HINT is consistently at least as good as AUTO in every cell; no provider/language combination shows HINT performing worse.

### Latency

| Provider | Mean (ms) | P50 (ms) | P95 (ms) |
|---|---|---|---|
| ElevenLabs Scribe v2 | 899 | 818 | 1,512 |
| GCS Chirp 2 | 2,364 | 2,228 | 3,994 |

ElevenLabs Scribe v2 is substantially faster (2.6× lower mean latency).

---

## 8. Phase 3A Results

**Provider:** ElevenLabs Scribe v2 only
**Corpus:** 200 held-out utterances (100 Uzbek + 100 Kazakh, disjoint from Phase 2)
**Benchmark version:** `phase3a_trackb_v1`
**Frozen commit:** `b8b364c`
**Records:** 400 successful + 68 historical error records (all historical; all 46 errored tuples later completed)
**Actual spend:** $0.14973

### Dataset verification (computed from frozen JSONL)

| Check | Expected | Verified |
|---|---|---|
| Total records | 468 | 468 |
| Successful records | 400 | 400 |
| Historical error records | 68 | 68 |
| Duplicate successful tuples | 0 | 0 |
| Pilot records (`is_pilot=true`) | 80 | 80 |
| Evaluation records (`is_pilot=false`) | 320 | 320 |
| Eval AUTO records | 160 | 160 |
| Eval HINT records | 160 | 160 |
| Uzbek eval utterances | 70 | 70 |
| Kazakh eval utterances | 90 | 90 |
| Actual spend | $0.14973 | $0.14973 |

### Phase 3A evaluation WER and CER

All figures below use the 160-utterance evaluation set (is\_pilot=false) unless stated.

| Condition | n | WER mean | WER median | CER mean | CER median |
|---|---|---|---|---|---|
| AUTO | 160 | 0.1664 | 0.0625 | 0.0731 | 0.0031 |
| HINT | 160 | 0.1534 | 0.0000 | 0.0632 | 0.0000 |

**Pairwise AUTO − HINT (n=160 paired utterances):**
- Mean WER difference: +0.0130 (positive = HINT better)
- HINT better: 19 utterances (12%); AUTO better: 11 (7%); Tied: 130 (81%)

See `plot_wer_by_language.png` and `plot_wer_vs_cer.png` for language-level and WER/CER comparisons.

### Phase 3A vs Phase 2 (ElevenLabs, observational)

These sets use different utterances; the comparison is observational only and not controlled for utterance-level difficulty.

| Language | Condition | Phase 2 WER (n=300) | Phase 3A eval WER (n=70/90) | Delta |
|---|---|---|---|---|
| Uzbek | AUTO | 0.3416 | 0.2906 | −0.051 |
| Uzbek | HINT | 0.2446 | 0.2662 | +0.022 |
| Kazakh | AUTO | 0.0534 | 0.0699 | +0.017 |
| Kazakh | HINT | 0.0510 | 0.0657 | +0.015 |

Phase 3A Uzbek AUTO is lower than Phase 2 (0.291 vs 0.342). This is likely a corpus effect: 22 of 38 USC speakers were fully exhausted by Phase 2; the remaining 16 speakers contributing to Phase 3A may skew toward lower-difficulty utterances.

---

## 9. PRIMARY Hypothesis Test: R1 Routed WER vs HINT WER

**This is the pre-specified primary test (Phase 3A execution plan, Section H, Steps 5–7).**

**R1 routing rule:** For each utterance, use HINT if `provider_detected_language` ≠ expected ISO-639-3 code for the utterance language (`uzb` for Uzbek, `kaz` for Kazakh); use AUTO otherwise. Null or missing `provider_detected_language` is treated as a mismatch (route to HINT).

**Primary test formulation:**
- Define d[i] = wer\_routed[i] − wer\_hint[i] for each evaluation utterance i
- H₀: mean(d) ≥ 0; H₁: mean(d) < 0 (routing outperforms always-HINT)
- Test: Wilcoxon signed-rank, one-tailed (`alternative='less'`), large-sample normal approximation with average-rank tie handling

**Primary success criterion (both required simultaneously):**
1. mean(d) ≤ −0.030
2. Wilcoxon p < 0.05

### Results (verified from frozen JSONL)

| Population | mean(wer\_routed) | mean(wer\_hint) | mean(d) | W⁺ | W⁻ | z | PRIMARY p |
|---|---|---|---|---|---|---|---|
| Overall (n=160) | 0.1539 | 0.1534 | **+0.0005** | 106.5 | 64.5 | 0.915 | **0.820** |
| Uzbek (n=70) | 0.2620 | 0.2662 | **−0.0043** | 6.0 | 4.0 | 0.365 | **0.642** |
| Kazakh (n=90) | 0.0699 | 0.0657 | **+0.0042** | 63.5 | 41.5 | 0.691 | **0.755** |

Nonzero pairs: overall n=18; Uzbek n=4; Kazakh n=14.

**The primary success criterion is not met.** Neither condition (mean(d) ≤ −0.030 nor p < 0.05) is satisfied for any population. The overall mean(d) = +0.0005 indicates that R1 routing produces results that are essentially equivalent to always using HINT, with no detectable advantage.

For Uzbek, mean(d) = −0.0043 is directionally favourable but falls far short of the −0.030 threshold and has p=0.642. Only 4 utterances (out of 70) show a nonzero difference between routed and HINT — indicating that routing selects HINT for most Uzbek utterances anyway, converging the two conditions.

---

## 10. SECONDARY Analysis: AUTO vs HINT

**These are secondary analyses only.** They do not address the primary routing hypothesis. The p-values below are SECONDARY and cannot be used to assess whether routing is beneficial.

**Test:** Wilcoxon signed-rank, one-tailed, H₁: AUTO WER > HINT WER.

| Population | AUTO WER mean | HINT WER mean | mean(AUTO−HINT) | W⁺ | W⁻ | z | SECONDARY p |
|---|---|---|---|---|---|---|---|
| Overall (n=160) | 0.1664 | 0.1534 | +0.0130 | 302.5 | 162.5 | 1.440 | **0.075** |
| Uzbek (n=70) | 0.2906 | 0.2662 | +0.0243 | 92.5 | 43.5 | 1.268 | **0.103** |
| Kazakh (n=90) | 0.0699 | 0.0657 | +0.0042 | 63.5 | 41.5 | 0.691 | **0.245** |

Nonzero pairs: overall n=30; Uzbek n=16; Kazakh n=14.

No test reaches p < 0.05. Bootstrap 95% CIs on mean(AUTO−HINT): overall [−0.008, 0.034]; Uzbek [−0.019, 0.066]; Kazakh [−0.010, 0.019]. All confidence intervals include zero.

**Interpretation:**
- HINT directionally improves WER relative to AUTO for Uzbek. The difference is not statistically significant at α=0.05 (SECONDARY: AUTO vs HINT, Uzbek, p=0.103).
- For Kazakh, AUTO and HINT are nearly equivalent. The AUTO detection accuracy is 99%, so supplying the hint provides no practical benefit (SECONDARY: AUTO vs HINT, Kazakh, p=0.245).
- The overall SECONDARY p=0.075 (AUTO vs HINT, overall) is driven primarily by the Uzbek component; the aggregate is not significant.

---

## 11. Uzbek Findings

### WER and CER (Phase 3A evaluation, n=70 utterances)

| Condition | WER mean | WER median | CER mean | CER median |
|---|---|---|---|---|
| AUTO | 0.2906 | 0.1429 | 0.1392 | 0.0244 |
| HINT | 0.2662 | 0.1429 | 0.1190 | 0.0169 |

HINT directionally improves Uzbek WER (−8.4% relative). The improvement is not statistically significant (SECONDARY: AUTO vs HINT, Uzbek, p=0.103; bootstrap 95% CI [−0.019, 0.066] includes zero).

### Language detection (AUTO condition, n=70)

| Outcome | Count | Fraction |
|---|---|---|
| Correct (`uzb`) | 19 | 27% |
| Misdetected | 51 | 73% |

Top misdetected languages: Turkish (`tur`) 18, English (`eng`) 12, Russian (`rus`) 3, Finnish (`fin`) 2, Estonian (`est`) 2, others 14.

Uzbek is phonologically close to Turkish, explaining the dominant misdetection category. Cyrillic-script detections (Russian, Tatar, Kyrgyz, Bashkir) produce wrong-script output and WER ≥ 1.0.

WER by detection outcome (AUTO condition):
- Correctly detected (`uzb`): WER mean 0.168
- Misdetected: WER mean 0.336 (+100% relative vs correctly detected)

### WER by duration tier

| Tier | n | AUTO WER mean | HINT WER mean |
|---|---|---|---|
| Short (<5 s) | 50 | 0.3347 | 0.3099 |
| Medium (5–10 s) | 18 | 0.1884 | 0.1626 |
| Long (>10 s) | 2 | — (n<3) | — (n<3) |

Shorter utterances have higher WER in both conditions, consistent with less phonological context being available for language identification.

### R1 routing (Uzbek)

- Routing rate: 51/70 = 73%
- Routed WER mean: 0.2620
- AUTO WER mean: 0.2906 (−0.029 vs routed, secondary observation)
- HINT WER mean: 0.2662 (−0.004 vs routed)

R1 routing reduces Uzbek WER relative to pure AUTO (by replacing misdetected AUTO calls with HINT for 73% of utterances). However, the routed result is approximately equivalent to always using HINT. The PRIMARY test confirms routing provides no detectable incremental benefit over always-HINT (PRIMARY: routed vs HINT, Uzbek, mean(d)=−0.0043, p=0.642).

---

## 12. Kazakh Findings

### WER and CER (Phase 3A evaluation, n=90 utterances)

| Condition | WER mean | WER median | CER mean | CER median |
|---|---|---|---|---|
| AUTO | 0.0699 | 0.0000 | 0.0216 | 0.0000 |
| HINT | 0.0657 | 0.0000 | 0.0198 | 0.0000 |

AUTO performs strongly for Kazakh because language detection is highly accurate. HINT provides no meaningful benefit (SECONDARY: AUTO vs HINT, Kazakh, p=0.245; bootstrap 95% CI [−0.010, 0.019]).

### Language detection (AUTO condition, n=90)

| Outcome | Count | Fraction |
|---|---|---|
| Correct (`kaz`) | 89 | 99% |
| Misdetected | 1 | 1% |

The single misdetection was Ukrainian (`ukr`), WER 0.167. Kazakh is reliably detected by ElevenLabs Scribe v2 in AUTO mode.

### R1 routing (Kazakh)

- Routing rate: 1/90 = 1%
- Routed WER mean: 0.0699 (identical to AUTO; only one utterance was routed)
- The near-zero routing rate means routing is operationally equivalent to AUTO for Kazakh.

### WER by duration tier

| Tier | n | AUTO WER mean | HINT WER mean |
|---|---|---|---|
| Short (<5 s) | 14 | 0.0976 | 0.0706 |
| Medium (5–10 s) | 52 | 0.0657 | 0.0694 |
| Long (>10 s) | 24 | 0.0626 | 0.0549 |

WER is uniformly low across all Kazakh duration tiers. The apparent HINT advantage for short utterances (n=14) is insufficient for inference.

---

## 13. Error Analysis

### WER ≥ 1.0 records (Phase 3A evaluation)

**Count: 15 records, all Uzbek.** No Kazakh record reached WER ≥ 1.0 in the evaluation set.

Summary of failure types:

| UID | Cond | WER | AUTO detected | Failure type |
|---|---|---|---|---|
| 265773029\_2\_83580\_2 | auto | 1.333 | rus | Cyrillic output |
| 265773029\_2\_83580\_2 | hint | 1.333 | uzb | Cyrillic output despite HINT |
| 972644779\_2\_87520\_1 | hint | 1.200 | uzb | Cyrillic output despite HINT |
| 382004286\_2\_20612\_1 | auto | 1.200 | tur | Word insertion via tokenisation |
| 1571110404\_2\_19314\_1 | auto | 1.000 | rus | Cyrillic output |
| 1571110404\_2\_19314\_1 | hint | 1.000 | uzb | Cyrillic output despite HINT |
| 1571110404\_2\_36820\_1 | auto | 1.000 | bak | Bashkir Cyrillic output |
| 1571110404\_2\_36820\_1 | hint | 1.000 | uzb | Cyrillic output despite HINT |
| 265773029\_2\_75008\_2 | auto | 1.000 | ara | Arabic script output |
| 972644779\_2\_87507\_3 | auto | 1.000 | kir | Mixed Chinese + Cyrillic (see below) |
| 972644779\_2\_87520\_1 | auto | 1.000 | rus | Cyrillic output |
| 467174862\_2\_34142\_1 | auto | 1.000 | tat | Tatar Cyrillic output |
| 467174862\_2\_34142\_1 | hint | 1.000 | uzb | Cyrillic output despite HINT |
| 382004286\_2\_20598\_1 | hint | 1.000 | uzb | Cyrillic output despite HINT |
| 382004286\_2\_20612\_1 | hint | 1.000 | uzb | Word-level tokenisation differences |

**HINT does not fully resolve wrong-script output.** For speakers 1571110404, 265773029, 467174862, and 382004286, the HINT call correctly changes the detection tag to `uzb` but the decoding path still produces Cyrillic-script Uzbek. Both Latin and Cyrillic scripts are used in real Uzbek text; the model's decoding does not deterministically select Latin when `uz` is specified. These records are valid data points.

### Notable anomaly: UID 972644779\_2\_87507\_3 — Chinese hallucination

- AUTO (detected: `kir`): `电话铃声 товар биржиси норозилик акцияси ўтказиш бойича талабнома киритилган` — mixed Chinese characters and Cyrillic text, WER 1.000
- HINT (detected: `uzb`): `air tovar belgisi ro'yxatdan o'tkazish bo'yicha talablar ko'rilgan` — partial recovery, WER 0.444

The Chinese characters in the AUTO output are a model hallucination unrelated to the audio content. HINT largely recovers correct transcription. Valid data point; no exclusion warranted.

### Notable anomaly: UID 1131474547\_2\_30677\_1 — Persistent Kurdish script

- AUTO (detected: `ckb`): Kurdish Central script output, WER 1.5
- HINT (detected: `uzb`): Identical Kurdish Central script output, WER 1.5

HINT correctly changes the detection label to `uzb` but produces identical output. The audio (`aka ukaligimiz bor edi`) may be phonetically indistinguishable from Kurdish to the model at the acoustic level. Both conditions fail equally.

### Apostrophe-stripping confound (Uzbek HINT)

Uzbek Latin script uses the apostrophe as a phonological marker (e.g., `o'zbek`, `bo'lib`). In 7 of 70 Uzbek HINT evaluation records, the HINT transcription strips apostrophes from positions where the reference retains them.

| Metric | Value |
|---|---|
| Uzbek HINT records with apostrophe in reference | 45 |
| Records where HINT strips apostrophes | 7 (16% of apostrophe-bearing) |
| WER mean (stripped) | 0.819 |
| WER mean (preserved) | 0.129 |
| AUTO WER mean for same 7 UIDs | 0.601 |

These 7 records show higher WER in HINT than in AUTO (0.819 vs 0.601), inverting the usual direction for those specific utterances. Apostrophe omission changes word identity in Uzbek and is not a normalisation artefact. The official WER is not adjusted — the frozen methodology applies uniformly. This effect modestly suppresses the measured Uzbek HINT advantage and contributes to the non-significance of the Uzbek secondary test.

---

## 14. Routing Analysis

### R1 routing rule

R1 applies HINT when ElevenLabs Scribe v2 AUTO reports a language code other than the expected ISO-639-3 code for the utterance language (`uzb` for Uzbek, `kk`/`kaz` for Kazakh). Null or empty `provider_detected_language` is treated as a mismatch.

### Routing rates (Phase 3A evaluation)

| Language | Routed (HINT) | Not routed (AUTO) | Total | Routing rate |
|---|---|---|---|---|
| Uzbek | 51 | 19 | 70 | **73%** |
| Kazakh | 1 | 89 | 90 | **1%** |
| Overall | 52 | 108 | 160 | **32%** |

### Routing outcome table

| Population | mean(wer\_routed) | mean(wer\_auto) | mean(wer\_hint) | Δ routed−AUTO | Δ routed−HINT |
|---|---|---|---|---|---|
| Overall | 0.1539 | 0.1664 | 0.1534 | −0.0125 | **+0.0005** |
| Uzbek | 0.2620 | 0.2906 | 0.2662 | −0.0286 | **−0.0043** |
| Kazakh | 0.0699 | 0.0699 | 0.0657 | 0.0000 | **+0.0042** |

The improvement in routed WER relative to pure AUTO (Δ = −0.0286 for Uzbek, −0.0125 overall) is a **secondary observation, not a primary criterion**. The same result is achieved by simply always using HINT, which is simpler and equally effective.

Routing converges toward HINT performance because: (1) 73% of Uzbek utterances are routed to HINT anyway; (2) the 27% of correctly detected utterances where routing keeps AUTO performs similarly to HINT for those utterances. For Kazakh, routing is almost never triggered, so routed ≈ AUTO ≈ HINT.

---

## 15. Latency Analysis

### Phase 3A evaluation (ElevenLabs Scribe v2, n=320 records)

| Segment | Mean (ms) | P50 (ms) | P95 (ms) |
|---|---|---|---|
| All eval (n=320) | 1,049 | 938 | 1,922 |
| AUTO condition | 1,070 | 953 | 1,922 |
| HINT condition | 1,027 | 922 | 1,953 |
| Uzbek (both conds) | 834 | 797 | 1,219 |
| Kazakh (both conds) | 1,216 | 1,047 | 2,250 |

HINT latency is marginally lower than AUTO (mean 1,027 vs 1,070 ms); the difference is small and does not affect practical use. Uzbek utterances are shorter on average (mean 4.5 s vs 8.6 s for Kazakh), explaining the lower Uzbek latency. The P95 of 1,922 ms covers the vast majority of calls.

See `plot_latency.png` for the latency distribution.

### Phase 2 latency comparison

| Provider | Mean (ms) | P50 (ms) | P95 (ms) |
|---|---|---|---|
| ElevenLabs Scribe v2 (Phase 2) | 899 | 818 | 1,512 |
| GCS Chirp 2 (Phase 2) | 2,364 | 2,228 | 3,994 |
| ElevenLabs Scribe v2 (Phase 3A eval) | 1,049 | 938 | 1,922 |

Phase 3A ElevenLabs latency is modestly higher than Phase 2 (mean +150 ms). This may reflect longer Kazakh utterances in the Phase 3A pool (the KSC held-out set has more medium/long utterances) rather than a provider change. GCS Chirp 2 latency is 2.6× higher than ElevenLabs.

---

## 16. Statistical Interpretation

### Wilcoxon signed-rank test details

All Wilcoxon tests use paired observations on the 160-utterance evaluation set. Implementation: manual Python with average-rank tie handling and large-sample normal approximation. Note that 81% of paired observations are exact ties (WER identical in both conditions), which reduces the effective sample size.

Formulas used:
```
E[W⁺] = n(n+1)/4
Var[W⁺] = n(n+1)(2n+1)/24 − Σ(tⱼ³ − tⱼ)/48
z = (W⁺ − E[W⁺]) / √Var[W⁺]
```
where tⱼ is the size of each tie group among nonzero absolute differences. For `alt='less'`: p = Φ(z); for `alt='greater'`: p = 1 − Φ(z).

### Bootstrap CIs

5,000 resamples with replacement on the 160-length paired difference vector. 95% CI: [2.5th, 97.5th] percentile.

| Test | mean(d) | 95% CI |
|---|---|---|
| PRIMARY overall (routed − HINT) | +0.0005 | [−0.0151, +0.0132] |
| SECONDARY overall (AUTO − HINT) | +0.0130 | [−0.008, +0.034] |
| SECONDARY Uzbek (AUTO − HINT) | +0.0243 | [−0.019, +0.066] |
| SECONDARY Kazakh (AUTO − HINT) | +0.0042 | [−0.010, +0.019] |

All confidence intervals include zero. None of the comparisons yields a CI that excludes zero.

### Summary of all hypothesis tests

| # | Label | Test | Statistic | p | α=0.05 |
|---|---|---|---|---|---|
| 1 | PRIMARY: routed vs HINT (overall) | Wilcoxon `less` | z=0.915 | 0.820 | NOT MET |
| 2 | PRIMARY: routed vs HINT (Uzbek) | Wilcoxon `less` | z=0.365 | 0.642 | NOT MET |
| 3 | PRIMARY: routed vs HINT (Kazakh) | Wilcoxon `less` | z=0.691 | 0.755 | NOT MET |
| 4 | SECONDARY: AUTO vs HINT (overall) | Wilcoxon `greater` | z=1.440 | 0.075 | NOT MET |
| 5 | SECONDARY: AUTO vs HINT (Uzbek) | Wilcoxon `greater` | z=1.268 | 0.103 | NOT MET |
| 6 | SECONDARY: AUTO vs HINT (Kazakh) | Wilcoxon `greater` | z=0.691 | 0.245 | NOT MET |

No test reaches p < 0.05. All p-values are one-tailed on n=160 (or subsets). The 81% tie rate means the Wilcoxon p-values are approximate; they are consistent with bootstrap CIs throughout.

---

## 17. Production Implications

**This section describes what the benchmark supports and does not support. No production deployment recommendation is implied.**

**What this benchmark supports:**

1. Always-HINT is the simplest condition supported by this benchmark. R1 routing did not demonstrate a statistically significant advantage over always-HINT.

2. For Kazakhs audio, AUTO and HINT are operationally equivalent. ElevenLabs Scribe v2 correctly identifies Kazakh in 99% of cases without any hint.

3. For Uzbek audio, HINT directionally improves WER relative to AUTO, but the difference is not statistically significant at this sample size. The improvement would need to be confirmed in a larger study before drawing conclusions about its practical magnitude.

4. Both ElevenLabs Scribe v2 conditions substantially outperform GCS Chirp 2 for Kazakh, and show lower WER for Uzbek HINT as well.

5. Apostrophe handling in Uzbek HINT output is inconsistent — approximately 10% of apostrophe-bearing records show apostrophe stripping that inflates WER. Any downstream use of HINT transcripts for Uzbek should account for this.

**What this benchmark does not support:**

- Claims that R1 routing is beneficial for Uzbek in a deployment context.
- Claims about any provider's quality beyond these specific audio conditions and corpus.
- Generalization to audio characteristics or speaker populations not represented in the USC or KSC corpora.

---

## 18. Limitations

**1. Uzbek duration-stratum deviation.**
The evaluation set has 50 short / 18 medium / 2 long Uzbek utterances (target was approximately 46/44/10). The 22 fully exhausted Phase 2 speakers could not contribute to Phase 3A, skewing the remaining pool toward shorter utterances from the 16 active speakers. Long-Uzbek analysis (n=2) has no statistical power and is excluded.

**2. Apostrophe-stripping confound.**
In 7 Uzbek HINT records (10% of apostrophe-bearing records), HINT transcription omits apostrophes, inflating WER and suppressing the HINT advantage. Official WER is not adjusted; this finding is diagnostic for future work.

**3. Historical rate-limit errors.**
The 68 historical error records in the Phase 3A JSONL are from ElevenLabs API quota exhaustion during the run. All 46 originally failed tuples were subsequently completed. Error records have cost\_usd=0 and are excluded from all analyses.

**4. Speaker overlap with Phase 2.**
Phase 3A Uzbek uses different utterances but the same 16 speakers as Phase 2. Speaker-level effects may be correlated across phases. Utterance-level independence is maintained; speaker-level independence is not.

**5. Contamination risk: MEDIUM.**
Both ISSAI corpora (CC BY 4.0) are publicly available and may be present in model training data. This is an inherent limitation of available Uzbek and Kazakh corpora; independent evaluation corpora are not available at this time.

**6. Phase 3A evaluation split deviation.**
The execution plan anticipated 60 Uzbek + 100 Kazakh in evaluation. The actual split is 70 Uzbek + 90 Kazakh (driven by the approved pilot strata). All analyses use the actual counts.

**7. Single provider in Phase 3A.**
Phase 3A tests ElevenLabs Scribe v2 only. Results do not generalize to Azure Speech Fast Transcription or other providers without additional benchmarking.

**8. Small nonzero-pair counts in PRIMARY test.**
The PRIMARY test has only 18 nonzero paired differences overall (30 for the SECONDARY AUTO vs HINT test overall; 16 Uzbek, 14 Kazakh). With 81% tied pairs in the SECONDARY test (130/160), Wilcoxon p-values are approximate. The substantive conclusion (routing ≈ HINT) is robust — the mean differences are small and the CIs confirm no economically meaningful effect.

**9. Phase 1 scope limitation.**
Phase 1 used a smaller, different corpus and different billing structure (token-based). Phase 1 results are not directly comparable to Phase 2/3A WERs.

---

## 19. Reproducibility

### Version identifiers

| Component | Version / Hash |
|---|---|
| Phase 2 benchmark version | `phase2_trackb_v1` |
| Phase 3A benchmark version | `phase3a_trackb_v1` |
| Phase 3A results commit | `b8b364c` |
| Phase 3A analysis commit | `82a69c8` |
| Phase 3A manifest SHA-256 | `4e2ab89f7c30afebbb0fe756cc5deab2c171a9fbeefd65879bff5afd4ff6eddc` |
| Phase 2 manifest SHA-256 | `d01408af2e04d048a44600138ac878f97b2a2372f62b9a42f2f7d0b161f34924` |

### Key files

| File | Description |
|---|---|
| `results/phase3a/phase3a_trackb_results.jsonl` | 468 records; all Phase 3A API call outputs |
| `results/phase3a/run_phase3a_trackb.py` | Phase 3A execution script |
| `results/phase2_full/phase2_trackb_results.jsonl` | 2,400 Phase 2 records |
| `results/phase2_full/run_phase2_trackb.py` | Phase 2 execution script |
| `research/phase3a_audio_manifest.csv` | 200-row Phase 3A utterance manifest |
| `research/phase3a_execution_plan.md` | Pre-specified Phase 3A analysis plan (commit `21df2af`) |
| `research/phase3a_deep_analysis.md` | Detailed Phase 3A analysis (commit `82a69c8`) |

### Statistical implementation note

Wilcoxon tests were implemented manually in Python (no scipy dependency) using average-rank tie handling and large-sample normal approximation. The variance formula is:

```
Var[W⁺] = n(n+1)(2n+1)/24 − Σ(tⱼ³ − tⱼ)/48
```

Results were verified independently; computed p-values match the values in `research/phase3a_deep_analysis.md`.

### ElevenLabs Scribe v2 logging note

ElevenLabs logs requests and transcripts server-side by default (zero-retention mode is enterprise-only). All Phase 2 and Phase 3A audio and transcriptions should be assumed to have been logged by ElevenLabs. This does not affect the benchmark results but must be disclosed in any publication.

---

## 20. Final Conclusion

Across three phases of evaluation for Uzbek and Kazakh STT, ElevenLabs Scribe v2 achieves the lowest WER of any model tested. The key results from the pre-specified Phase 3A evaluation are:

**Kazakh:** ElevenLabs Scribe v2 detects Kazakh reliably in AUTO mode (99% accuracy). The HINT condition provides no statistically significant improvement. AUTO and HINT are operationally equivalent for Kazakh on this benchmark.

**Uzbek:** ElevenLabs Scribe v2 misdetects Uzbek in AUTO mode 73% of the time, primarily identifying it as Turkish, English, or a Cyrillic-script language. HINT directionally improves WER relative to AUTO, but the difference is not statistically significant (SECONDARY: AUTO vs HINT, Uzbek, p=0.103). Approximately 10% of apostrophe-bearing Uzbek HINT records exhibit apostrophe stripping that inflates measured WER.

**R1 routing (PRIMARY hypothesis):** The pre-specified routing rule — using HINT when AUTO misdetects the language — does not outperform always-HINT (PRIMARY: routed vs HINT, overall, mean(d)=+0.0005, p=0.820). The primary success criterion (mean(d) ≤ −0.030 AND p < 0.05) is not met by a wide margin. Routing converges to HINT-equivalent performance because it routes 73% of Uzbek utterances to HINT regardless.

**Simplest supported recommendation:** Always-HINT is the simplest condition supported by this benchmark. R1 routing did not demonstrate a statistically significant advantage over always-HINT.

**Phase 3B (Azure Speech Fast Transcription):** Deferred. Phase 3B would require additional paid API usage (Azure Fast Transcription pricing and credentials were not confirmed at the time this report was frozen) and was outside the scope of the current frozen experiment. Phase 3B results are not included in this report and Phase 3B should not be presented as having failed.

---

## Appendix A: Phase 1 Reference Results

Phase 1 used a different corpus and billing structure. Results are included for completeness only and are not directly comparable to Phase 2/3A WERs.

| Model | Language | AUTO WER | HINT WER |
|---|---|---|---|
| gpt-4o-transcribe | Uzbek | 0.545 | 0.316 |
| gpt-4o-transcribe | Kazakh | 0.257 | 0.227 |
| gpt-4o-mini-transcribe | Uzbek | 0.755 | 0.492 |
| gpt-4o-mini-transcribe | Kazakh | 0.452 | 0.359 |
| whisper-1 | Uzbek | 1.141 | 1.150\* |
| whisper-1 | Kazakh | 0.532 | 0.495 |

\*Whisper-1 Uzbek HINT used `prompt='Uzbek'` only (ISO `language='uz'` rejected). Both Uzbek conditions are effectively the same.

Phase 1 records: 3,600 · Spend: $2.1703

---

## Appendix B: All WER Summary by Phase and Provider

| Phase | Provider | Language | Condition | WER mean | n |
|---|---|---|---|---|---|
| 1 | gpt-4o-transcribe | Uzbek | AUTO | 0.545 | 300 |
| 1 | gpt-4o-transcribe | Uzbek | HINT | 0.316 | 300 |
| 1 | gpt-4o-transcribe | Kazakh | AUTO | 0.257 | 300 |
| 1 | gpt-4o-transcribe | Kazakh | HINT | 0.227 | 300 |
| 1 | gpt-4o-mini-transcribe | Uzbek | AUTO | 0.755 | 300 |
| 1 | gpt-4o-mini-transcribe | Uzbek | HINT | 0.492 | 300 |
| 1 | gpt-4o-mini-transcribe | Kazakh | AUTO | 0.452 | 300 |
| 1 | gpt-4o-mini-transcribe | Kazakh | HINT | 0.359 | 300 |
| 1 | whisper-1 | Uzbek | AUTO | 1.141 | 300 |
| 1 | whisper-1 | Uzbek | HINT | 1.150 | 300 |
| 1 | whisper-1 | Kazakh | AUTO | 0.532 | 300 |
| 1 | whisper-1 | Kazakh | HINT | 0.495 | 300 |
| 2 | ElevenLabs Scribe v2 | Uzbek | AUTO | 0.3416 | 300 |
| 2 | ElevenLabs Scribe v2 | Uzbek | HINT | 0.2446 | 300 |
| 2 | ElevenLabs Scribe v2 | Kazakh | AUTO | 0.0534 | 300 |
| 2 | ElevenLabs Scribe v2 | Kazakh | HINT | 0.0510 | 300 |
| 2 | GCS Chirp 2 | Uzbek | AUTO | 0.4227 | 300 |
| 2 | GCS Chirp 2 | Uzbek | HINT | 0.2602 | 300 |
| 2 | GCS Chirp 2 | Kazakh | AUTO | 0.2666 | 300 |
| 2 | GCS Chirp 2 | Kazakh | HINT | 0.2112 | 300 |
| 3A | ElevenLabs Scribe v2 | Uzbek | AUTO | 0.2906 | 70 |
| 3A | ElevenLabs Scribe v2 | Uzbek | HINT | 0.2662 | 70 |
| 3A | ElevenLabs Scribe v2 | Kazakh | AUTO | 0.0699 | 90 |
| 3A | ElevenLabs Scribe v2 | Kazakh | HINT | 0.0657 | 90 |
| 3A | ElevenLabs Scribe v2 | Overall | AUTO | 0.1664 | 160 |
| 3A | ElevenLabs Scribe v2 | Overall | HINT | 0.1534 | 160 |

---

## Appendix C: Spend Summary

| Phase | Provider | Records | Spend |
|---|---|---|---|
| 1 | GPT-4o-transcribe + GPT-4o-mini + Whisper-1 | 3,600 | $2.1703 |
| 2 | ElevenLabs Scribe v2 | 1,200 | $0.4332 |
| 2 | GCS Chirp 2 | 1,200 | $6.3630 |
| 3A | ElevenLabs Scribe v2 | 400 | $0.1497 |
| **Total** | | **6,400** | **$9.116** |

Phase 2 GCS Chirp 2 accounts for 70% of total spend at $0.021/min vs ElevenLabs' $0.00367/min (5.7× more expensive per audio-minute).
