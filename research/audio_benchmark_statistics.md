# Audio Benchmark Set — Statistics

**Date:** 2026-08-23
**Master manifest:** `research/audio_benchmark_manifest.csv`
**Manifest SHA-256:** `d01408af2e04d048a44600138ac878f97b2a2372f62b9a42f2f7d0b161f34924`
**Status:** Frozen audio set. No STT calls made.

---

## File Counts

| Language | Files | Directory |
|---|---|---|
| Uzbek | 300 | `benchmark_audio/uzbek/` |
| Kazakh | 300 | `benchmark_audio/kazakh/` |
| **Total** | **600** | — |

---

## Audio Specification

| Parameter | Value |
|---|---|
| Sample rate | 16,000 Hz |
| Channels | 1 (mono) |
| Bit depth | 16-bit PCM |
| Format | WAV (PCM) |
| Encoding | Linear PCM (uncompressed) |

All files verified: sample rate, channel count, bit depth, non-zero duration.

---

## Duration Statistics

| Metric | Uzbek | Kazakh | Combined |
|---|---|---|---|
| Total duration | 21m 47s (1307.8s) | 37m 13s (2233.6s) | 59m 01s (3541.4s) |
| Mean per utterance | 4.36s | 7.45s | 5.90s |
| Median per utterance | 3.87s | 6.83s | 5.29s |
| Shortest utterance | 0.70s | 1.56s | 0.70s |
| Longest utterance | 10.35s | 23.72s | 23.72s |
| Utterance count | 300 | 300 | 600 |

---

## Source Datasets

| Language | Source | Format | License |
|---|---|---|---|
| Uzbek | ISSAI USC v1 via `murodbek/uzbek-speech-corpus` (HuggingFace) | Embedded WAV → 16kHz mono WAV | CC BY 4.0 |
| Kazakh | ISSAI KSC v1.1 — OpenSLR SLR102 | FLAC → 16kHz mono WAV | CC BY 4.0 |

---

## Conversion

All audio converted with ffmpeg 8.1.1:
```
ffmpeg -y -loglevel error -i <input> -ar 16000 -ac 1 -sample_fmt s16 <output.wav>
```

No pitch, speed, or spectral modifications were applied.
Resampling uses ffmpeg default (sinc interpolation).

---

## Verification Results

| Check | Result |
|---|---|
| Total files | **600** (target: 600) |
| Uzbek files | **300** (target: 300) |
| Kazakh files | **300** (target: 300) |
| Duplicate utterance IDs | **0** |
| Files with wrong sample rate | **0** |
| Files not mono | **0** |
| Files not 16-bit | **0** |
| Files with zero duration | **0** |
| Missing transcripts | **0** |
| Manifest SHA-256 | `d01408af2e04d048a44600138ac878f97b2a2372f62b9a42f2f7d0b161f34924` |

---

*No STT APIs have been called. No models have been run.*
*This is the frozen audio input set for the benchmark.*
