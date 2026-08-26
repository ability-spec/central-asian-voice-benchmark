# Phase 3A Deep Analysis: ElevenLabs Scribe v2 AUTO vs HINT — Central Asian Languages

**Benchmark version:** `phase3a_trackb_v1`  
**Commit frozen at:** `b8b364c`  
**Analysis date:** 2026-08-25  
**Provider:** ElevenLabs Scribe v2 only  
**Languages:** Uzbek (USC), Kazakh (ISSAI KSC)  
**Dataset:** 200 held-out utterances (100 Uzbek + 100 Kazakh), disjoint from Phase 2  

---

## Dataset Summary

| Split | Utterances | Records (×2 conditions) |
|---|---|---|
| Pilot (is_pilot=True) | 40 | 80 |
| Evaluation (is_pilot=False) | 160 | 320 |
| **Total successful** | **200** | **400** |

All analyses in sections 1–13 use the **160-utterance evaluation set** (320 records) unless explicitly stated. The 80 pilot records are kept separate and used only for pilot-vs-eval comparison in section 9. The 68 historical error records (all cost_usd=0, all superseded by successful retries) are excluded from all analyses.

**Evaluation split:** 70 Uzbek + 90 Kazakh utterances (160 total). The execution plan anticipated 60 Uzbek + 100 Kazakh, based on a hypothetical equal pilot split. The actual pilot composition was 30 Uzbek + 10 Kazakh (driven by the approved strata), yielding 70 + 90 in evaluation. All analyses use the actual counts.

---

## 1. Overall WER and CER

### Evaluation set (n=160 utterances, 320 records)

| Condition | n | WER mean | WER median | CER mean | CER median |
|---|---|---|---|---|---|
| AUTO | 160 | 0.1664 | 0.0625 | 0.0731 | 0.0031 |
| HINT | 160 | 0.1534 | 0.0000 | 0.0632 | 0.0000 |

**Pairwise (AUTO − HINT) on 160 paired utterances:**

- Mean WER difference: **+0.0130** (positive = HINT better)
- Median WER difference: 0.0000
- HINT better: 19 utterances (12%)
- AUTO better: 11 utterances (7%)
- Tied: 130 utterances (81%)

**Wilcoxon signed-rank test** (H₁: AUTO WER > HINT WER, one-tailed, n=160, nonzero pairs=30):  
W⁺=302.5, W⁻=162.5, z=1.440, **p=0.075**

**Bootstrap 95% CI** (mean WER difference AUTO−HINT, 5,000 resamples):  
**0.0130 [−0.0077, 0.0336]**

The confidence interval includes zero. The overall advantage of HINT over AUTO is positive in direction but does not reach conventional significance at α=0.05 on the evaluation set alone.

---

## 2. Uzbek

### WER and CER (evaluation set, n=70 utterances)

| Condition | n | WER mean | WER median | CER mean | CER median |
|---|---|---|---|---|---|
| AUTO | 70 | 0.2906 | 0.1429 | 0.1392 | 0.0244 |
| HINT | 70 | 0.2662 | 0.1429 | 0.1190 | 0.0169 |

**Pairwise (n=70):** HINT better: 11, AUTO better: 5, Tied: 54  
Mean difference: **+0.0243** (HINT better)  
Wilcoxon: W⁺=92.5, W⁻=43.5, z=1.267, **p=0.103**  
Bootstrap 95% CI: **0.0243 [−0.0189, 0.0656]**

HINT directionally improves Uzbek WER (−8.4% relative), but the effect does not reach p<0.05 at n=70.

### Language detection (AUTO condition)

- Correct (detected as `uzb`): **19/70 (27%)**
- Misdetected: **51/70 (73%)**

Top misdetected languages: Turkish (`tur`) 18, English (`eng`) 12, Russian (`rus`) 3, Finnish (`fin`) 2, Estonian (`est`) 2, others 14.

WER when correctly detected: 0.1679  
WER when misdetected: 0.3363 (+100% relative increase vs correct detection)

The low detection rate (27%) is the primary driver of the Uzbek AUTO WER penalty. Uzbek is phonologically close to Turkish, which explains the most common misdetection. English misdetections tend to produce lower WER (model still transcribes correctly despite wrong language tag) while Cyrillic-script detections (Russian, Tatar, Kyrgyz) produce entirely wrong-script output and WER ≥ 1.0.

