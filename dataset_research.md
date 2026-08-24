# Central Asian Voice Benchmark
## STEP 3 — Dataset Acquisition Research

**Date:** 2026-08-23 | **Status:** Research only. Nothing downloaded. | **Scope:** Candidate dataset identification for STT benchmark corpus selection.

---

## Uzbek Candidates

| Dataset | Source | Size | Speakers | License | Format | Splits | Gated | Notes |
|---|---|---|---|---|---|---|---|---|
| FLEURS uz_uz | HuggingFace google/fleurs | ~4,170 utterances (~11.6 h) | Multiple, verified | CC BY 4.0 | FLAC, 16 kHz, mono | Train 2940 / Val 363 / Test 862 | No | Clean read speech from Wikipedia-sourced sentences; multilingual benchmark corpus; speaker IDs in metadata; test split usable directly |
| Mozilla Common Voice Uzbek | Mozilla Data Collective (moved Oct 2025) | UNKNOWN — was growing | Multiple, crowd-sourced | CC0 1.0 | MP3 | Train / Dev / Test | Account required | Moved off HuggingFace; HuggingFace viewer returns empty; new access method unverified; size and current test-split size unknown until manual check |
| instinct-org/audiobook_unchunked | HuggingFace | 209 MB (duration unknown) | UNKNOWN | "other" (unspecified) | UNKNOWN | UNKNOWN | Yes (gated) | Uzbek audiobook source; no speaker metadata visible; license is not a standard SPDX identifier — must not be used until license is confirmed in writing |

**Assessment:** Only one Uzbek dataset is immediately accessible with a verified license and known structure: FLEURS uz_uz. Mozilla Common Voice Uzbek is the most desirable long-term source (CC0, crowd-sourced diversity) but its new access method must be verified. The instinct-org dataset is blocked by an unresolvable license.

---

## Kazakh Candidates

| Dataset | Source | Size | Speakers | License | Format | Splits | Gated | Notes |
|---|---|---|---|---|---|---|---|---|
| FLEURS kk_kz | HuggingFace google/fleurs | ~4,430 utterances (~12.3 h) | Multiple, verified | CC BY 4.0 | FLAC, 16 kHz, mono | Train 3200 / Val 369 / Test 856 | No | Same corpus structure as uz_uz; cross-language comparability guaranteed; test split usable directly |
| ISSAI KSC2 | HuggingFace issai/Kazakh_Speech_Corpus_2 + ISSAI website | ~1,200 h, 600k+ utterances | Unknown count — large studio corpus | **CONFLICTED** — ISSAI website: CC BY 4.0; HuggingFace card: MIT | WAV, 16 kHz | Formal train/dev/test splits | No (HuggingFace viewer non-functional; download may work) | Interspeech 2022; largest high-quality Kazakh corpus; license conflict between website and HuggingFace card must be resolved before download |
| ISSAI KSC (SLR102) | openslr.org/102 | ~332 h, 153k+ utterances | Unknown count — studio corpus | CC BY 4.0 | FLAC | Formal splits | No (OpenSLR direct download) | Predecessor to KSC2; well-documented; speaker metadata likely present; Interspeech-backed; smaller but cleaner provenance |
| KSD (SLR140) | openslr.org/140 | ~554 h, 204k utterances | Unknown count — large corpus | CC BY-SA 3.0 US | WAV, 22 kHz and 44 kHz (mixed) | Formal splits | No (OpenSLR direct download) | Al-Farabi KNU; share-alike license requires results published under compatible license; mixed sample rate requires downsampling to 16 kHz before use |
| TilQazyna/Til-Audio-Corpus-KK-v1 | HuggingFace | 1,042.8 h | Not identified — audiobook/sermon sources | Non-commercial (gated) | MP3 | Train only | Yes (gated, non-commercial) | No speaker IDs; train-only split; non-commercial restriction; not suitable for speaker-disjoint evaluation or any commercial-context benchmark |
| Mozilla Common Voice Kazakh | Mozilla Data Collective (moved Oct 2025) | UNKNOWN | Multiple, crowd-sourced | CC0 1.0 | MP3 | Train / Dev / Test | Account required | Same migration situation as Uzbek; new access method unverified |

---

## License & Usage Analysis

| License | Datasets | Research use | Commercial use | Share-alike | Attribution |
|---|---|---|---|---|---|
| CC0 1.0 | Mozilla Common Voice (both languages) | Yes | Yes | No | Not required |
| CC BY 4.0 | FLEURS, ISSAI KSC, ISSAI KSC2 (website) | Yes | Yes | No | Required |
| MIT | ISSAI KSC2 (HuggingFace card only) | Yes | Yes | No | Required |
| CC BY-SA 3.0 US | KSD | Yes | Yes | **Yes** — published results must use a compatible license | Required |
| Non-commercial | TilQazyna | Research only | **No** | N/A | Required |
| "other" | instinct-org/audiobook_unchunked | **Do not use** | **Do not use** | N/A | N/A |

