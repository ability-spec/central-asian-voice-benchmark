# Benchmark Visualization System

Publication-quality figures for the Central Asian Voice Benchmark,
generated **directly from the frozen benchmark results**.

## Scope & integrity

- Reads only `results/phase2_full/phase2_trackb_results.jsonl` (2,400 records)
  and `results/phase3a/phase3a_trackb_results.jsonl` (468 records).
- No benchmark methodology, frozen results, or statistical tests are modified.
- No network access, no API calls.
- Every displayed number is computed at figure-generation time from the JSONL.
- `verify_against_report.py` cross-checks 41 recomputed values (including
  Wilcoxon p-values via the same manual formulation) against the frozen
  final report (`research/final_benchmark_report.md`).

## Reproduce

```bash
cd research/visualizations
uv venv .venv                      # once
uv pip install --python .venv/Scripts/python.exe matplotlib numpy
.venv/Scripts/python.exe verify_against_report.py   # 41/41 checks must pass
.venv/Scripts/python.exe make_figures.py            # writes figures/
```

## Figures

| File | Communicates |
|---|---|
| `01_flagship_uzbek_detection_failure` | **Flagship.** Uzbek AUTO detection 27% vs Kazakh 99%, and the +100% relative WER cost of Uzbek misdetection. |
| `02_detection_outcomes_by_language` | Detection accuracy per target language; what Uzbek is mistaken for (Turkish, English, Russian...). |
| `03_auto_vs_hint_paired` | SECONDARY AUTO vs HINT analysis with paired per-utterance lines and difference distribution. Explicitly annotated as non-significant (all p > 0.05, CIs include zero). |
| `04_r1_routing_primary` | PRIMARY R1 routing test: routed ≈ always-HINT; success criterion (mean(d) ≤ −0.030 AND p < 0.05) NOT MET. Presented as a null result. |
| `05_phase2_provider_comparison` | Phase 2 descriptive provider comparison (ElevenLabs Scribe v2 vs GCS Chirp 2), WER + latency. |
| `06_research_design_overview` | Research design story: Phase 2 → detection analysis → routing test; pilot-study scope disclaimer. |
| `07_phase2_accuracy_vs_latency` | WER vs mean latency for Phase 2 cells only (same corpus). No efficiency score derived. |

## Semantic color system (consistent across all figures)

- **AUTO** — steel blue `#3E6D9C`
- **HINT** — amber `#D9822B`
- **ROUTED (R1)** — green `#4F8A5B`
- **Uzbek** — red accent `#B0413E` · **Kazakh** — teal `#2E7D6B`

Each figure is written as PNG (Kaggle/web), SVG and PDF (publication).