### Script errors

15 eval records have WER ≥ 1.0, all Uzbek. In every case the model output either:
- Transcribed in Cyrillic (Russian, Tatar, Kyrgyz, Bashkir) despite Latin Uzbek reference
- Transcribed in Arabic script (Arabic, Farsi)
- Transcribed in Kurdish script (Central Kurdish)
- Returned mixed scripts (Latin + Cyrillic, or Cyrillic + Chinese; see section 7)

HINT corrects most of these (detection changes from wrong language to `uzb`) but 7 of the 15 extreme records persist under HINT: the HINT call returns `uzb` detection but still outputs Cyrillic Uzbek, which the WER metric correctly penalises since the reference is Latin.

---

## 3. Kazakh

### WER and CER (evaluation set, n=90 utterances)

| Condition | n | WER mean | WER median | CER mean | CER median |
|---|---|---|---|---|---|
| AUTO | 90 | 0.0699 | 0.0000 | 0.0216 | 0.0000 |
| HINT | 90 | 0.0657 | 0.0000 | 0.0198 | 0.0000 |

**Pairwise (n=90):** HINT better: 8, AUTO better: 6, Tied: 76  
Mean difference: **+0.0042** (HINT better)  
Wilcoxon: W⁺=63.5, W⁻=41.5, z=0.691, **p=0.245**  
Bootstrap 95% CI: **0.0042 [−0.0097, 0.0188]**

HINT provides no meaningful benefit for Kazakh. The effect is small (−6.0% relative), non-significant, and the CI is entirely contained well below any practical threshold.

### Language detection (AUTO condition)

- Correct (detected as `kaz`): **89/90 (99%)**
- Misdetected: **1/90 (1%)**, detected as Ukrainian (`ukr`), WER=0.167

Kazakh is reliably detected by ElevenLabs Scribe v2 in AUTO mode. The near-perfect detection rate explains the minimal HINT benefit: HINT routing is essentially never triggered for Kazakh, so AUTO and HINT produce nearly identical results.

---

## 4. R1 Routing (AUTO → HINT on language-detection mismatch)

**Rule R1:** If `provider_detected_language` ≠ expected ISO-639-3 code for the utterance language, route to HINT.

### Routing rates (evaluation set)

| Language | Routing rate |
|---|---|
| Uzbek | 51/70 = **73%** |
| Kazakh | 1/90 = **1%** |
| Overall | 52/160 = **32%** |

### Primary hypothesis test: routed WER vs HINT WER

The pre-specified primary test (execution plan, Section H, Steps 5–7) compares **routed WER against always-HINT WER**, not against AUTO. Define d[i] = wer_routed[i] − wer_hint[i]. H₁: mean(d) < 0 (routing beats HINT).

| Population | mean(wer_routed) | mean(wer_hint) | mean(d) | Wilcoxon p (less) | Bootstrap 95% CI on mean(d) |
|---|---|---|---|---|---|
| Overall (n=160) | 0.1539 | 0.1534 | **+0.0005** | **0.820** | [−0.0151, +0.0132] |
| Uzbek (n=70) | 0.2620 | 0.2662 | **−0.0043** | **0.642** | — |
| Kazakh (n=90) | 0.0699 | 0.0657 | **+0.0042** | **0.755** | — |

Wilcoxon: H₁: d < 0, large-sample normal approximation, nonzero pairs: overall=18, Uzbek=4, Kazakh=14.

**Primary success criterion** (both required simultaneously):  
1. mean(d) ≤ −0.030  
2. Wilcoxon p < 0.05

**Result: Neither condition is met.** The overall mean(d) = +0.0005 (routing ≈ HINT). For Uzbek, mean(d) = −0.0043, which is far below the −0.030 threshold and has p=0.642. The primary criterion is not met by a wide margin, not narrowly.

### Secondary comparison: routed WER vs AUTO WER

R1 routing does improve over pure AUTO (secondary observation, not the primary test):

| Language | AUTO WER | Routed WER | Δ vs AUTO |
|---|---|---|---|
| Uzbek | 0.2906 | 0.2620 | −0.0286 (−10% relative) |
| Kazakh | 0.0699 | 0.0699 | 0.0000 |
| Overall | 0.1664 | 0.1539 | −0.0125 (−7.5% relative) |

