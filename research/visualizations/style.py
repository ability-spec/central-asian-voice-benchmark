"""Shared visual identity for the Central Asian Voice Benchmark figure system.

All colors are presentation-only. No benchmark numbers live in this file:
every displayed value is computed from frozen JSONL results by data.py.
"""

# ---- Semantic condition colors (used identically across all figures) ----
COLOR_AUTO = "#3E6D9C"      # muted steel blue
COLOR_HINT = "#D9822B"      # amber
COLOR_ROUTED = "#4F8A5B"    # green
COLOR_NEUTRAL = "#6B7280"   # grey for reference lines / non-benchmark elements

# ---- Language accents (used sparingly: headers, panel titles, markers) ----
COLOR_UZBEK = "#B0413E"
COLOR_KAZAKH = "#2E7D6B"

CONDITION_COLORS = {"AUTO": COLOR_AUTO, "HINT": COLOR_HINT, "ROUTED": COLOR_ROUTED}

TONE_TEXT = "#1F2430"
TONE_MUTED = "#5B6472"
TONE_GRID = "#D9DEE5"
TONE_BG = "#FFFFFF"

FONT_FAMILY = "DejaVu Sans"


def apply_style():
    import matplotlib as mpl

    mpl.rcParams.update({
        "font.family": FONT_FAMILY,
        "font.size": 10,
        "text.color": TONE_TEXT,
        "axes.edgecolor": TONE_MUTED,
        "axes.labelcolor": TONE_TEXT,
        "axes.titlesize": 12,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.color": TONE_GRID,
        "grid.linewidth": 0.6,
        "axes.axisbelow": True,
        "xtick.color": TONE_MUTED,
        "ytick.color": TONE_MUTED,
        "xtick.labelsize": 9.5,
        "ytick.labelsize": 9.5,
        "legend.frameon": False,
        "legend.fontsize": 9.5,
        "figure.facecolor": TONE_BG,
        "axes.facecolor": TONE_BG,
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
        "savefig.facecolor": TONE_BG,
    })


def save_all(fig, outdir, stem):
    """Save PNG (web/Kaggle) and SVG+PDF (publication) for one figure."""
    png = outdir / f"{stem}.png"
    svg = outdir / f"{stem}.svg"
    pdf = outdir / f"{stem}.pdf"
    fig.savefig(png)
    fig.savefig(svg)
    fig.savefig(pdf)
    return png, svg, pdf


def annotate_stat(ax, x, y, text, ha="center"):
    ax.annotate(text, (x, y), ha=ha, va="bottom", fontsize=8.5,
                color=TONE_MUTED, style="italic")
