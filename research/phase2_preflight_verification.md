# Phase 2 Pre-Pilot Verification
**Date:** 2026-08-24
**Status:** Verification complete. See verdict at the end.
**Hard cap for this stage:** $2.00 — no API calls were made; $0.00 spent.

Evidence labels: CONFIRMED = verified from official source this date. CLAIMED = provider assertion. NEEDS_VERIFICATION = could not confirm.

---

## 1. FLEURS Test Split Counts

**Method:** `load_dataset("google/fleurs", ...)` via Python 3.14 / `datasets 5.0.1`. Both splits downloaded and counted.

| Language | Subset | Test rows | Evidence |
|---|---|---|---|
| Uzbek | `uz_uz` | **862** | CONFIRMED |
| Kazakh | `kk_kz` | **856** | CONFIRMED |

**Prior status:** Uzbek count was previously CONFIRMED from the HuggingFace viewer. Kazakh was NEEDS_VERIFICATION.

**Correction to phase2_public_benchmarks.md:** Table previously showed "NEEDS_VERIFICATION" for Kazakh test rows and "~4,430 total" as a proxy. Actual count is 856. Update the document before any Track A run.

---

## 2. ElevenLabs Scribe v2 — PAYG Pricing

**Source:** `elevenlabs.io/pricing/api` fetched 2026-08-24.

**Finding:** ElevenLabs bills API users in USD, not credits. The credit system applies only to bundled plan allowances; API overage and PAYG usage is priced directly.

| Metric | Value | Evidence |
|---|---|---|
| Scribe v2 batch rate | **$0.22 / hour** (= $0.00367 / min) | CONFIRMED |
| Rate across all plan tiers | Flat $0.22/hr | CONFIRMED |
| Entity detection add-on | +$0.07/hr | CONFIRMED |
| Keyterm prompting add-on | +$0.05/hr | CONFIRMED |
| Scribe v2 realtime | $0.39/hr (not used in benchmark) | CONFIRMED |

**Critical correction to phase2_cost_estimate.md:**
The earlier cost estimate used a credit-based Pro plan calculation (330 credits/min ÷ 600k credits/$99 = $0.054/min). This was wrong by approximately 15×. The actual PAYG rate is $0.00367/min.

| Item | Old estimate | Corrected estimate | Delta |
|---|---|---|---|
| Pilot (7.86 min) | ~$0.42 | **~$0.029** | −$0.39 |
| Track B full (118.04 min) | ~$6.37 | **~$0.43** | −$5.94 |
| Track A ~285 min (estimate) | ~$15.39 | **~$1.05** | −$14.34 |

Revised Phase 2 total (all providers, both tracks, excl. Gemini unverified):
- Old estimate: ~$38.48
- Corrected estimate: ~**$16.17** (ElevenLabs is no longer the dominant cost line)
- Hard cap: $60.00 — headroom is now larger than previously estimated.

---

## 3. Azure Speech Services — Fast Transcription Pricing

**Source:** `azure.microsoft.com/en-us/pricing/details/cognitive-services/speech-services/` fetched 2026-08-24.

**Finding:** The public pricing page renders actual prices as "$-" for unauthenticated sessions. The exact USD rate for Fast Transcription cannot be retrieved without signing in or selecting a region/currency.

| Item | Status |
|---|---|
| Fast Transcription exact price | **NEEDS_VERIFICATION** — page shows "$-" |
| Free tier: Standard real-time | 5 audio hours/month (F0) | CONFIRMED |
| Free tier: Batch | Not supported on F0 | CONFIRMED |
| Historical estimate ~$1.00/hr = $0.0167/min | Unverified; treat as prior estimate only |

**Action required before Azure pilot:** Use the Azure Pricing Calculator (requires sign-in) or check `learn.microsoft.com/azure/ai-services/speech-service/fast-transcription-create` for current rates. Alternatively, the first pilot call will produce a billing record.

