# Phase 2 Cost Estimate
**Date:** 2026-08-24
**Status:** Planning estimate only. No API calls made. No money spent.
**Pricing sources:** Official documentation fetched 2026-08-24. Verify all prices before any run.

---

## Audio Duration Baseline

From Phase 1 frozen manifests (immutable):

| Language | Utterances | Total audio | Mean duration |
|---|---|---|---|
| Uzbek | 300 | 1,307.8 s = 21.80 min | 4.4 s |
| Kazakh | 300 | 2,233.6 s = 37.23 min | 7.4 s |
| **Combined** | **600** | **3,541.4 s = 59.02 min** | |

### Pilot Audio (20 utterances per language)
Proportional sample: 20/300 of each language's total.

| Language | Utterances | Audio |
|---|---|---|
| Uzbek pilot | 20 | 1,307.8 × (20/300) = 87.2 s = **1.45 min** |
| Kazakh pilot | 20 | 2,233.6 × (20/300) = 148.9 s = **2.48 min** |
| **Pilot total** | **40** | **3.93 min** |

Pilot requests per provider: 40 utterances × 2 conditions (AUTO + HINT) = **80 requests**
Total pilot audio submitted per provider: 3.93 min × 2 conditions = **7.86 audio-minutes**

### Full Benchmark Audio per Provider
600 utterances × 2 conditions = **1,200 requests**
Total full benchmark audio submitted per provider: 59.02 min × 2 conditions = **118.04 audio-minutes**

Track A (FLEURS) adds approximately 650–900 utterances per language (exact size TBD after download). Using 750/language as a working estimate:
- FLEURS Uzbek (750 utterances): ~750 × 4.4 s average = 3,300 s = 55 min (estimate)
- FLEURS Kazakh (750 utterances): ~750 × 7 s average = 5,250 s = 87.5 min (estimate)
- FLEURS combined: ~142.5 min × 2 conditions = ~285 audio-minutes per provider

*FLEURS estimates are rough. Actual FLEURS audio duration is unknown until download. Recalculate before authorising Track A runs.*

---

## Pricing Summary

| Provider | Model | Price per audio-minute | Pricing basis | Verified? |
|---|---|---|---|---|
| ElevenLabs | scribe_v2 | ~$0.054/min (effective) | 330 credits/min @ Pro plan | NEEDS_VERIFICATION for API overage rate |
| Google Cloud STT | chirp_2 | $0.021/min | $0.00035/second | CONFIRMED |
| Azure Speech | Fast Transcription | ~$0.0167/min (~$1.00/hr) | Per hour | NEEDS_VERIFICATION — exact USD not rendered |
| Google Gemini | gemini-2.5-flash | ~$0.00192/min | $1.00/1M tokens, 32 tok/s | CONFIRMED pricing; language support unverified |

---

## Track B (Frozen 600-Utterance Benchmark)

### Pilot Cost (40 utterances, 7.86 audio-minutes per provider)

| Provider | Model | Rate | Pilot cost |
|---|---|---|---|
| ElevenLabs | scribe_v2 | ~$0.054/min | **~$0.42** |
| Google Cloud STT | chirp_2 | $0.021/min | **$0.17** |
| Azure Speech | Fast Transcription | ~$0.0167/min | **~$0.13** |
| Google Gemini | gemini-2.5-flash | ~$0.00192/min | **~$0.02** |
| **Pilot total (all 4 providers)** | | | **~$0.74** |

### Full Track B Benchmark Cost (600 utterances, 118.04 audio-minutes per provider)

| Provider | Model | Rate | Full benchmark cost |
|---|---|---|---|
| ElevenLabs | scribe_v2 | ~$0.054/min | **~$6.37** |
| Google Cloud STT | chirp_2 | $0.021/min | **$2.48** |
| Azure Speech | Fast Transcription | ~$0.0167/min | **~$1.97** |
| Google Gemini | gemini-2.5-flash | ~$0.00192/min | **~$0.23** |
| **Track B total (all 4 providers)** | | | **~$11.05** |

*Track B total with pilot included: ~$11.79*

---

## Track A (FLEURS ~285 audio-minutes per provider — estimate)

| Provider | Model | Rate | Track A estimate |
|---|---|---|---|
| ElevenLabs | scribe_v2 | ~$0.054/min | **~$15.39** |
| Google Cloud STT | chirp_2 | $0.021/min | **$5.99** |
| Azure Speech | Fast Transcription | ~$0.0167/min | **~$4.76** |
| Google Gemini | gemini-2.5-flash | ~$0.00192/min | **~$0.55** |
| **Track A total (all 4 providers)** | | | **~$26.69** |

*These are rough estimates. Recalculate with actual FLEURS audio durations after download.*

---

## Combined Phase 2 Cost (Track A + Track B + Pilot)

| Component | Estimated cost |
|---|---|
| Pilot (all 4 providers, Track B only) | ~$0.74 |
| Track B full (all 4 providers) | ~$11.05 |
| Track A full (all 4 providers, FLEURS) | ~$26.69 |
| **Phase 2 total** | **~$38.48** |

---

## Maximum Possible Cost Scenario

Worst case — all providers succeed, both tracks run fully, Gemini included:

| Source | Cost |
|---|---|
| Track B (4 providers × 118 min) | $11.05 |
| Track A (4 providers × 285 min, estimate) | $26.69 |
| Retries (10% overhead on full runs) | ~$3.77 |
| ElevenLabs overage rate uncertainty (2× safety factor on ElevenLabs) | +$6.37 |
| Azure pricing uncertainty (1.5× safety factor on Azure) | +$0.99 |
| **Maximum possible Phase 2 cost** | **~$48.87** |

---

## Recommended Spending Cap

**Hard cap: $60.00 for all of Phase 2.**

Rationale:
- Maximum possible cost estimate is ~$49.
- $60 cap provides $11 headroom (~22%) for pricing changes, retries, Gemini smoke test, and FLEURS duration underestimates.
- The cap is consistent with a no-surprises solo research budget.
- If Track A FLEURS audio turns out substantially longer than estimated (e.g. Kazakh average duration >> 7 s), recalculate before authorising Track A runs.

### Pre-Run Authorization Process
Before any API call:
1. Calculate per-provider cost estimate using exact audio durations from manifest
2. Record estimate in `benchmark/config/phase2_cost_estimate_prerun.txt`
3. Confirm estimate is within remaining cap
4. Abort if projected cost would exceed cap

### Partial Execution if Cap is Tight
If budget is constrained, priority order:
1. Track B pilot (all 4 providers) — highest value per dollar, validates integration
2. Track B full (cheapest providers first: Gemini, Azure, Google Cloud STT, ElevenLabs)
3. Track A (FLEURS) — add after Track B is complete

---

## Pricing Verification Required Before Any Run

| Item | Status |
|---|---|
| ElevenLabs API overage rate (per-minute for PAYG) | NEEDS_VERIFICATION at `elevenlabs.io/pricing/api` |
| Azure Fast Transcription exact per-hour price | NEEDS_VERIFICATION via Azure pricing calculator |
| Google Cloud Chirp regional pricing differences | NEEDS_VERIFICATION (us vs eu vs asia regions) |
| Gemini 2.5 Flash rate limits (RPM/TPM) | NEEDS_VERIFICATION at `aistudio.google.com/rate-limit` |

---

*All estimates are pre-run projections. Actual costs may differ. No API calls have been made.*