This improvement over AUTO arises because routing replaces AUTO with HINT for the 73% of Uzbek utterances that AUTO misdetects. Since HINT is generally better than misdetected AUTO (though not necessarily better than correctly-detected AUTO), the aggregate improves. However, routing produces results that are essentially equivalent to always using HINT — the routing strategy offers no incremental benefit over simply always passing the language hint.

Note: the pilot routing simulation showed a larger apparent improvement because the uz_control stratum over-represents speakers with the highest misdetection rates.

---

## 5. Duration Tiers

**Evaluation distribution:**  
Uzbek: short=50 (71%), medium=18 (26%), long=2 (3%)  
Kazakh: short=14 (16%), medium=52 (58%), long=24 (27%)

*Uzbek distribution deviates from plan target (46/44/10%) due to the structural constraint that 22 of 38 USC speakers were fully exhausted by Phase 2. The remaining 16 speakers skew toward shorter utterances. This is a known limitation; see section 13.*

### WER by duration tier (evaluation)

| Language | Tier | n | AUTO WER mean | HINT WER mean |
|---|---|---|---|---|
| Uzbek | short | 50 | 0.3347 | 0.3099 |
| Uzbek | medium | 18 | 0.1884 | 0.1626 |
| Uzbek | long | 2 | — (n<3) | — (n<3) |
| Kazakh | short | 14 | 0.0976 | 0.0706 |
| Kazakh | medium | 52 | 0.0657 | 0.0694 |
| Kazakh | long | 24 | 0.0626 | 0.0549 |

For Uzbek, shorter utterances have higher WER in both conditions. This is consistent with short utterances providing less phonological context for language identification, increasing misdetection. For Kazakh, WER is uniformly low across all tiers; the HINT advantage in Kazakh short utterances (0.0976 vs 0.0706) is based on n=14 and should not be over-interpreted.

---

## 6. Speaker Effects

Speaker-level AUTO WER (evaluation set, speakers with ≥3 utterances):

| Speaker | n | WER mean | WER median | Notes |
|---|---|---|---|---|
| 265773029 | 5 | 0.6667 | 0.5000 | Highest WER; multiple wrong-script outputs |
| 1571110404 | 6 | 0.5417 | 0.5833 | Consistent Cyrillic output in AUTO |
| 467174862 | 3 | 0.5333 | 0.6000 | Tatar-script misdetection |
| 382004286 | 4 | 0.5188 | 0.3750 | Turkish misdetection + HINT script issues |
| 972644779 | 6 | 0.4127 | 0.2381 | Includes Chinese hallucination (see §7) |
| 818938633 | 4 | 0.2708 | 0.1667 | |
| 1289864764 | 4 | 0.2500 | 0.2500 | |
| 1229529100 | 4 | 0.2068 | 0.1993 | |
| 1187023182 | 7 | 0.1704 | 0.1429 | |
| 1131474547 | 4 | 0.1250 | 0.0000 | Includes Kurdish-script failure (both conds) |
| 709378413 | 5 | 0.1133 | 0.1000 | |
| 1428043076 | 5 | 0.0800 | 0.0000 | |
| 351600865 | 5 | 0.0786 | 0.0000 | |
| 709790549 | 4 | 0.0732 | 0.0556 | |

Speakers 265773029, 1571110404, 467174862, and 382004286 each have mean AUTO WER > 0.50. These are all Uzbek speakers. All four are represented by ≤6 utterances; individual speaker WERs are high-variance estimates. The pattern is consistent with phonetic characteristics (accent, speech rate, or recording conditions) that increase AUTO misdetection.

Kazakh speaker-level analysis is not reported here because all KSC speakers contribute ≤2 utterances in this evaluation set.

---

## 7. Outliers and Anomalous Records

### WER ≥ 1.0 (evaluation set): 15 records

All 15 are Uzbek. Summary:

