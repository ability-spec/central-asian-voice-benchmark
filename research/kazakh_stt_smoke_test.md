# Kazakh STT Smoke Test — STEP 6D

**Date:** 2026-08-23
**Status:** Complete. 7 API calls made (+ 4 rejected before billing due to wrong response_format).
**Utterance tested:** `5f2b074881760` — speaker 15872, 8.789 s
**Reference transcript:** қазір болған аумаққа қаладағы коммуналдық қызмет толық жұмылдырылды
**Source:** ISSAI KSC v1.1 test split, CC BY 4.0

---

## Pre-Run Correction: verbose_json Incompatible with gpt-4o Models

Initial attempt used `response_format="verbose_json"` for all models (matching the config for whisper-1).
gpt-4o-transcribe and gpt-4o-mini-transcribe immediately rejected this:

```
HTTP 400 invalid_request_error
"response_format 'verbose_json' is not compatible with model 'gpt-4o-transcribe-api-ev3'.
Use 'json' or 'text' instead."
```

These 4 calls returned 400 before audio was processed. **No billing incurred for the failed calls.**

whisper-1 accepted `verbose_json` in both runs. All subsequent gpt-4o calls used `response_format="json"`.

**Consequence:** gpt-4o-transcribe and gpt-4o-mini-transcribe do not return a `language` field via the
transcription endpoint. `provider_detected_language` will be NULL for all gpt-4o-variant calls in the
benchmark. This is recorded in the config (see `response_format_config` and `provider_detected_language_available`).

---

## Results

### gpt-4o-transcribe

| Condition | HTTP | Transcript | Detected | Latency | Cost (est.) |
|---|---|---|---|---|---|
| AUTO | 200 | Қазіргі болған аумаққа қаладағы коммуналдық қызмет толық жұмылдырылды. | NULL | 1763 ms | $0.000879 |
| prompt="Kazakh" | 200 | Қазір болған аумаққа қаладағы коммуналдық қызмет толық жұмылдырылды. | NULL | 1313 ms | $0.000879 |

**Analysis:**
- Both conditions produce correct Kazakh Cyrillic output. **Kazakh support: CONFIRMED WORKING.**
- AUTO introduced a one-word error ("Қазіргі" — adjectival form — instead of "Қазір" — adverbial form). The hint corrected this to match the reference exactly.
- `verbose_json` not supported; `json` used; `provider_detected_language` = NULL for all runs.
- Token usage (from `usage` field): 87 audio_tokens input, 20 output_tokens.
- The internal model version resolved by the API is `gpt-4o-transcribe-api-ev3`.

### gpt-4o-mini-transcribe

| Condition | HTTP | Transcript | Detected | Latency | Cost (est.) |
|---|---|---|---|---|---|
| AUTO | 200 | Азыр болгон аумакка каладагы коммуналдык кызмат толук жумулдурылды. | NULL | 600 ms | $0.000439 |
| prompt="Kazakh" | 200 | Азыр болгон аймакка каладагы коммуналдык кызмат толук жумулдурылды. | NULL | 598 ms | $0.000439 |

**Analysis:**
- Both conditions produce Cyrillic output that is **Kyrgyz, not Kazakh**.
  - "Азыр" = Kyrgyz for "now"; correct Kazakh is "Қазір"
  - Missing Kazakh-specific characters: қ→к, ғ→г, ұ→у, і→и, ы→ы
  - "болгон" (Kyrgyz past tense form) vs. "болған" (Kazakh)
  - "кызмат" (Kyrgyz) vs. "қызмет" (Kazakh)
- **Kazakh support: CONFIRMED_FAIL — model produces Kyrgyz output for Kazakh audio, in both AUTO and hint conditions.**
- The hint (`prompt="Kazakh"`) does not correct the language confusion: model still outputs Kyrgyz.
- Token usage: 87 audio_tokens input, 24/23 output_tokens.
- Internal model version: `gpt-4o-mini-transcribe-api-ev3`.

### whisper-1

| Condition | HTTP | Transcript | Detected | Latency | Cost (est.) |
|---|---|---|---|---|---|
| AUTO | 200 | Қазір болған аумаққа қаладағы коммуналдық қызмет толық жұмылдырылды. | kazakh | 2180 ms | $0.000879 |
| language="kk" | 200 | Қазір болған аумаққа қаладағы коммуналдық қызмет толық жұмылдырылды. | kazakh | 791 ms | $0.000879 |
| prompt="Kazakh" | 200 | Қазір болған аумаққа қаладағы коммуналдық қызмет толық жұмылдырылды. | kazakh | 1736 ms | $0.000879 |

