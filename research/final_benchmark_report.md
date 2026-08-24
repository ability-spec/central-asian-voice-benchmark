# Phase 1 STT Benchmark — Final Report

**Run ID:** `pilot_001`  
**Total records:** 3600 / 3,600 logical  
**Total cost:** $2.1703  
**Languages:** Uzbek (uz) · Kazakh (kk)  
**Models:** gpt-4o-transcribe · gpt-4o-mini-transcribe · whisper-1  
**Conditions:** AUTO (no hint) · HINT (language supplied)  
**Contamination risk:** MEDIUM (ISSAI CC BY 4.0 corpora)  

---

## Summary Table

| Model | Lang | Cond | WER | CER | Script | FT-LID | Cust-LID | Prov-LID | P50ms | P95ms | Cost$ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gpt-4o-mini-transcribe | kk | auto | 0.452 | 0.170 | 0.983 | 0.700 | 0.753 | — | 644 | 925 | 0.1512 |
| gpt-4o-mini-transcribe | kk | hint | 0.359 | 0.126 | 0.993 | 0.857 | 0.873 | — | 623 | 952 | 0.1508 |
| gpt-4o-mini-transcribe | uz | auto | 0.755 | 0.537 | 0.540 | 0.323 | 0.363 | — | 588 | 857 | 0.0955 |
| gpt-4o-mini-transcribe | uz | hint | 0.492 | 0.243 | 0.873 | 0.533 | 0.643 | — | 600 | 940 | 0.0940 |
| gpt-4o-transcribe | kk | auto | 0.257 | 0.106 | 0.987 | 0.940 | 0.950 | — | 786 | 1131 | 0.2992 |
| gpt-4o-transcribe | kk | hint | 0.227 | 0.088 | 1.000 | 0.990 | 0.993 | — | 801 | 1169 | 0.2989 |
| gpt-4o-transcribe | uz | auto | 0.545 | 0.285 | 0.867 | 0.480 | 0.613 | — | 731 | 1119 | 0.1874 |
| gpt-4o-transcribe | uz | hint | 0.316 | 0.121 | 0.993 | 0.653 | 0.807 | — | 578 | 841 | 0.1851 |
| whisper-1 | kk | auto | 0.532 | 0.194 | 0.953 | 0.903 | 0.907 | 0.893 | 1488 | 2594 | 0.2234 |
| whisper-1 | kk | hint | 0.495 | 0.144 | 1.000 | 0.980 | 0.990 | 1.000 | 1460 | 2460 | 0.2234 |
| whisper-1 | uz | auto | 1.141 | 0.690 | 0.550 | 0.040 | 0.287 | 0.020 | 1310 | 3145 | 0.1308 |
| whisper-1 | uz | hint | 1.150 | 0.817 | 0.351 | 0.035 | 0.063 | 0.004 | 1352 | 2822 | 0.1308 |

---

## Key Findings

### AUTO vs HINT

- **gpt-4o-transcribe uz**: AUTO WER=0.545, HINT WER=0.316 → HINT is better (Δ=-0.229)  
- **gpt-4o-mini-transcribe uz**: AUTO WER=0.755, HINT WER=0.492 → HINT is better (Δ=-0.263)  
- **whisper-1 uz**: AUTO WER=1.141, HINT WER=1.150 → HINT is similar (Δ=+0.009)  
- **gpt-4o-transcribe kk**: AUTO WER=0.257, HINT WER=0.227 → HINT is better (Δ=-0.030)  
- **gpt-4o-mini-transcribe kk**: AUTO WER=0.452, HINT WER=0.359 → HINT is better (Δ=-0.093)  
- **whisper-1 kk**: AUTO WER=0.532, HINT WER=0.495 → HINT is better (Δ=-0.037)  

### gpt-4o-mini-transcribe Kazakh — CONFIRMED FAIL

gpt-4o-mini-transcribe produces Kyrgyz Cyrillic output for Kazakh audio. Hint sent (prompt='Kazakh') but CONFIRMED_SENT_INEFFECTIVE.  
- AUTO: WER=0.452 Script=0.983 FT-LID=0.700  
- HINT: WER=0.359 Script=0.993 FT-LID=0.857  

---

## LID Methodology

Two-layer independent LID (neither is ground truth):

**Layer 1 — fastText `lid.176.bin`** (primary for new records)  
SHA-256: `7e69ec5451bc261cc7844e49e4792a85d7f09c06789ec800fc4a44aec362764e`  
Python 3.12.10 · fasttext-wheel==0.9.2 · numpy==1.26.4  
- kk recall (pilot): **95.0%** ✓  
- uz recall (pilot): **32.5%** ✗ (fastText misclassifies Uzbek Latin as Turkish/Azerbaijani)  
- kk→ky correctly identified (improvement over custom)  

**Layer 2 — `custom_script_based_v1`** (secondary diagnostic / pilot primary)  
Unicode character analysis. uz recall (pilot): 67.5%.  
240 pilot records: `independent_detected_language` = custom result. 3,360 new records: `independent_detected_language` = fasttext, `custom_lid_diagnostic` = custom.  

**Uzbek LID caveat:** Neither tool meets the 80% uz recall threshold. Results are diagnostic only.  

---

## Known Limitations

1. **Contamination risk: MEDIUM** — ISSAI corpora CC BY 4.0; models may have seen this data.  
2. **Uzbek LID unreliable** — fastText 32.5%, custom 67.5%; neither meets 80% threshold.  
3. **gpt-4o-mini Kazakh: FAIL** — produces Kyrgyz Cyrillic; hint ineffective.  
4. **whisper-1 Uzbek hint: CLAIMED** — `prompt='Uzbek'` sent; effectiveness unconfirmed. ISO `language='uz'` rejected by API.  
5. **Provider LID unavailable** for gpt-4o-transcribe and gpt-4o-mini-transcribe.  
6. **Uyghur Arabic hallucinations** in Uzbek audio — gpt-4o models produce Uyghur Arabic script for some Uzbek utterances.  
7. **Mixed LID methodology** — pilot (240) uses custom LID; new records (3,360) use fasttext primary.  
8. **AUTO=HINT for whisper-1 Uzbek** — both conditions send `prompt='Uzbek'` (CLAIMED hint). Effectively same condition.  

---

## Methodology

- Audio: 16kHz mono 16-bit PCM WAV; 300 Uzbek (21.8 min) + 300 Kazakh (37.2 min)  
- Normalisation: NFC → casefold → apostrophe unification → punctuation strip → whitespace  
- WER/CER: `jiwer` library  
- Cost: audio_minutes × price_per_min + output_tokens/1M × token_rate  
- Dedup: deterministic request IDs; existing records never overwritten  
- AUTO and HINT never averaged — reported separately  