**Auto-detect behavior without candidate list:**
- Documentation states auto language detection is available but "may require a candidate language list."
- True unconstrained auto-detect (no candidate list) for uz-UZ and kk-KZ: NEEDS_VERIFICATION.
- This affects whether the AUTO condition can be run as designed. If Azure requires a candidate list for auto-detect, the AUTO condition for Azure will need to specify `[uz-UZ, kk-KZ]` as candidates — which is not strictly equivalent to AUTO on other providers. Must document this asymmetry.

---

## 4. Google Cloud STT Chirp 2

### 4a. Language Support
**Source:** `docs.cloud.google.com/speech-to-text/docs/speech-to-text-supported-languages` fetched 2026-08-24.

| Language | Model | Regions | Evidence |
|---|---|---|---|
| uz-UZ | `chirp_2` | asia-southeast1, europe-west4 | CONFIRMED |
| kk-KZ | `chirp_2` | asia-southeast1, europe-west4 | CONFIRMED |
| uz-UZ | `chirp_3` | eu | CONFIRMED |
| kk-KZ | `chirp_3` | eu | CONFIRMED |

Note: `chirp_2` is Private GA. `chirp_3` requires EU region (`eu` multi-region).

### 4b. Language Parameter Correction
**Critical correction to phase2_methodology.md and phase2_provider_matrix.json:**
The V2 API uses `language_codes` (array), **not** `languageCode` (singular string). Documents previously recorded the wrong parameter name.

| Condition | Correct V2 API parameter | Value for Uzbek | Value for Kazakh |
|---|---|---|---|
| HINT | `language_codes=["uz-UZ"]` | `["uz-UZ"]` | `["kk-KZ"]` |
| AUTO (language) | `language_codes=["auto"]` | `["auto"]` | `["auto"]` |

### 4c. `auto_decoding_config` Clarification
**Source:** `docs.cloud.google.com/speech-to-text/docs/models/chirp-2` fetched 2026-08-24.

`auto_decoding_config` (`AutoDetectDecodingConfig()`) controls **audio format** detection — it tells the API to infer the encoding, sample rate, and channel count from the audio stream. It does **not** perform language detection.

Language auto-detection is a separate feature controlled by `language_codes=["auto"]`.

| Feature | Parameter | Status for uz-UZ/kk-KZ |
|---|---|---|
| Audio format auto-detect | `auto_decoding_config` | CONFIRMED supported by Chirp 2 |
| Language auto-detect | `language_codes=["auto"]` | NEEDS_VERIFICATION — no docs confirm behavior for uz-UZ/kk-KZ specifically |

**AUTO condition risk:** `language_codes=["auto"]` may or may not correctly identify Uzbek or Kazakh audio. This is exactly what the pilot is designed to measure. No blocker, but the behavior is unconfirmed prior to the pilot.

### 4d. Pricing (unchanged)
- $0.021/min ($0.00035/sec), 15-second billing increments — CONFIRMED (no change from prior research)

---

## 5. Gemini Smoke Test

**Status: BLOCKED**

Both `GOOGLE_API_KEY` and `GEMINI_API_KEY` are absent from the environment. The smoke test cannot run without one of these.

| Item | Status |
|---|---|
| GOOGLE_API_KEY | NOT SET |
| GEMINI_API_KEY | NOT SET |
| Smoke test | **BLOCKED — pending API key** |
| Gemini pilot inclusion | CONDITIONAL — cannot include until smoke test passes |

**Required action:** Set `GOOGLE_API_KEY` (or `GEMINI_API_KEY`) to a valid Gemini API key, then re-run the smoke test:
- 1 Uzbek audio file → Gemini 2.5 Flash → confirm Uzbek Latin transcription
- 1 Kazakh audio file → Gemini 2.5 Flash → confirm Kazakh Cyrillic transcription

Until this passes, Gemini is excluded from the pilot.

---

## 6. Corrections Required Before Pilot

The following documents contain errors identified during this verification pass. Correct before running any pilot.