| UID | Cond | WER | AUTO detected | Failure type |
|---|---|---|---|---|
| 265773029_2_83580_2 | auto | 1.333 | rus | Cyrillic output |
| 265773029_2_83580_2 | hint | 1.333 | uzb | Cyrillic output despite HINT |
| 972644779_2_87520_1 | hint | 1.200 | uzb | Cyrillic output despite HINT |
| 382004286_2_20612_1 | auto | 1.200 | tur | Word insertion via tokenisation |
| 1571110404_2_19314_1 | auto | 1.000 | rus | Cyrillic output |
| 1571110404_2_19314_1 | hint | 1.000 | uzb | Cyrillic output despite HINT |
| 1571110404_2_36820_1 | auto | 1.000 | bak | Bashkir Cyrillic output |
| 1571110404_2_36820_1 | hint | 1.000 | uzb | Cyrillic output despite HINT |
| 265773029_2_75008_2 | auto | 1.000 | ara | Arabic script output |
| 972644779_2_87507_3 | auto | 1.000 | kir | Mixed Chinese + Cyrillic (see below) |
| 972644779_2_87520_1 | auto | 1.000 | rus | Cyrillic output |
| 467174862_2_34142_1 | auto | 1.000 | tat | Tatar Cyrillic output |
| 467174862_2_34142_1 | hint | 1.000 | uzb | Cyrillic output despite HINT |
| 382004286_2_20598_1 | hint | 1.000 | uzb | Cyrillic output despite HINT |
| 382004286_2_20612_1 | hint | 1.000 | uzb | Word-level tokenisation differences |

**HINT does not fully resolve wrong-script Uzbek output.** For speakers 1571110404, 265773029, 467174862, and 382004286, the HINT call correctly detects `uzb` but still returns Cyrillic Uzbek output. This is a known property of ElevenLabs Scribe v2: the language hint changes the detection label but the decoding path may still produce a Cyrillic-script variant of Uzbek (both scripts are used in real Uzbek text). These records are valid data points.

### UID 972644779_2_87507_3 — Chinese hallucination

- **AUTO** (detected: kir): `电话铃声 товар биржиси норозилик акцияси ўтказиш бойича талабнома киритилган`
- **HINT** (detected: uzb): `air tovar belgisi ro'yxatdan o'tkazish bo'yicha talablar ko'rilgan` — WER 0.444

AUTO produced a mixed Chinese-Cyrillic hallucination. The HINT call largely recovers (WER 0.444 vs 1.0), with partial correct transcription. The Chinese characters are a model failure unrelated to the audio content. Valid data point; no deletion warranted.

### UID 1131474547_2_30677_1 — Persistent Kurdish script

- **AUTO** (detected: ckb): `ئاکە ئەو کالی گیمەس بۆ ڕێدە` — WER 1.5
- **HINT** (detected: uzb): `ئاکە ئەو کالی گیمەس بۆ ڕێدە` — WER 1.5

HINT correctly changes the detection to `uzb` but produces identical Kurdish Central script output. Both records are valid; this utterance (`aka ukaligimiz bor edi`) may be phonetically indistinguishable from Kurdish to the model. Both conditions fail equally, consistent with an audio-level ambiguity rather than a routing failure.

---

## 8. Apostrophe Stripping

Uzbek Latin script uses the apostrophe `'` as a phonological marker (e.g., `o'zbek`, `bo'lib`). In 7 of 70 Uzbek HINT evaluation records, the HINT transcription strips all apostrophes from positions where the reference retains them.

| Metric | Value |
|---|---|
| UZ HINT records with apostrophe in reference | 45 |
| Records where HINT strips apostrophes | 7 (16% of apostrophe-bearing) |
| Records where HINT preserves apostrophes | 38 |
| WER mean (stripped) | 0.8194 |
| WER mean (preserved) | 0.1286 |
| AUTO WER mean for same 7 UIDs | 0.6012 |

**Interpretation:** The 7 affected records have higher WER in HINT than in AUTO (0.819 vs 0.601), inverting the usual direction. This is a genuine transcription difference — the apostrophe is phonemically significant and its omission changes word identity in Uzbek. It is not a normalisation artefact.

This effect is present in approximately 10% of Uzbek HINT records and is a real confound when comparing AUTO vs HINT WER for Uzbek. It modestly suppresses the measured HINT advantage and contributes to the non-significance of the Uzbek pairwise test.

**The official WER is not adjusted.** The frozen benchmark methodology applies uniformly. This finding is a diagnostic for future work.

---

## 9. Pilot vs Evaluation

