# Uzbek STT Smoke Test — Initial Results

**Date:** 2026-08-24
**Status:** Smoke test only. NOT final benchmark results.
**Purpose:** Determine which providers can produce any recognisable Uzbek output before committing to a formal benchmark corpus and evaluation methodology.

---

## Test Corpus

| File | Duration |
|---|---|
| `uzbek voice test.mp3` | ~10.8 s |
| `uzbek voice test 2.mp3` | ~14.7 s |

Both recordings are from a single speaker. Submitted as-is — no preprocessing or normalisation.

---

## Note on OpenAI Language Parameter

All three OpenAI models tested here reject the ISO 639-1 code `uz` at the API level. This is a parameter limitation, not evidence that these models cannot recognise Uzbek speech. Recognition capability was assessed separately by submitting audio with auto-detect or `prompt="Uzbek"`. Results are reported on that basis.

---

## Results

### AWS Bedrock — mistral.voxtral-mini-3b-2507

| Field | Value |
|---|---|
| **Provider** | AWS Bedrock (us-east-2) |
| **Recordings tested** | 2 |
| **Recording 1** | FAIL |
| **Recording 2** | FAIL |
| **Failure mode** | Did not produce recognisable Uzbek on either recording. Detailed raw output was not preserved from the prior session in which this test was conducted. |
| **Evidence status** | CONFIRMED FAIL |

---

### AWS Bedrock — mistral.voxtral-small-24b-2507

| Field | Value |
|---|---|
| **Provider** | AWS Bedrock (us-east-2) |
| **Recordings tested** | 2 |
| **Recording 1** | FAIL |
| **Recording 2** | FAIL |
| **Failure mode** | Did not produce recognisable Uzbek on either recording. Detailed raw output was not preserved from the prior session in which this test was conducted. |
| **Evidence status** | CONFIRMED FAIL |

---

### OpenAI — whisper-1

| Field | Value |
|---|---|
| **Provider** | OpenAI |
| **`uz` language parameter** | Rejected — HTTP 400 `unsupported_language` |
| **Recordings tested** | 2 (auto-detect) |
| **Recording 1** | FAIL |
| **Recording 2** | FAIL |
| **Latency range** | 2151–2609 ms |
| **Failure mode** | Auto-detect returned `detected_language: "kazakh"` on both recordings and produced Kazakh Cyrillic output. The model conflated Uzbek with its nearest high-resource Turkic neighbour. This is a recognition failure independent of the parameter rejection. |
| **Evidence status** | CONFIRMED FAIL |

**Recording 1 output (auto-detect):**
> Бүгін біз сүнійін тілік ерді әміді өз бектілдеге ауазыи технологияларыны санап қорамыз. Бұл күтек тест орқали тізім нұтқыны қанчалеге ашы түсіні жүрінішіні тек кереміз.

*(Kazakh Cyrillic — not Uzbek)*

**Recording 2 output (auto-detect):**
> Бүгін мен үзбектіліді қысқа нұтуқы язып ол епмен. Біз сөйлейін тілік еордамында оазыны мәтінге айлантырыш кісімлеріні снап көреп міз. Үш бұл тест орқали модель үзбектіліді әйге нұтуқыны қанчалық яғшы чүнішініктік шырамыз.

*(Kazakh Cyrillic — not Uzbek)*

---

### OpenAI — gpt-4o-mini-transcribe

| Field | Value |
|---|---|
| **Provider** | OpenAI |
| **`uz` language parameter** | Rejected — HTTP 400 `invalid_value` |
| **Recordings tested** | 2 (auto-detect and `prompt="Uzbek"`) |
| **Recording 1** | PASS — correct Uzbek Latin |
| **Recording 2** | FAIL — Uyghur Arabic script |
| **Latency range** | 690–1718 ms |
| **Failure mode** | Recording 2 produced Uyghur Arabic script under both auto-detect and `prompt="Uzbek"` conditions. One run produced a corrupted mixed-script token (`yardامىدا`). Behaviour was inconsistent between two recordings from the same speaker in the same session. |
| **Evidence status** | CONFIRMED INCONSISTENT — not suitable for Uzbek benchmarking in current form |

