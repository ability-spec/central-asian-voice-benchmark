"""
Splice the Kaggle notebook: replace old visualization cells (25-31) with the
publication figure gallery. Keeps all other cells intact.

Run from repo root:
  python research/kaggle/_splice_gallery.py
"""
import json, pathlib

NOTEBOOK = pathlib.Path("research/kaggle/central_asian_voice_benchmark.ipynb")

PUB_STEMS = [
    "00_benchmark_overview",
    "01_provider_comparison",
    "02_uzbek_vs_kazakh_detection",
    "03_auto_vs_hint",
    "04_routed_vs_hint",
    "05_cost_vs_wer",
    "06_latency_vs_wer",
    "07_error_analysis",
    "08_reproducibility",
]

TITLES = {
    "00_benchmark_overview": "1. Benchmark overview",
    "01_provider_comparison": "2. Model / provider comparison",
    "02_uzbek_vs_kazakh_detection": "3. Uzbek vs Kazakh language detection",
    "03_auto_vs_hint": "4. AUTO vs HINT (SECONDARY)",
    "04_routed_vs_hint": "5. ROUTED vs HINT (PRIMARY, null result)",
    "05_cost_vs_wer": "6. Cost vs WER",
    "06_latency_vs_wer": "7. Latency vs WER",
    "07_error_analysis": "8. Error analysis",
    "08_reproducibility": "9. Reproducibility / data integrity",
}


def md_cell(text: str):
    normalized = text.rstrip("\n")
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": [normalized],
    }


def code_cell(source_lines: list, execution_count=None):
    out = {
        "cell_type": "code",
        "metadata": {},
        "source": [ln + "\n" for ln in source_lines],
        "outputs": [],
        "execution_count": execution_count,
    }
    return out


# ---- New gallery markdown cell ----
GALLERY_MD = """\
## 11. Publication Figure Gallery

The figures below are the **publication-quality analysis gallery** for the Central Asian Voice Benchmark. They are generated directly from the frozen JSONL results and pre-rendered as high-resolution PNGs (200 DPI). Each figure is displayed inline so the notebook reads as a self-contained research report.

**Scientific-honesty labels used throughout:**
- **PRIMARY** — the pre-specified R1 routing hypothesis test (null result).
- **SECONDARY** — the AUTO vs HINT comparison (directionally favoured HINT; not significant).
- **Descriptive** — observational comparisons (provider, latency, cost) without inferential claims.
- **Diagnostic** — error analysis and apostrophe confound, not inferential.

All figures source the same two frozen files:
- `phase2_trackb_results.jsonl` (Phase 2, 2,400 records)
- `phase3a_trackb_results.jsonl` (Phase 3A, 468 records; 400 successful + 68 historical error records)

Figure source code and the verification gate live in `research/visualizations/`:
- `make_publication_figures.py`
- `verify_publication.py` (55/55 checks)
- `verify_against_report.py` (41/41 checks)
"""