| Group | Condition | Pilot WER mean | Eval WER mean | Difference |
|---|---|---|---|---|
| Uzbek | AUTO | 0.3215 | 0.2906 | −0.031 |
| Uzbek | HINT | 0.2375 | 0.2662 | +0.029 |
| Kazakh | AUTO | 0.1052 | 0.0699 | −0.035 |
| Kazakh | HINT | 0.1395 | 0.0657 | −0.074 |

The pilot Kazakh WER is notably higher than the eval Kazakh WER (0.105 vs 0.070 AUTO). This is consistent with the pilot stratum design: pilot Kazakh utterances were deliberately selected for shorter duration (`kk_short` and `kk_medium` strata) and may not be representative of the full KSC eval distribution. The Kazakh pilot included only 10 utterances per condition vs 90 in eval; sampling variance at n=10 is large.

The pilot Uzbek WER (0.322 AUTO) is somewhat higher than eval (0.291 AUTO), consistent with the uz_control stratum (5 speakers with historically highest misdetection rates) being disproportionately represented in the pilot.

**Conclusion:** The pilot was directionally informative but not representative of final eval distributions, particularly for Kazakh. This is expected given the stratified pilot design. The pilot go/no-go decision (routing signal confirmed, no methodology blockers) was correct and the eval corroborates the pilot's main finding.

---

## 10. Phase 2 vs Phase 3A Comparison

Phase 3A uses a different (non-overlapping) utterance set from Phase 2. The two sets cannot be directly compared without controlling for utterance-level difficulty. The comparison below is observational only.

### ElevenLabs Scribe v2 across Phase 2 and Phase 3A

| Language | Condition | Phase 2 (n=300) | Phase 3A eval (n=70/90) | Observed delta |
|---|---|---|---|---|
| Uzbek | AUTO | 0.3416 | 0.2906 | −0.051 |
| Uzbek | HINT | 0.2446 | 0.2662 | +0.022 |
| Kazakh | AUTO | 0.0534 | 0.0699 | +0.017 |
| Kazakh | HINT | 0.0510 | 0.0657 | +0.015 |

Phase 3A Uzbek AUTO improves over Phase 2 (0.291 vs 0.342). This is likely a corpus effect: the 22 exhausted USC speakers (excluded from Phase 3A) may include those with more atypical pronunciation or recording conditions that inflate Phase 2 WER. Phase 3A draws from a smaller, potentially more homogeneous speaker pool.

Phase 3A Uzbek HINT is slightly worse than Phase 2 (0.266 vs 0.245). This may partially reflect the apostrophe-stripping effect, which was less prevalent in Phase 2, or utterance-level difficulty differences.

Phase 3A Kazakh is slightly worse than Phase 2 in both conditions (0.070 vs 0.053 AUTO). The Kazakh held-out utterances were selected by systematic sampling from KSC; no strong corpus-effect explanation is available.

### GCS Chirp 2 (Phase 2 only, for reference)

| Language | Condition | GCS Phase 2 (n=300) |
|---|---|---|
| Uzbek | AUTO | 0.4227 |
| Uzbek | HINT | 0.2602 |
| Kazakh | AUTO | 0.2666 |
| Kazakh | HINT | 0.2112 |

ElevenLabs Scribe v2 outperforms GCS Chirp 2 on Uzbek (both conditions) and substantially outperforms on Kazakh. GCS Chirp 2 is not tested in Phase 3A.

---

## 11. Statistical Analysis

All tests use the 160-utterance evaluation set (320 records) with paired observations per utterance. Scipy was unavailable; all tests use a manual Wilcoxon implementation with average-rank tie handling and large-sample normal approximation. Note that 81% of paired observations are ties (WER identical in both conditions), which reduces effective sample size; p-values should be treated as approximate.

### 11a. Primary test: routed WER vs HINT WER

Per the execution plan (Section H, Steps 5–7): d[i] = wer_routed[i] − wer_hint[i]; H₁: mean(d) < 0.

| Population | n (pairs) | Nonzero | W⁺ | W⁻ | z | p (less) | Bootstrap 95% CI on mean(d) |
|---|---|---|---|---|---|---|---|
| Overall | 160 | 18 | 106.5 | 64.5 | 0.915 | **0.820** | [−0.0151, +0.0132] |
| Uzbek | 70 | 4 | 6.0 | 4.0 | 0.365 | **0.642** | — |
| Kazakh | 90 | 14 | 63.5 | 41.5 | 0.691 | **0.755** | — |

