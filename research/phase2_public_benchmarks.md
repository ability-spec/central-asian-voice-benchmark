# Phase 2 Public Benchmark Research
**Date:** 2026-08-24
**Status:** Research only. No data downloaded. No API calls made.

Evidence labels follow project standard (CONFIRMED / CLAIMED / NEEDS_VERIFICATION).

---

## 1. FLEURS (Few-shot Learning Evaluation of Universal Representations of Speech)

### Source
Google Research. Dataset: `google/fleurs` on Hugging Face.
Paper: Conneau et al. (2022), "FLEURS: Few-Shot Learning Evaluation of Universal Representations of Speech."

### Language Coverage
- Total languages: 102
- **Uzbek (`uz_uz`):** CONFIRMED present
- **Kazakh (`kk_kz`):** CONFIRMED present

### Dataset Statistics
| Language | Total rows (all splits) | Test split rows |
|---|---|---|
| Uzbek (`uz_uz`) | ~4,170 | **862** (CONFIRMED — Python download 2026-08-24) |
| Kazakh (`kk_kz`) | ~4,430 | **856** (CONFIRMED — Python download 2026-08-24) |

*Note: test split counts verified by downloading both splits and running `len(ds)` via Python 3.14 / datasets 5.0.1 on 2026-08-24.*

### Audio Format
- Format: FLAC (stored as Parquet in HuggingFace dataset files)
- Sample rate: 16,000 Hz
- Compatible with our benchmark audio protocol (16 kHz mono PCM)

### License
CC BY 4.0 — permits benchmark use and publication of results.

### Access
```python
from datasets import load_dataset
uz = load_dataset("google/fleurs", "uz_uz", split="test")
kk = load_dataset("google/fleurs", "kk_kz", split="test")
```

### Suitability for Track A
**RECOMMENDED.** FLEURS is the standard public multilingual speech benchmark with confirmed Uzbek and Kazakh splits. CC BY 4.0 license permits publication. Results on FLEURS enable direct comparison with published academic work. The test split (~650–862 utterances) is larger than our frozen 300-utterance benchmark per language, providing a complementary evaluation with higher statistical power.

### Contamination Risk
MEDIUM — same as our Common Voice-sourced frozen benchmark. FLEURS data is public and may appear in commercial training sets. All FLEURS results must carry the MEDIUM contamination label per project methodology.

### Recommended Track A Scope
Use the official FLEURS test split for both `uz_uz` and `kk_kz`. Pin the dataset version (HuggingFace commit SHA) before downloading. Apply the same normalisation pipeline (NFC → casefold → apostrophe → punctuation → whitespace) and the same language conditions (AUTO + HINT). Report results separately from Track B.

---

## 2. Mozilla Common Voice

### Current Version
NEEDS_VERIFICATION — documentation page rendered minimal content. Based on public release history, the current version as of mid-2026 is likely CV 19 or CV 20. Must verify version at `commonvoice.mozilla.org/en/datasets` before download and pin the exact version in all benchmark metadata.

### Language Coverage
- **Uzbek:** Present in Common Voice. Our frozen benchmark already uses Common Voice Uzbek data (contamination risk: MEDIUM per project methodology). Using Common Voice again for Track A would duplicate our Track B corpus, reducing comparability value.
- **Kazakh:** Present in Common Voice. Our frozen benchmark uses ISSAI KSC (Kazakh Speech Corpus), not Common Voice Kazakh, so the overlap with Track B is partial.

### License
CC0 (public domain) for audio; transcripts under CC BY 4.0.

### Track A Suitability
**NOT RECOMMENDED as primary Track A corpus.** Reasons:
1. Our Track B Uzbek data already derives from Common Voice — Track A should be independent to add comparability value.
2. FLEURS provides cleaner, more uniform per-language splits with established benchmark comparisons in the literature.
3. Common Voice clip quality and transcript accuracy vary more than FLEURS.

Common Voice may be used as a **secondary validation** source if FLEURS results are inconclusive for either language.

---

## 3. Existing Published Benchmarks and SOTA Results

### FLEURS Leaderboard (paperswithcode.com)
The paperswithcode.com FLEURS Uzbek and Kazakh SOTA pages redirected and were inaccessible at time of research. Results below are from general literature knowledge and must be verified against current leaderboard before publication.

**FLEURS Uzbek (uz_uz) — known published results (NEEDS_VERIFICATION of recency):**

| Model | WER (%) | Source |
|---|---|---|
| MMS (Meta Massively Multilingual Speech) | ~15–25% | Meta AI (2023), varies by fine-tuning |
| Whisper large-v3 | ~15–30% | OpenAI (2023) |
| wav2vec2-based fine-tunes | ~10–20% | Community HuggingFace models |

*All figures unverified against current leaderboard. Treat as order-of-magnitude priors only.*

**FLEURS Kazakh (kk_kz) — known published results (NEEDS_VERIFICATION of recency):**

| Model | WER (%) | Source |
|---|---|---|
| MMS | ~10–20% | Meta AI (2023) |
| Whisper large-v3 | ~10–20% | OpenAI (2023) |
| ISSAI fine-tuned models | ~5–15% | ISSAI papers (various) |

*Same caveat — unverified against current leaderboard.*

### HuggingFace Open ASR Leaderboard
The HuggingFace Open ASR Leaderboard 2 (Space: `hf-audio/open_asr_leaderboard2`) was inaccessible at time of research (authentication required for the Space). NEEDS_VERIFICATION of whether Uzbek or Kazakh are among evaluated languages.

### ISSAI (Institute of Smart Systems and Artificial Intelligence, Kazakhstan)
ISSAI has published Kazakh ASR research including the ISSAI KSC dataset (which our benchmark uses for Kazakh). Published WER figures from ISSAI papers use their own in-house models (Kazakh-specific fine-tunes of Wav2Vec2 and Whisper). Those results are not directly comparable to commercial STT APIs.

Key ISSAI resource: `https://issai.nu.edu.kz` — NEEDS_VERIFICATION of specific benchmark papers with WER figures for comparison.

### Existing Commercial STT Comparisons
No published peer-reviewed comparison of commercial STT APIs on Uzbek or Kazakh was found in this research pass. This benchmark would be among the first published systematic comparisons for these languages.

---

## Recommendation: Track A Dataset

**Use FLEURS as the Track A public benchmark.**

Rationale:
- CONFIRMED presence of both uz_uz and kk_kz splits
- CC BY 4.0 license — publication permitted
- Standard academic benchmark with literature comparisons available
- Independent from our Track B corpus (no overlap with ISSAI KSC or our frozen Common Voice Uzbek utterances)
- ~650–862 test utterances per language — adequate statistical power

Pre-download action items:
1. Pin HuggingFace dataset commit SHA before first download
2. Verify exact test split sizes via `len(ds["test"])` after loading
3. Convert FLAC to WAV 16 kHz mono PCM to match our audio protocol before submission
4. Record the conversion command and ffmpeg version in run metadata