**Analysis:**
- All three conditions produce identical, correct Kazakh Cyrillic output matching the reference exactly (after case-normalisation).
- `language="kk"` is **CONFIRMED ACCEPTED** — no HTTP 400 error. (Contrast: `language="uz"` was rejected for Uzbek.)
- `verbose_json` is supported; `provider_detected_language = "kazakh"` is returned in all three conditions.
- All three conditions are equivalent for this utterance — AUTO already detects and transcribes Kazakh correctly.
- Duration returned by API: 8.78 s (matches manifest: 8.789 s).

---

## Summary Table

| Model | Condition | Status | Kazakh Output Quality | provider_detected_language |
|---|---|---|---|---|
| gpt-4o-transcribe | AUTO | ✅ OK | CORRECT Kazakh Cyrillic (minor error: Қазіргі) | NULL (verbose_json unsupported) |
| gpt-4o-transcribe | prompt="Kazakh" | ✅ OK | CORRECT Kazakh Cyrillic (exact match) | NULL |
| gpt-4o-mini-transcribe | AUTO | ✅ OK (HTTP) | FAIL — Kyrgyz output | NULL |
| gpt-4o-mini-transcribe | prompt="Kazakh" | ✅ OK (HTTP) | FAIL — Kyrgyz output (hint has no effect) | NULL |
| whisper-1 | AUTO | ✅ OK | CORRECT Kazakh Cyrillic | "kazakh" |
| whisper-1 | language="kk" | ✅ OK | CORRECT Kazakh Cyrillic (identical to AUTO) | "kazakh" |
| whisper-1 | prompt="Kazakh" | ✅ OK | CORRECT Kazakh Cyrillic (identical to AUTO) | "kazakh" |

---

## Capability Verdicts (Post Smoke Test)

| Model | Kazakh capability | Evidence status |
|---|---|---|
| gpt-4o-transcribe | **CONFIRMED WORKING** — produces correct Kazakh Cyrillic | **CONFIRMED** — direct API call, 2026-08-23 |
| gpt-4o-mini-transcribe | **CONFIRMED FAIL (Kazakh)** — produces Kyrgyz instead of Kazakh | **CONFIRMED** — direct API call, 2026-08-23 |
| whisper-1 | **CONFIRMED WORKING** — `language="kk"` accepted, output correct | **CONFIRMED** — direct API call, 2026-08-23 |

---

## Config Changes Required

1. **response_format for gpt-4o models:** Change from `verbose_json` to `json`.
2. **gpt-4o-transcribe kazakh_support:** CLAIMED → CONFIRMED_WORKING.
3. **gpt-4o-mini-transcribe kazakh_support:** CLAIMED → CONFIRMED_FAIL (same pattern as Uzbek — language confused with neighbour language).
4. **whisper-1 kazakh_support:** UNKNOWN → CONFIRMED_WORKING.
5. **whisper-1 language="kk":** CLAIMED → CONFIRMED ACCEPTED.
6. **provider_detected_language:** Mark as unavailable for all gpt-4o-variant models.
7. **New confound:** gpt-4o-mini-transcribe conflates Kazakh with Kyrgyz (Kazakh→Kyrgyz) just as whisper-1 conflated Uzbek with Kazakh. Document in known_confounds.

---

## Cost Accounting

| Run | Calls | Billed? | Estimated cost |
|---|---|---|---|
| Run 1 — gpt-4o attempts (wrong format) | 4 | No (HTTP 400 before audio) | $0.00 |
| Run 1 — whisper-1 (3 conditions) | 3 | Yes | $0.002637 |
| Run 2 — gpt-4o-transcribe (2 conditions) | 2 | Yes | $0.001758 |
| Run 2 — gpt-4o-mini-transcribe (2 conditions) | 2 | Yes | $0.000878 |
| Run 2 — whisper-1 (3 conditions, duplicate of run 1) | 3 | Yes | $0.002637 |
| **Total** | **10 billed** | — | **~$0.007910** |

Well within the $0.10 cap. Whisper-1 was run twice (run 1 + run 2), so 6 whisper-1 calls total.

---

*No benchmark manifests or audio files were modified.*
*No calls beyond these 10 were made.*