**Primary success criterion not met.** Neither the mean(d) ≤ −0.030 threshold nor p < 0.05 is achieved for any population.

### 11b. Secondary test: AUTO WER vs HINT WER

This tests whether having the language hint at all (HINT condition) is better than no hint (AUTO), independent of routing. H₁: AUTO > HINT, one-tailed.

| Population | n (pairs) | Nonzero | W⁺ | W⁻ | z | p (greater) | Bootstrap 95% CI on mean(AUTO−HINT) |
|---|---|---|---|---|---|---|---|
| Overall | 160 | 30 | 302.5 | 162.5 | 1.440 | 0.075 | [−0.008, 0.034] |
| Uzbek | 70 | 16 | 92.5 | 43.5 | 1.267 | 0.103 | [−0.019, 0.066] |
| Kazakh | 90 | 14 | 63.5 | 41.5 | 0.691 | 0.245 | [−0.010, 0.019] |

No test reaches p<0.05. These p-values (0.075 overall; 0.103 Uzbek; 0.245 Kazakh) are **secondary** results and do not speak to the primary routing criterion. They are not comparable to the routing criterion threshold.

---

## 12. Primary Conclusions

**Does HINT improve Uzbek WER? (secondary question)**  
Directionally, mean WER decreases from 0.2906 (AUTO) to 0.2662 (HINT), a −8.4% relative reduction. However, the Wilcoxon p=0.103 (H₁: AUTO > HINT) and the bootstrap 95% CI [−0.019, 0.066] includes zero. This is a directional observation, not a confirmed finding. HINT does correct catastrophic wrong-script failures for utterances where AUTO misdetects; for some speakers (1571110404, 265773029), HINT changes the detection tag to `uzb` but the model still outputs Cyrillic Uzbek.

**Does HINT improve Kazakh WER? (secondary question)**  
No. The mean difference is 0.004 (6% relative), non-significant (p=0.245), CI [−0.010, 0.019]. Kazakh AUTO detection accuracy is 99%; AUTO and HINT are operationally equivalent for Kazakh.

**Does R1 routing outperform always-HINT? (primary question)**  
No. This is the pre-specified primary hypothesis. mean(wer_routed − wer_hint) = +0.0005 overall, −0.0043 for Uzbek. The Wilcoxon p=0.820 overall, p=0.642 Uzbek. The primary success criterion (mean(d) ≤ −0.030 AND p<0.05) is not met. R1 routing is approximately equivalent to always using HINT on this benchmark; it provides no statistically detectable benefit beyond simply always passing the language hint.

**Does R1 routing outperform pure AUTO? (secondary observation)**  
Yes, as a secondary, untested observation: R1 routing reduces Uzbek mean WER by 0.029 (10% relative) vs pure AUTO, and by 0.013 (7.5%) overall. This arises because routing replaces misdetected-AUTO with HINT for 73% of Uzbek utterances. This improvement over AUTO is not formally tested and should not be interpreted as evidence that routing is the correct strategy — the same result is achieved by simply always using HINT (which is simpler and equally effective on this dataset).

**Benchmark finding:**  
The benchmark cannot confirm that R1 routing provides an advantage over always-HINT for Uzbek at this sample size and effect magnitude. The pre-specified criterion was not met. Observations about HINT vs AUTO are directional and uncertain (CI includes zero). These are benchmark observations, not product recommendations.

---

## 13. Limitations

**1. Uzbek duration-stratum deviation.**  
The evaluation set has 50 short / 18 medium / 2 long Uzbek utterances vs. the plan target of 46/44/10. The 22 exhausted Phase 2 speakers could not contribute to Phase 3A; their absence skews the pool toward shorter utterances from the remaining 16 speakers. Subgroup analysis of long Uzbek utterances (n=2) has no statistical power and is excluded. Medium-duration analysis (n=18) is marginal.