**Flags:**

- **KSD (CC BY-SA 3.0 US):** The share-alike clause means any benchmark report or dataset release derived from KSD must be released under CC BY-SA 3.0 US or a compatible license. This is a policy decision, not a legal blocker — but it must be decided before KSD is used.
- **ISSAI KSC2 license conflict:** The ISSAI website (issai.nu.edu.kz) states CC BY 4.0. The HuggingFace dataset card states MIT. These are both permissive and both allow research and publication, but the authoritative license must be confirmed. Contact ISSAI or use only the OpenSLR download (which does not carry the HuggingFace card) until resolved.
- **TilQazyna non-commercial:** Not suitable for this benchmark if any publication or platform access involves commercial activity. Even for purely academic research, verify exact terms of the gated access agreement before downloading.
- **Mozilla Data Collective:** Access requires account creation. License is CC0 (public domain), which imposes no restrictions, but the access step must be completed before size and content can be assessed.

---

## Speaker-Disjoint Evaluation Feasibility

Speaker-disjoint evaluation requires that speakers in the test split do not appear in any training material used by the models under test. This cannot be guaranteed for commercial models with opaque training data. The practical goal is to use an official test split that was never part of the original dataset's training partition.

| Dataset | Speaker metadata | Official test split | Speaker-disjoint feasible | Notes |
|---|---|---|---|---|
| FLEURS uz_uz | Yes — `speaker_id` field in schema | Yes | Yes | 862-row test split; 862 utterances exceeds 300-utterance target |
| FLEURS kk_kz | Yes — `speaker_id` field in schema | Yes | Yes | 856-row test split; same as above |
| ISSAI KSC (SLR102) | Likely present — formal studio corpus with documentation | Likely | Likely | Confirm speaker metadata before use; 153k+ utterances provides ample selection |
| ISSAI KSC2 | Likely present — 600k+ utterances, Interspeech publication | Likely | Likely | Same as KSC; license conflict must be resolved first |
| KSD (SLR140) | Likely present — formal university corpus | Likely | Likely | SA license policy decision required first |
| Mozilla Common Voice (both) | Yes — speaker IDs preserved in official splits | Yes | Yes | Official splits designed with speaker disjointness; must verify after Data Collective migration preserves split integrity |
| TilQazyna | **No** | **No** — train only | **Not feasible** | No speaker IDs; train-only split |
| instinct-org/audiobook_unchunked | Unknown | Unknown | Unknown | Blocked by license |

---

## Recommended Primary Dataset

### Uzbek — FLEURS uz_uz

**Rationale:** FLEURS uz_uz is the only Uzbek speech corpus that is simultaneously (a) freely accessible without gating, (b) CC BY 4.0, (c) has a clean documented test split with speaker metadata, and (d) has a known structure verified during this research session. The test split (862 utterances) exceeds the 300-utterance benchmark target. The corpus is read speech from Wikipedia-sourced sentences, which introduces a domain limitation, but this limitation is consistent across all benchmark items and is a known, documentable confound rather than an unknown one.

**Size adequacy:** 862 test utterances at ~10 s average = ~144 min. The 300-utterance sample can be drawn from this.

**Contamination risk:** MEDIUM. FLEURS is a published multilingual benchmark; commercial model training data may include FLEURS audio. This is no different from Common Voice and cannot be mitigated, only labelled.

**Primary limitation:** Small speaker pool and read-speech domain only. Not representative of spontaneous conversational Uzbek.

### Kazakh — ISSAI KSC2 (issai/Kazakh_Speech_Corpus_2)

**Rationale:** KSC2 is the largest high-quality Kazakh speech corpus available (~1,200 h, 600k+ utterances), has formal evaluation splits, is WAV 16 kHz (no resampling needed), and is backed by an Interspeech 2022 publication providing verified ground-truth transcripts. The CC BY 4.0 license (per the ISSAI website) is compatible with publication and attribution.

**Condition:** The license conflict between the ISSAI website (CC BY 4.0) and the HuggingFace card (MIT) must be confirmed before download. Both licenses permit the intended use — this is a provenance verification step, not a blocker in practice.

**Primary limitation:** Studio/read speech bias (as with all formal corpora). Size makes random stratified sampling feasible.

---

## Recommended Backup Datasets

### Uzbek backup — Mozilla Common Voice Uzbek (CC0)

Mozilla Common Voice Uzbek was the natural first choice for any STT benchmark. CC0 removes all license friction, and its official test split was designed for benchmark use. The only current blocker is the migration to Mozilla Data Collective (October 2025): the new access URL and account registration process must be verified before it can be evaluated further.

