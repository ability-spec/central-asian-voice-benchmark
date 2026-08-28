"""Reference-styled benchmark figures (light 'Google benchmark' aesthetic).

Every number is either:
  - computed at runtime from frozen JSONL via data.py, or
  - copied verbatim from the FROZEN final report (research/final_benchmark_report.md),
    marked with [report] below. Phase 1 numbers come from Appendix A/B of that
    report (no Phase 1 JSONL exists in results/).

Run:  .venv/Scripts/python.exe make_reference_figures.py
Outputs PNG (+SVG) into ../../reference pics/
"""

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.transforms as mtransforms
import numpy as np

import data
from style import apply_style

apply_style()
OUT = Path(__file__).resolve().parents[2] / "reference pics"
OUT.mkdir(exist_ok=True)

# ---- palette (reference aesthetic: light bg, saturated accents) ----
BG = "#F7F8FA"
CARD = "#FFFFFF"
TEXT = "#202124"
MUTED = "#5F6368"
GRID = "#E8EAED"

BLUE = "#1A73E8"
RED = "#D93025"
TEAL = "#188038"
AMBER = "#E94235"
GREY = "#9AA0A6"

C_AUTO = "#3E6D9C"
C_HINT = "#D9822B"
C_ROUTED = "#4F8A5B"
UZ_COL = "#B0413E"
KK_COL = "#2E7D6B"

SOURCE = ("Source: Central Asian Voice Benchmark — frozen Phase 1/2/3A results "
          "(final_benchmark_report.md, 2026-08-25) · central-asian-voice-benchmark")

# ---- frozen-report values [report: Appendix B, Section 7] ----
# (label, auto_wer, hint_wer, phase)
LEADERBOARD = [
    ("ElevenLabs Scribe v2", 0.0534, 0.0510, 0.3416, 0.2446, "Phase 2"),
    ("Google Cloud STT Chirp 2", 0.2666, 0.2112, 0.4227, 0.2602, "Phase 2"),
    ("GPT-4o-transcribe", 0.257, 0.227, 0.545, 0.316, "Phase 1*"),
    ("GPT-4o-mini-transcribe", 0.452, 0.359, 0.755, 0.492, "Phase 1*"),
    ("Whisper-1", 0.532, 0.495, 1.141, 1.150, "Phase 1*"),
]


def new_canvas(w=12.5, h=6.4):
    fig = plt.figure(figsize=(w, h), facecolor=BG)
    fig.patch.set_facecolor(BG)
    return fig


def header(fig, title, subtitle, x=0.065, ty=0.925, sy=0.862, tsize=21):
    fig.text(x, ty, title, fontsize=tsize, fontweight="bold", color=TEXT,
             ha="left", va="top")
    fig.text(x, sy, subtitle, fontsize=10.5, color=MUTED, ha="left", va="top")


def footer(fig, text=SOURCE, x=0.065):
    fig.text(x, 0.022, text, fontsize=8.2, color=MUTED, ha="left")


def strip_axes(ax):
    ax.set_facecolor(BG)
    for s in ("top", "right", "left", "bottom"):
        ax.spines[s].set_visible(False)
    ax.grid(False)
    ax.tick_params(colors=MUTED, length=0)


def save(fig, stem):
    fig.savefig(OUT / f"{stem}.png", dpi=200, facecolor=BG)
    fig.savefig(OUT / f"{stem}.svg", facecolor=BG)
    plt.close(fig)
    print("wrote", stem)


# =====================================================================
# 1 — MAIN LEADERBOARD
# =====================================================================