# ---- New gallery code cell ----
GALLERY_CODE = [
    "# ---------------------------------------------------------------------------",
    "# Publication figure gallery — display pre-rendered high-resolution PNGs inline",
    "# ---------------------------------------------------------------------------",
    "# All figures are pre-generated from the frozen JSONL by",
    "#   research/visualizations/make_publication_figures.py",
    "# and verified by",
    "#   research/visualizations/verify_publication.py   (55/55)",
    "#   research/visualizations/verify_against_report.py (41/41)",
    "#",
    "# This cell does NOT regenerate figures and does NOT touch the frozen JSONL.",
    "# ---------------------------------------------------------------------------",
    "import pathlib",
    "",
    "PUB_STEMS = [",
    '    "00_benchmark_overview",',
    '    "01_provider_comparison",',
    '    "02_uzbek_vs_kazakh_detection",',
    '    "03_auto_vs_hint",',
    '    "04_routed_vs_hint",',
    '    "05_cost_vs_wer",',
    '    "06_latency_vs_wer",',
    '    "07_error_analysis",',
    '    "08_reproducibility",',
    "]",
    "",
    "TITLES = {",
    '    "00_benchmark_overview": "1. Benchmark overview",',
    '    "01_provider_comparison": "2. Model / provider comparison",',
    '    "02_uzbek_vs_kazakh_detection": "3. Uzbek vs Kazakh language detection",',
    '    "03_auto_vs_hint": "4. AUTO vs HINT (SECONDARY)",',
    '    "04_routed_vs_hint": "5. ROUTED vs HINT (PRIMARY, null result)",',
    '    "05_cost_vs_wer": "6. Cost vs WER",',
    '    "06_latency_vs_wer": "7. Latency vs WER",',
    '    "07_error_analysis": "8. Error analysis",',
    '    "08_reproducibility": "9. Reproducibility / data integrity",',
    "}",
    "",
    "def _resolve_pub_figures():",
    '    """Locate the pre-rendered publication PNGs.',
    "",
    "    Search order mirrors _find_data_file:",
    "      1. Kaggle: any PNG matching one of the 9 base stems under /kaggle/input/",
    "         (the dataset should include figures/publication/).",
    "      2. Local package / repo root: research/visualizations/figures/publication/",
    '         alongside the notebook (research/kaggle/ -> research/..).',
    '    """',
    '    driver = pathlib.Path("/kaggle/input")',
    "",
    "    # 1. Kaggle",
    "    if driver.exists():",
    "        out = {}",
    '        for p in sorted(driver.rglob("*.png")):',
    "            if p.stem in PUB_STEMS:",
    "                out[p.stem] = p",
    "                if len(out) == len(PUB_STEMS):",
    "                    break",
    "        return out",
    "",
    "    # 2. Local / repo root",
    '    here = pathlib.Path(".")',
    '    for base in [here, here.parent, (here / "..").resolve()]:',
    '        candidate = base / "research" / "visualizations" / "figures" / "publication"',
    "        if candidate.is_dir():",
    '            return {stem: candidate / f"{stem}.png" for stem in PUB_STEMS}',
    "",
    "    return {}",
    "",
    "",
    "fig_map = _resolve_pub_figures()",
    "",
    'print("=== PUBLICATION FIGURE GALLERY ===")',
    'print(f"Figures located: {len(fig_map)} / {len(PUB_STEMS)}")',
    'for stem in PUB_STEMS:',
    "    p = fig_map.get(stem)",
    '    status = str(p) if p and p.exists() else "MISSING"',
    '    print(f"  {stem:28s} -> {status}")',
    "",
    'if len(fig_map) < len(PUB_STEMS):',
    "    print()",
    '    print("WARNING: not all publication figures are present. Gaps will be shown in")',
    '    print("the gallery below. Re-build missing figures from")',
    '    print("  research/visualizations/make_publication_figures.py")',
    '    print("before publishing on Kaggle (figures must be in the attached dataset OR")',
    '    print("in research/visualizations/figures/publication/ beside the notebook).")',
    "",
    "# matplotlib inline backend for notebook image rendering.",
    "try:",
    "    import matplotlib",
    '    matplotlib.use("module://matplotlib_inline.backend_inline", force=True)',
    "except Exception:",
    "    pass",
    "",
    "# Display the gallery.",
    "for stem in PUB_STEMS:",
    "    p = fig_map.get(stem)",
    "    if p and p.exists():",
    "        print()",
    '        print(TITLES[stem], "-", p.name)',
    "        _disp(Image(filename=str(p), width=720))",
    "    else:",
    "        print()",
    '        print("**", TITLES[stem], "** - figure PNG not available.")',
]


def splice() -> dict:
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    cells = nb["cells"]
    assert len(cells) == 39, len(cells)

    # Verify boundaries before splicing
    assert "".join(cells[25]["source"]).strip().splitlines()[0] == "## 11. Visualizations", (
        "".join(cells[25]["source"])[:80]
    )
    assert "".join(cells[32]["source"]).strip().splitlines()[0] == "## 12. Combined Leaderboard (Phase 2 + Phase 3A)", (
        "".join(cells[32]["source"])[:80]
    )

    new_cells = [
        md_cell(GALLERY_MD),
        code_cell(GALLERY_CODE, execution_count=None),
    ]

    # keep cells[0:25], insert new, keep cells[32:]
    nb["cells"] = cells[:25] + new_cells + cells[32:]

    tmp = NOTEBOOK.with_suffix(".ipynb.tmp")
    tmp.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(NOTEBOOK)
    return nb


if __name__ == "__main__":
    nb = splice()
    print("spliced OK. new cell count:", len(nb["cells"]))
    print("cells 25..26 now:")
    for i in (25, 26):
        c = nb["cells"][i]
        head = "".join(c["source"]).strip().splitlines()[0]
        print(f"  [{i}] {c['cell_type']:8s} head={head[:80]!r}")