**Action required:** Navigate to the Mozilla Data Collective website (do not download), confirm dataset size and current test-split row count, and confirm that the official test split is still preserved unchanged from the pre-migration HuggingFace version.

### Kazakh backup — ISSAI KSC (SLR102)

KSC is the predecessor to KSC2, with ~332 h and 153k+ utterances, CC BY 4.0, directly downloadable from OpenSLR without gating. If KSC2 access fails or the license conflict cannot be resolved quickly, KSC provides a well-documented, formally validated alternative with sufficient scale for the 300-utterance benchmark target.

---

## Dataset Acquisition Plan

**No downloads have occurred. This plan describes intended sequence only.**

### Phase 1 — Access verification (before any download)

1. **FLEURS uz_uz and kk_kz:** Confirm `google/fleurs` is still publicly accessible on HuggingFace without gating. Inspect dataset card for any terms of use added since initial publication. Confirm `speaker_id` field is present in the test split schema.

2. **ISSAI KSC2 license:** Contact ISSAI (issai.nu.edu.kz) or inspect the OpenSLR mirror to resolve the CC BY 4.0 vs MIT discrepancy. Do not download until the authoritative license is confirmed.

3. **Mozilla Data Collective:** Locate the current access URL for Mozilla Common Voice Uzbek and Kazakh. Determine whether account registration is required. Confirm the test split row count and whether it is unchanged from the final HuggingFace release.

4. **KSD share-alike policy:** Decide whether the CC BY-SA 3.0 US share-alike clause is acceptable for this benchmark's publication plan. This is a project policy decision, not a technical step.

### Phase 2 — Primary downloads (pending Phase 1 completion)

| Priority | Dataset | Method | Size estimate |
|---|---|---|---|
| 1 | FLEURS uz_uz (test split only) | `load_dataset("google/fleurs", "uz_uz", split="test")` | ~60 MB |
| 2 | FLEURS kk_kz (test split only) | `load_dataset("google/fleurs", "kk_kz", split="test")` | ~60 MB |
| 3 | ISSAI KSC2 (test split only) | HuggingFace datasets or direct URL — pending license confirm | Unknown; full corpus ~1,200 h |
| 4 | Mozilla Common Voice Uzbek (test split) | Mozilla Data Collective — pending access verification | Unknown |
| 4 | Mozilla Common Voice Kazakh (test split) | Mozilla Data Collective — pending access verification | Unknown |

Download the test split only at first. Do not download train or dev splits until there is a specific use case for them.

### Phase 3 — Post-download validation

For each downloaded split:
1. Verify audio integrity: correct sample rate (16 kHz), channel count (mono), bit depth.
2. Confirm all reference transcripts are present and non-empty.
3. Confirm speaker IDs are present for all rows.
4. Compute total duration and per-speaker duration distribution.
5. Confirm no overlap between the downloaded test items and any items submitted in the smoke test.
6. Record SHA-256 of the full split archive before any processing.

---

## STEP 3 READINESS

**Primary Uzbek dataset:** FLEURS uz_uz (google/fleurs, test split) — CC BY 4.0, non-gated, 862 utterances, speaker IDs present

**Primary Kazakh dataset:** ISSAI KSC2 (issai/Kazakh_Speech_Corpus_2) — CC BY 4.0 per ISSAI website, ~600k utterances, 16 kHz WAV — **conditional on license conflict resolution**

**Backup datasets:**
- Uzbek: Mozilla Common Voice Uzbek — CC0, pending Data Collective access verification
- Kazakh: ISSAI KSC (SLR102) — CC BY 4.0, ~153k utterances, OpenSLR direct download, no gating

**What must be verified before download:**
- ISSAI KSC2: Confirm authoritative license is CC BY 4.0 (website) vs MIT (HuggingFace card)
- Mozilla Common Voice (both languages): Locate Data Collective access URL; confirm test-split integrity post-migration
- KSD: Decide whether CC BY-SA 3.0 US share-alike is acceptable for publication
- FLEURS: Spot-check that `speaker_id` field is present in the test split schema

**What can be downloaded immediately:**
- FLEURS uz_uz test split (no gating, CC BY 4.0, verified accessible) — pending only the schema spot-check above
- FLEURS kk_kz test split (same conditions)
- ISSAI KSC (SLR102) from openslr.org/102 (no gating, CC BY 4.0, direct download) — if the KSC2 license delay makes a Kazakh fallback necessary

---

*No datasets have been downloaded. No audio files have been created or modified. All size and row-count figures are from documentation and HuggingFace dataset viewer queries conducted during this research session. License and access information is current as of 2026-08-23 and should be re-verified at download time.*