def fig_leaderboard():
    fig = new_canvas(12.5, 6.8)
    header(fig,
           "Speech-to-Text Leaderboard — Uzbek & Kazakh",
           "Mean word error rate (lower is better) · HINT = language supplied, AUTO = automatic detection · "
           "n = 300 utterances per language per phase")

    gs = fig.add_gridspec(1, 2, width_ratios=[1, 1], wspace=0.32,
                          left=0.185, right=0.965, top=0.74, bottom=0.13)
    panels = [
        ("Uzbek", 2, UZ_COL, "uz"),
        ("Kazakh", 1, KK_COL, "kk"),
    ]
    order = sorted(range(len(LEADERBOARD)), key=lambda i: LEADERBOARD[i][3])

    for col, (lang, aidx, lcol, code) in enumerate(panels):
        ax = fig.add_subplot(gs[0, col])
        strip_axes(ax)
        ax.set_title(lang, fontsize=14, fontweight="bold", color=lcol,
                     loc="left", pad=10)
        ys = np.arange(len(order))[::-1]
        for y, i in zip(ys, order):
            name, kauto, khint, uauto, uhint, phase = LEADERBOARD[i]
            auto, hint = (uauto, uhint) if code == "uz" else (kauto, khint)
            best = phase != "Phase 1*"
            ax.hlines(y, hint, auto, color=GRID, lw=2.5, zorder=1)
            ax.plot(auto, y, "o", ms=9 if best else 7, color=C_AUTO,
                    alpha=1.0 if best else 0.45, zorder=3)
            ax.plot(hint, y, "o", ms=9 if best else 7, color=C_HINT,
                    alpha=1.0 if best else 0.45, zorder=4)
            ax.text(-0.012, y, name + ("*" if best is False else ""),
                    ha="right", va="center", fontsize=10.5,
                    color=TEXT if best else MUTED,
                    fontweight="bold" if best else "normal",
                    transform=mtransforms.blended_transform_factory(
                        fig.transFigure, ax.transData))
            ax.text(max(auto, hint) + 0.045, y,
                    f"HINT {hint:.3f}   AUTO {auto:.3f}",
                    va="center", fontsize=8.6, color=MUTED)
        ax.set_yticks([])
        ax.set_xlim(0, 1.42)
        ax.set_ylim(-0.6, len(order) - 0.4)
        ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
        ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"])
        ax.set_xlabel("Mean WER" if col == 0 else "")

    fig.legend([plt.Line2D([], [], marker="o", ls="", color=C_HINT),
                plt.Line2D([], [], marker="o", ls="", color=C_AUTO)],
               ["HINT (language supplied)", "AUTO (auto-detect)"],
               loc="lower center", bbox_to_anchor=(0.5, 0.135), ncol=2,
               fontsize=9.5, frameon=False, handletextpad=0.3, columnspacing=1.4)

    fig.text(0.065, 0.038,
             "* Phase 1 models used a different, smaller corpus and are shown for context only — "
             "not directly comparable to Phase 2 WERs (frozen report, Appendix A).",
             fontsize=8.4, color=MUTED)
    footer(fig)
    save(fig, "1_leaderboard")


# =====================================================================
# 2 — AUTO vs HINT (Phase 3A paired analysis)
# =====================================================================

def fig_auto_vs_hint():
    conds = data.phase3a_conditions()
    fig = new_canvas(12.5, 6.2)
    header(fig,
           "AUTO vs HINT: the hint helps Uzbek directionally, not significantly",
           "ElevenLabs Scribe v2 · Phase 3A held-out evaluation split · 160 paired utterances "
           "(70 Uzbek, 90 Kazakh) · Wilcoxon signed-rank, one-tailed")

    gs = fig.add_gridspec(1, 2, width_ratios=[1.15, 1], wspace=0.30,
                          left=0.075, right=0.96, top=0.72, bottom=0.15)

    # Panel A: means with paired deltas
    ax = fig.add_subplot(gs[0, 0])
    strip_axes(ax)
    pops = [("overall", "Overall\n(n=160)", TEXT),
            ("uz", "Uzbek\n(n=70)", UZ_COL),
            ("kk", "Kazakh\n(n=90)", KK_COL)]
    w = 0.26
    for i, (pop, lbl, lcol) in enumerate(pops):
        c = conds[pop]
        ax.bar(i - w / 2 - 0.015, c["auto_mean"], width=w, color=C_AUTO, label="AUTO" if i == 0 else None)
        ax.bar(i + w / 2 + 0.015, c["hint_mean"], width=w, color=C_HINT, label="HINT" if i == 0 else None)
        ax.text(i - w / 2 - 0.015, c["auto_mean"] + 0.007, f"{c['auto_mean']:.3f}",
                ha="center", fontsize=9, color=MUTED)
        ax.text(i + w / 2 + 0.015, c["hint_mean"] + 0.007, f"{c['hint_mean']:.3f}",
                ha="center", fontsize=9, color=MUTED)
        d = c["d_auto_hint_mean"]
        ax.text(i, max(c["auto_mean"], c["hint_mean"]) + 0.035,
                f"Δ +{d:.3f}\np = {c['p_secondary']:.3f}",
                ha="center", fontsize=9.2, color=TEXT, fontweight="bold")
    ax.set_xticks(range(3))
    ax.set_xticklabels([l for _, l, _ in pops], fontsize=10.5)
    for tick, (_, _, lcol) in zip(ax.get_xticklabels(), pops):
        tick.set_color(lcol)
        tick.set_fontweight("bold")
    ax.set_ylabel("Mean WER")
    ax.set_ylim(0, 0.40)
    ax.set_title("Mean WER by condition", loc="left", fontsize=12)
    ax.legend(loc="upper right", fontsize=9.5, frameon=False)

    # Panel B: paired outcome counts + CI (report Section 10)
    ax2 = fig.add_subplot(gs[0, 1])
    strip_axes(ax2)
    cats = ["HINT better", "Tied", "AUTO better"]
    vals = [19, 130, 11]
    cols = [TEAL, GREY, AMBER]
    bars = ax2.barh(range(3)[::-1], vals, height=0.55, color=cols)
    for y, v in zip(range(3)[::-1], vals):
        ax2.text(v + 2, y, f"{v}  ({v / 160 * 100:.0f}%)", va="center",
                 fontsize=10.5, color=TEXT, fontweight="bold")
    ax2.set_yticks(range(3)[::-1])
    ax2.set_yticklabels(cats, fontsize=11)
    ax2.set_xlim(0, 165)
    ax2.set_xlabel("Paired utterances (n=160)")
    ax2.set_title("Per-utterance outcome, AUTO − HINT", loc="left", fontsize=12)
    ax2.text(0.98, 0.06,
             "overall mean Δ +0.0130 · bootstrap 95% CI [−0.008, 0.034]\n"
             "includes zero — no comparison reaches p < 0.05",
             transform=ax2.transAxes, ha="right", fontsize=8.6, color=MUTED,
             style="italic")

    fig.text(0.065, 0.058,
             "SECONDARY analysis. The descriptive Uzbek HINT advantage (−8.4% relative WER, p=0.103) "
             "should NOT be presented as a proven improvement; all CIs include zero.",
             fontsize=8.4, color=MUTED)
    footer(fig)
    save(fig, "2_auto_vs_hint")


