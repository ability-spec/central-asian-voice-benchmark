# STT Benchmark Phase 1 — Cost Estimate

**Date:** 2026-08-23
**Status:** Pre-run estimate only. No API calls made. No costs incurred.
**Pricing source:** developers.openai.com/api/docs/pricing (verified 2026-08-23)

---

## Audio Inventory

| Language | Total duration | Utterances | Mean duration |
|---|---|---|---|
| Uzbek | 1,307.8 s = **21.8 min** | 300 | 4.36 s |
| Kazakh | 2,232.0 s = **37.2 min** | 300 | 7.44 s |
| Combined | 3,539.8 s = **59.0 min** | 600 | 5.90 s |

Source: `research/audio_benchmark_statistics.md`

---

## Phase 1 Scope

| Dimension | Value |
|---|---|
| Models | gpt-4o-transcribe, gpt-4o-mini-transcribe, whisper-1 |
| Conditions per model | 2 (auto + hint) |
| Utterances per language | 300 |
| Total requests | 3 × 2 × 600 = **3,600** |
| Total audio-minutes | 59.0 min × 3 models × 2 conditions = **354.0 min** |
| Audio-minutes per model | 59.0 min × 2 conditions = **118.0 min** |

---

## Pricing (Confirmed)

| Model | Audio rate | Output token rate | Source |
|---|---|---|---|
| gpt-4o-transcribe | $0.006000 / min | $10.00 / 1M tokens | developers.openai.com/api/docs/pricing |
| gpt-4o-mini-transcribe | $0.003000 / min | $5.00 / 1M tokens | developers.openai.com/api/docs/pricing |
| whisper-1 | $0.006000 / min | None | developers.openai.com/api/docs/pricing |

---

## Audio Cost (Primary Rate)

| Model | Audio-minutes | $/min | Audio cost |
|---|---|---|---|
| gpt-4o-transcribe | 118.0 | $0.006000 | **$0.708** |
| gpt-4o-mini-transcribe | 118.0 | $0.003000 | **$0.354** |
| whisper-1 | 118.0 | $0.006000 | **$0.708** |
| **Phase 1 total (audio)** | **354.0** | — | **$1.770** |

---

## Output Token Cost (gpt-4o models only — Conservative Estimate)

The gpt-4o-transcribe and gpt-4o-mini-transcribe models carry an additional per-output-token rate. Whether this applies to the `/v1/audio/transcriptions` endpoint or only to text-in/text-out usage is not definitively documented. This estimate includes it as a conservative upper bound.

### Token volume estimate

```
Assumed speech rate: 2.5 words/second
Assumed tokenisation: 1.35 tokens/word

Uzbek (600 utterances total across 2 conditions × 1 model):
  300 utterances × 4.36 s/utt × 2.5 words/s × 1.35 tokens/word ≈ 4,414 tokens per model-condition

Kazakh (same basis):
  300 utterances × 7.44 s/utt × 2.5 words/s × 1.35 tokens/word ≈ 7,533 tokens per model-condition

Per model, per condition:  4,414 + 7,533 = 11,947 tokens
Per model, both conditions: 11,947 × 2 = 23,894 tokens
```

### Token cost

| Model | Output tokens (est.) | $/1M tokens | Token cost |
|---|---|---|---|
| gpt-4o-transcribe | 23,894 | $10.00 | **$0.239** |
| gpt-4o-mini-transcribe | 23,894 | $5.00 | **$0.120** |
| whisper-1 | — | n/a | **$0.000** |
| **Subtotal (tokens)** | | | **$0.359** |

---

## Phase 1 Total — Two Scenarios

| Scenario | Audio | Tokens | Total |
|---|---|---|---|
| Audio-rate-only (floor) | $1.770 | $0.000 | **$1.770** |
| Audio + output tokens (ceiling) | $1.770 | $0.359 | **$2.129** |
| Conservative upper bound (estimation uncertainty ±20%) | — | — | **~$2.55** |

**Working estimate for budget purposes: $2.50 or less.**

---

## Per-Model Breakdown

| Model | Audio | Tokens (est.) | Model total |
|---|---|---|---|
| gpt-4o-transcribe | $0.708 | $0.239 | **$0.947** |
| gpt-4o-mini-transcribe | $0.354 | $0.120 | **$0.474** |
| whisper-1 | $0.708 | $0.000 | **$0.708** |
| **Phase 1 total** | **$1.770** | **$0.359** | **$2.129** |

---

## Retry Budget

Phase 1 hard cap: 4,000 requests (400 headroom above 3,600 planned).

If all 400 retry slots are consumed at the average audio rate:
```
400 requests × 5.90 s avg / 60 s = 39.3 audio-minutes of retries
39.3 min × weighted avg $0.005/min = ~$0.20 additional
```

Conservative maximum including retries: **~$2.75**

---

## Comparison

| Comparison point | Value |
|---|---|
| Phase 1 estimated cost | $2.13 (incl. tokens) |
| Phase 1 estimated cost (audio only) | $1.77 |
| Phase 1 max with retries | ~$2.75 |
| Per-request average | $2.13 / 3,600 = $0.00059 |
| Per audio-minute average | $2.13 / 354.0 = $0.0060 |

---

## Notes and Caveats

1. **Pricing retrieval date:** 2026-08-23. OpenAI pricing is subject to change. Re-verify before running the benchmark if substantial time has elapsed.

2. **Output token uncertainty:** It is unconfirmed whether the `/v1/audio/transcriptions` endpoint bills output tokens separately or only the audio rate. The floor estimate ($1.77) assumes audio-rate-only; the ceiling ($2.13) adds conservatively estimated output tokens.

3. **Duration measurement:** Uzbek and Kazakh total durations are from verified WAV files in `audio_benchmark_manifest.csv` (SHA-256: `d01408af2e04d048a44600138ac878f97b2a2372f62b9a42f2f7d0b161f34924`). These are fixed.

4. **Minimum billing unit:** OpenAI docs do not specify a minimum billing unit. This estimate assumes the actual audio duration is billed (no rounding up to the nearest 15 s or similar). If OpenAI rounds up per request, actual cost could be higher by up to (3,600 × per-request-rounding × $0.006/min). For 15-second rounding on 5.9-second average audio: up to ~$5.25 additional — unlikely given the pricing is per-minute, not per-request.

5. **Phase 2 / Phase 3 costs not included:** GCP Chirp and Azure STT costs are not estimated here. Open-source models (Whisper large-v3, MMS, etc.) will have compute costs not reflected in this document.

6. **This document is pre-run only.** Actual costs are recorded in `benchmark/logs/<run_id>/cost_actual.txt` after the run.

---

*No API calls have been made. No money has been spent.*