**Recording 1 output (auto-detect):**
> Bugun biz sun'iy intellekt yordamida O'zbek tilidagi ovoziy texnologiyalarini sinab ko'ramiz bu kichik test orqali tizim nutqini qanchalik yaxshi tushunishini tekshiramiz.

**Recording 2 output (auto-detect):**
> بۈگۈن مەن ئۆزبېك تىلىدا قىسقىنا نۇتق يازۇپ ئالىيەمەن. بىز زۇمىن ئىنتىلىلىك ياردەمىدە ئاۋازنى ماتنغا ئايلاندىرىش تىزىملىرىنى سىنىپ كۆرىمىز.

*(Uyghur Arabic script — wrong writing system for modern Uzbek)*

---

### OpenAI — gpt-4o-transcribe

| Field | Value |
|---|---|
| **Provider** | OpenAI |
| **`uz` language parameter** | Rejected — HTTP 400 `invalid_value` |
| **Recordings tested** | 2 (auto-detect and `prompt="Uzbek"`) |
| **Recording 1** | PASS — correct Uzbek Latin |
| **Recording 2** | PASS — correct Uzbek Latin |
| **Latency range** | 838–1245 ms |
| **Workaround** | Omit the language parameter (auto-detect) or pass `prompt="Uzbek"`. Both approaches produced correct output on both recordings. |
| **Minor variant** | One run produced `so'niy` instead of `sun'iy` (artificial intelligence) — phonetically plausible, semantically incorrect. All other output was coherent. |
| **Evidence status** | CONFIRMED WORKING |

**Recording 1 output (auto-detect):**
> Bugun biz sun'iy intellekt yordamida o'zbek tilidagi ovozli texnologiyalarni sinab ko'ramiz. Bu kichik test orqali tizim nutqni qanchalik yaxshi tushunishini tekshiramiz.

**Recording 2 output (prompt="Uzbek"):**
> Bugun men o'zbek tilida qisqa nutq yozib olayapman. Biz sun'iy intellekt yordamida ovozni matnga aylantirish tizimlarini sinab ko'rayapmiz. Ushbu test orqali model o'zbek tilidagi nutqni qanchalik yaxshi tushunishini tekshiramiz.

---

## Summary Table

| Provider | Model | `uz` parameter | Recording 1 | Recording 2 | Overall |
|---|---|---|---|---|---|
| AWS Bedrock | mistral.voxtral-mini-3b-2507 | not tested | FAIL | FAIL | CONFIRMED FAIL |
| AWS Bedrock | mistral.voxtral-small-24b-2507 | not tested | FAIL | FAIL | CONFIRMED FAIL |
| OpenAI | whisper-1 | REJECTED | FAIL | FAIL | CONFIRMED FAIL |
| OpenAI | gpt-4o-mini-transcribe | REJECTED | PASS | FAIL | CONFIRMED INCONSISTENT |
| OpenAI | gpt-4o-transcribe | REJECTED | PASS | PASS | CONFIRMED WORKING |

---

## Known Limitations of the Current Test

1. **Only 2 recordings tested.** Sufficient to screen for any Uzbek output; not sufficient to characterise accuracy, robustness, or generalisation.
2. **Single speaker.** Results may not generalise to other voices, accents, or speaking rates.
3. **Short recordings.** Both files are under 15 seconds. Longer or conversational audio is untested.
4. **No human ground-truth transcript.** Quality is assessed by script correctness and semantic coherence only. WER/CER cannot be computed yet.
5. **No Kazakh testing.** All results above are Uzbek only. No Kazakh recordings, API calls, or results exist yet.
6. **Google Cloud STT not tested.** No credentials are configured.
7. **ElevenLabs STT not tested.** No API key is configured.
8. **Azure STT not tested.** No subscription key is configured.
9. **Voxtral raw output not preserved.** The Voxtral tests were conducted in a prior session. The exact transcription outputs and failure details were not recorded at the time.
10. **No statistical significance.** Two recordings from one speaker permit no statistical claims. This is a feasibility screen, not a benchmark.

---

*This document records only what was directly observed. All claims labelled CONFIRMED reflect actual API responses received during testing. No extrapolation beyond observed results is intended.*