# =====================================================================
# 3 — LANGUAGE DETECTION & ROUTING
# =====================================================================

def fig_detection_routing():
    det = data.detection_counts()
    conds = data.phase3a_conditions()
    dw = data.detection_wer_split()

    fig = new_canvas(12.5, 6.4)
    header(fig,
           "Language detection is the single point of failure for Uzbek",
           "ElevenLabs Scribe v2, AUTO condition · Phase 3A evaluation split · "
           "R1 routing = switch to HINT when detection is wrong")

    gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 1.15], wspace=0.30,
                          left=0.065, right=0.965, top=0.70, bottom=0.16)

    # Panel A: detection accuracy big numbers
    ax = fig.add_subplot(gs[0, 0])
    strip_axes(ax)
    ax.set_title("A · Detection accuracy (AUTO)", loc="left", fontsize=12)
    for y, (lang, col, n, corr) in enumerate([
            ("Uzbek", UZ_COL, det["uz"]["n"], det["uz"]["correct"]),
            ("Kazakh", KK_COL, det["kk"]["n"], det["kk"]["correct"])]):
        acc = corr / n
        yb = 1 - y
        ax.barh(yb, 1, height=0.42, color=GRID)
        ax.barh(yb, acc, height=0.42, color=col)
        if acc > 0.5:
            ax.text(0.015, yb, f"{acc * 100:.0f}%", va="center", fontsize=17,
                    fontweight="bold", color="white")
        else:
            ax.text(acc + 0.015, yb, f"{acc * 100:.0f}%", va="center",
                    fontsize=17, fontweight="bold", color=col)
        ax.text(1.0, yb + 0.32, f"n={n}", ha="right", fontsize=8.5, color=MUTED)
        ax.text(1.0, yb - 0.30, f"{corr}/{n} correct", ha="right", va="center",
                fontsize=9, color=MUTED)
    ax.set_xlim(0, 1.02)
    ax.set_ylim(-0.45, 2.05)
    ax.set_yticks([])
    ax.set_xticks([0, 0.5, 1])
    ax.set_xticklabels(["0%", "50%", "100%"])

    # Panel B: cost of misdetection
    ax2 = fig.add_subplot(gs[0, 1])
    strip_axes(ax2)
    ax2.set_title("B · What misdetection costs (Uzbek)", loc="left", fontsize=12)
    vals = [dw["correct"]["mean"], dw["misdetected"]["mean"]]
    ax2.bar([0, 1], vals, width=0.5, color=[C_AUTO, RED])
    for x, v in zip([0, 1], vals):
        ax2.text(x, v + 0.008, f"{v:.3f}", ha="center", fontsize=12,
                 fontweight="bold", color=TEXT)
    ax2.annotate("2× the error rate", xy=(0.30, 0.365), ha="center",
                 fontsize=10.5, color=RED, fontweight="bold")
    ax2.set_xticks([0, 1])
    ax2.set_xticklabels(["detected\ncorrectly (n=19)", "misdetected\n(n=51)"],
                        fontsize=9.5)
    ax2.set_ylabel("Mean WER")
    ax2.set_ylim(0, 0.42)

    # Panel C: routing result
    ax3 = fig.add_subplot(gs[0, 2])
    strip_axes(ax3)
    ax3.set_title("C · R1 routing vs always-HINT (PRIMARY)", loc="left",
                  fontsize=12)
    rows = [("Overall", "overall", TEXT), ("Uzbek", "uz", UZ_COL),
            ("Kazakh", "kk", KK_COL)]
    ys = [2, 1, 0]
    for y, (lbl, pop, col) in zip(ys, rows):
        c = conds[pop]
        d = c["d_routed_hint_mean"]
        ax3.hlines(y, -0.012, 0.012, color=GRID, lw=6, zorder=1)
        ax3.plot(d, y, "o", ms=11, color=col, zorder=3)
        ax3.text(-0.013, y, lbl, ha="right", va="center", fontsize=10.5,
                 color=col, fontweight="bold")
        ax3.text(0.014, y + 0.05, f"Δ {d:+.4f} · p = {c['p_primary']:.3f}",
                 va="center", fontsize=9, color=MUTED)
        ax3.text(0.014, y - 0.14,
                 f"routed to HINT: {c['routing_rate'] * 100:.0f}% of utterances",
                 va="center", fontsize=8, color=MUTED)
    ax3.axvline(0, color=MUTED, lw=0.8, ls="--", zorder=2)
    ax3.set_xlim(-0.045, 0.062)
    ax3.set_ylim(-0.7, 2.6)
    ax3.set_yticks([])
    ax3.set_xlabel("mean(WER routed − WER HINT)   ·   0 = identical to always-HINT",
                   fontsize=9)
    ax3.text(0.014, 2.45, "success criterion NOT MET for any population",
             fontsize=9.3, color=RED, fontweight="bold")

    fig.text(0.065, 0.052,
             "Routing converges to always-HINT because 73% of Uzbek utterances are already routed there "
             "(Kazakh: 1%). Top Uzbek misdetections: Turkish 18, English 12, Russian 3 (frozen report §11).",
             fontsize=8.4, color=MUTED)
    footer(fig)
    save(fig, "3_detection_routing")