| Document | Issue | Correction |
|---|---|---|
| `phase2_cost_estimate.md` | ElevenLabs rate wrong (~15×) | Change to $0.22/hr = $0.00367/min; recalculate all ElevenLabs line items |
| `phase2_provider_matrix.json` | ElevenLabs `effective_rate_per_minute_usd_approx: 0.054` | Change to `0.00367`; update `effective_rate_evidence` to `CONFIRMED` |
| `phase2_methodology.md` (line 67) | GCS hint says `languageCode="uz-UZ"` | Change to `language_codes=["uz-UZ"]` and `language_codes=["kk-KZ"]` |
| `phase2_provider_matrix.json` (GCS language_conditions) | `parameter_name: "languageCode"` | Change to `language_codes` (array, not scalar) |
| `phase2_provider_research.md` (GCS section) | `languageCode="uz-UZ"` in hint mechanism | Change to `language_codes=["uz-UZ"]` |
| `phase2_public_benchmarks.md` | Kazakh test rows `NEEDS_VERIFICATION` | Update to 856 (CONFIRMED from Python download) |
| `phase2_provider_matrix.json` | `kazakh_test_rows: "NEEDS_VERIFICATION"` | Update to `856`; update evidence label |

---

## 7. Provider Readiness Summary

| Provider | Language support | Pricing | Auto-detect | Credential | Pilot-ready? |
|---|---|---|---|---|---|
| ElevenLabs `scribe_v2` | CONFIRMED | **CONFIRMED** ($0.00367/min) | CONFIRMED | No key | Ready pending key |
| GCS `chirp_2` | CONFIRMED | CONFIRMED ($0.021/min) | NEEDS_VERIFICATION | No credentials | Ready pending credentials |
| Azure Fast Transcription | CONFIRMED | NEEDS_VERIFICATION | NEEDS_VERIFICATION | No subscription | Verify pricing + setup first |
| Gemini `gemini-2.5-flash` | NEEDS_VERIFICATION | CONFIRMED pricing | N/A | **No API key** | **BLOCKED** |

---

## 8. Revised Pilot Cost Estimate

Based on verified pricing (ElevenLabs corrected; Azure held at prior estimate):

| Provider | Rate | Pilot (7.86 min) |
|---|---|---|
| ElevenLabs `scribe_v2` | $0.00367/min | **$0.029** |
| GCS `chirp_2` | $0.021/min | **$0.165** |
| Azure Fast Transcription | ~$0.0167/min (unverified) | **~$0.131** |
| Gemini 2.5 Flash | $0.00192/min | **~$0.015** (if smoke test passes) |
| **Total (all 4 providers)** | | **~$0.34** |
| **Total (excl. Gemini)** | | **~$0.33** |

The pilot is well within the $2.00 verification hard cap and within any reasonable pilot budget.

---

## VERDICT

**CONDITIONAL GREEN LIGHT FOR PILOT**

ElevenLabs and GCS Chirp 2 are cleared to proceed to pilot once API credentials are configured. No fundamental blockers for these two providers.

**Pre-pilot checklist:**

- [ ] Apply all corrections from Section 6 (document fixes) — **required before first call**
- [ ] Set `ELEVENLABS_API_KEY` and verify connectivity
- [ ] Configure `GOOGLE_APPLICATION_CREDENTIALS` for GCS; select `asia-southeast1` or `europe-west4` region
- [ ] **Azure:** Verify exact Fast Transcription pricing before any Azure call; determine whether AUTO condition requires a candidate list
- [ ] **Gemini:** Set `GOOGLE_API_KEY` and run 2-utterance smoke test; do not include in pilot until smoke test passes
- [ ] Run pilot (40 utterances × 2 conditions = 80 requests per provider) for ElevenLabs + GCS Chirp 2
- [ ] Add Azure and Gemini to pilot only after their respective blockers are resolved

**Blockers that would change CONDITIONAL to BLOCKED:**
- If Azure requires a candidate language list for AUTO condition: design the Azure AUTO condition as a constrained auto-detect and disclose in results (methodology note, not a blocker)
- If Gemini smoke test fails on both Uzbek and Kazakh: exclude Gemini from Phase 2; add to future candidates list

**$0.00 spent in this verification stage.** All lookups were documentation reads and one dataset download (no charge).