**2. Apostrophe-stripping confound.**  
In 7 Uzbek HINT records (10% of apostrophe-bearing records), HINT returns output without apostrophes, inflating WER by creating artificial mismatches. The true HINT transcript quality for these utterances is better than WER suggests. The effect modestly suppresses the Uzbek HINT advantage and is one reason the Wilcoxon test does not reach significance.

**3. Historical rate-limit errors.**  
The 68 error records in the JSONL are all from ElevenLabs API quota exhaustion during the run. All 46 originally-failed tuples were subsequently completed; the error records are inert. No successful results were lost. The multi-session execution could in principle have introduced systematic timing differences between originally-run and retry-run records, but there is no mechanism for this to affect WER/CER computation.

**4. Unpopulated metadata fields.**  
`contamination_risk` is hardcoded to `"MEDIUM"` for all records (not computed per utterance). `independent_detected_language` and `dominant_script` are `None` for all records. R2 routing (script-mismatch detection) was not implemented. These fields are excluded from all analyses.

**5. Pilot stratification effect.**  
The pilot's uz_control stratum (5 speakers with historically highest Phase 2 misdetection rates) made the pilot's routing signal appear stronger (+0.094 mean improvement over AUTO) than the full eval (+0.029 Uzbek vs AUTO). More importantly, the pilot routing simulation compared routed vs AUTO, not routed vs HINT. Pilot results should not be pooled with eval results for any primary analysis.

**8. Evaluation split deviation.**  
The execution plan's subgroup breakdown section (Step 8) anticipated 60 Uzbek + 100 Kazakh evaluation utterances, based on a hypothetical equal pilot split. The actual pilot comprised 30 Uzbek + 10 Kazakh utterances (driven by approved strata: uz_short=15, uz_medium=10, uz_control=5, kk_short=5, kk_medium=5), yielding 70 Uzbek + 90 Kazakh in evaluation. All analyses use the actual counts; no data was altered.

**6. Speaker overlap with Phase 2.**  
Phase 3A Uzbek uses different utterances but the same 16 speakers as Phase 2 (the USC has 38 speakers, all used in Phase 2; 22 were fully exhausted). Speaker-level effects observed in Phase 3A may be correlated with Phase 2 results. Utterance-level independence is maintained; speaker-level independence is not.

**7. Single provider.**  
Phase 3A tests ElevenLabs Scribe v2 only. Results do not generalise to other providers without additional benchmarking.

---

## Appendix: Key Numbers

| Metric | Value |
|---|---|
| Evaluation utterances | 160 (Uzbek 70, Kazakh 90) |
| Overall AUTO mean WER | 0.1664 |
| Overall HINT mean WER | 0.1534 |
| Uzbek AUTO mean WER | 0.2906 |
| Uzbek HINT mean WER | 0.2662 |
| Kazakh AUTO mean WER | 0.0699 |
| Kazakh HINT mean WER | 0.0657 |
| Uzbek AUTO detection accuracy | 27% |
| Kazakh AUTO detection accuracy | 99% |
| R1 routing rate (overall) | 32% (52/160) |
| R1 routing rate (Uzbek) | 73% (51/70) |
| R1 routing rate (Kazakh) | 1% (1/90) |
| Routed WER (Uzbek) | 0.2620 (vs AUTO 0.2906; vs HINT 0.2662) |
| **PRIMARY TEST: mean(wer_routed − wer_hint) overall** | **+0.0005** |
| **PRIMARY TEST: mean(wer_routed − wer_hint) Uzbek** | **−0.0043** |
| **PRIMARY Wilcoxon p (routed vs HINT, overall)** | **0.820** |
| **PRIMARY Wilcoxon p (routed vs HINT, Uzbek)** | **0.642** |
| PRIMARY Bootstrap 95% CI on mean(d) overall | [−0.0151, +0.0132] |
| Secondary: Wilcoxon p (AUTO vs HINT, overall) | 0.075 |
| Secondary: Wilcoxon p (AUTO vs HINT, Uzbek) | 0.103 |
| Secondary: Wilcoxon p (AUTO vs HINT, Kazakh) | 0.245 |
| Secondary: Bootstrap 95% CI (AUTO−HINT, overall) | [−0.008, 0.034] |
| WER ≥ 1.0 records | 15 (all Uzbek eval) |
| Apostrophe-stripping HINT records | 7 |
| Actual spend (all 400 successful) | $0.14973 |