# =====================================================================
# 4 — COST / LATENCY vs PERFORMANCE
# =====================================================================

def fig_cost_perf():
    s = data.phase2_summary()
    lat = data.phase2_latency()
    recs = data.load_phase2()
    cost = {}
    for r in recs:
        cost.setdefault(r["provider"], []).append(r["cost_usd"])
    cost = {p: data.mean(v) for p, v in cost.items()}

    fig = new_canvas(12.5, 6.6)
    header(fig,
           "Accuracy vs cost per audio-minute",
           "Phase 2 frozen corpus (300 utterances per language) · bubble size = mean request latency · "
           "list prices: ElevenLabs \\$0.00367/min · GCS Chirp 2 \\$0.021/min (frozen report §6)",
           ty=0.93, sy=0.865)

    ax = fig.add_axes([0.08, 0.15, 0.87, 0.60])
    strip_axes(ax)
    ax.set_facecolor(BG)

    providers = [
        ("elevenlabs", "ElevenLabs Scribe v2", BLUE, 0.00367),
        ("google_cloud_stt", "Google Cloud STT Chirp 2", AMBER, 0.021),
    ]
    for key, name, col, price in providers:
        for lang, lcol, lshort in (("uz", UZ_COL, "Uzbek"), ("kk", KK_COL, "Kazakh")):
            wer = s[(key, lang, "hint")]["mean"]
            mlat = lat[key]["mean"]
            ax.scatter(price, wer, s=mlat / 3.2, color=col, alpha=0.30, zorder=2,
                       edgecolors="none")
            ax.scatter(price, wer, s=42, color=col, zorder=3)
            dx = 0.06 if key == "elevenlabs" else 0.055
            ax.annotate(f"{lshort} · HINT WER {wer:.3f}",
                        (price, wer), xytext=(price * (1 + dx), wer + 0.004),
                        fontsize=9.6, color=TEXT, fontweight="bold", va="center")
            ax.annotate(f"{mlat / 1000:.2f}s mean latency · {cost[key] * 100:.2f}¢/call",
                        (price, wer), xytext=(price * (1 + dx), wer - 0.020),
                        fontsize=8.2, color=MUTED, va="center")

    ax.set_xscale("log")
    ax.set_xlim(0.0022, 0.075)
    ax.set_ylim(-0.02, 0.36)
    ax.minorticks_off()
    ax.set_xticks([0.00367, 0.021])
    ax.set_xticklabels(["$0.00367 / min\nElevenLabs", "$0.021 / min\nGCS Chirp 2"])
    ax.xaxis.set_minor_formatter(plt.NullFormatter())
    ax.tick_params(axis="x", which="minor", length=0)
    ax.set_yticks([0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35])
    ax.set_yticklabels(["0%", "5%", "10%", "15%", "20%", "25%", "30%", "35%"])
    ax.set_ylabel("Mean WER (HINT condition)", fontsize=10.5)
    ax.set_xlabel("List price per audio-minute (log scale)", fontsize=10.5)

    # AUTO reference markers (lighter)
    for key, name, col, price in providers:
        for lang in ("uz", "kk"):
            wer = s[(key, lang, "auto")]["mean"]
            ax.scatter(price, wer, s=26, color=col, alpha=0.45, zorder=3,
                       marker="s")
    ax.scatter([], [], s=26, color=GREY, marker="s", label="AUTO (auto-detect)")
    ax.scatter([], [], s=42, color=GREY, label="HINT (language supplied)")
    ax.legend(loc="upper left", fontsize=9.5, frameon=False)

    fig.text(0.065, 0.052,
             "ElevenLabs Scribe v2 dominates the frontier: lowest WER in all four provider×language cells "
             "at 1/5.7 the price and 2.6× lower mean latency. Phase 2 was descriptive (no hypothesis tests).",
             fontsize=8.4, color=MUTED)
    footer(fig)
    save(fig, "4_cost_latency_vs_performance")


# =====================================================================
# 5 — HERO FIGURE (social / Kaggle)
# =====================================================================

def fig_hero():
    fig = new_canvas(12.0, 6.75)  # 16:9
    fig.text(0.075, 0.865,
             "Central Asian Voice Benchmark",
             fontsize=30, fontweight="bold", color=TEXT, ha="left", va="top")
    fig.text(0.075, 0.775,
             "Speech-to-text for Uzbek & Kazakh · 6,400 API calls · 5 models · frozen results, 2026-08-25",
             fontsize=12, color=MUTED, ha="left", va="top")

    # accent rule
    fig.lines.append(plt.Line2D([0.075, 0.30], [0.735, 0.735],
                                transform=fig.transFigure, color=BLUE, lw=3))

    # three stat cards
    cards = [
        ("5.1%", "best Kazakh WER", "ElevenLabs Scribe v2, HINT · n=300", KK_COL),
        ("24.5%", "best Uzbek WER", "ElevenLabs Scribe v2, HINT · n=300", UZ_COL),
        ("27% vs 99%", "Uzbek vs Kazakh\ndetection accuracy", "AUTO mode · held-out eval split", RED),
    ]
    xs = [0.075, 0.395, 0.715]
    for x, (big, lbl, sub, col) in zip(xs, cards):
        # card background
        ax = fig.add_axes([x, 0.24, 0.21, 0.42])
        ax.axis("off")
        ax.set_facecolor(BG)
        ax.add_patch(plt.Rectangle((0, 0), 1, 1, transform=ax.transAxes,
                                   facecolor=CARD, edgecolor=GRID, lw=1,
                                   zorder=1, clip_on=False))
        ax.text(0.5, 0.74, big, ha="center", fontsize=27 if "%" in big and big != "27% vs 99%" else 21,
                fontweight="bold", color=col, transform=ax.transAxes, zorder=2)
        ax.text(0.5, 0.40, lbl, ha="center", fontsize=11.5, color=TEXT,
                transform=ax.transAxes, zorder=2, linespacing=1.3)
        ax.text(0.5, 0.16, sub, ha="center", fontsize=8.2, color=MUTED,
                transform=ax.transAxes, zorder=2)

    fig.text(0.075, 0.155,
             "Key finding: automatic language detection fails for Uzbek (27%) but not Kazakh (99%) — "
             "and misdetected Uzbek audio transcribes with 2× the error rate.\n"
             "A detect-and-route rule (R1) matched but did not beat always supplying the language hint "
             "(PRIMARY p = 0.820).",
             fontsize=9.8, color=TEXT, ha="left", va="top", linespacing=1.5)
    fig.text(0.075, 0.035, SOURCE, fontsize=8.2, color=MUTED, ha="left")
    save(fig, "5_hero_social")


if __name__ == "__main__":
    fig_leaderboard()
    fig_auto_vs_hint()
    fig_detection_routing()
    fig_cost_perf()
    fig_hero()
    print("done ->", OUT)
