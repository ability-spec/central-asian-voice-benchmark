"""Generate all benchmark figures from frozen results. No network, no API calls.

Run:  .venv/Scripts/python.exe make_figures.py
Outputs PNG + SVG + PDF to figures/.
"""

import math
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

import data
from style import (COLOR_AUTO, COLOR_HINT, COLOR_ROUTED, CONDITION_COLORS,
                   COLOR_KAZAKH, COLOR_UZBEK, TONE_MUTED, TONE_TEXT,
                   apply_style, save_all)

apply_style()
OUT = Path(__file__).resolve().parent / "figures"
OUT.mkdir(exist_ok=True)

LANG_LABEL = {"uz": "Uzbek", "kk": "Kazakh"}
LANG_COLOR = {"uz": COLOR_UZBEK, "kk": COLOR_KAZAKH}
PROVIDER_LABEL = {
    "elevenlabs": "ElevenLabs\nScribe v2",
    "google_cloud_stt": "Google Cloud STT\nChirp 2",
}

conds = None


def get_conds():
    global conds
    if conds is None:
        conds = data.phase3a_conditions()
    return conds


def fmt_pct(x):
    return f"{100 * x:.0f}%"


# =====================================================================
# FIGURE 1 — FLAGSHIP: the Uzbek detection failure and its consequence
# =====================================================================

def fig_flagship():
    det = data.detection_counts()
    dw = data.detection_wer_split()
    c = get_conds()

    fig = plt.figure(figsize=(11, 5.6))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.05, 1], wspace=0.28,
                          left=0.07, right=0.96, top=0.80, bottom=0.16)

    fig.suptitle(
        "Automatic language detection fails for Uzbek but not for Kazakh",
        x=0.07, ha="left", fontsize=15, fontweight="bold")
    fig.text(0.07, 0.885,
             "ElevenLabs Scribe v2, AUTO condition · Phase 3A evaluation set "
             "(held-out, n=160 utterances) · focused pilot study",
             fontsize=10, color=TONE_MUTED)

    # ---- Panel A: detection correctness as stacked bars ----
    ax = fig.add_subplot(gs[0, 0])
    langs = ["uz", "kk"]
    correct = [det[l]["correct"] for l in langs]
    wrong = [det[l]["n"] - det[l]["correct"] for l in langs]

    y = np.arange(len(langs))
    ax.barh(y, wrong, color="#C4CCD6", height=0.55,
            label="Misdetected")
    ax.barh(y, correct, left=wrong, color=CONDITION_COLORS["AUTO"],
            height=0.55, label="Correctly detected")

    for i, l in enumerate(langs):
        acc = det[l]["accuracy"]
        n = det[l]["n"]
        colr = LANG_COLOR[l]
        ax.text(det[l]["n"] + 2, i, f"{fmt_pct(acc)}  (n={n})",
                va="center", fontsize=12, fontweight="bold", color=colr)
        # inside-bar labels
        if wrong[i] > 0:
            ax.text(wrong[i] / 2, i, str(wrong[i]), va="center", ha="center",
                    fontsize=9.5, color="white" if wrong[i] > 10 else TONE_MUTED)
        ax.text(wrong[i] + correct[i] / 2, i, str(correct[i]),
                va="center", ha="center", fontsize=9.5, color="white")

    ax.set_yticks(y)
    ax.set_yticklabels(["Uzbek", "Kazakh"], fontsize=12)
    for tick, l in zip(ax.get_yticklabels(), langs):
        tick.set_color(LANG_COLOR[l])
        tick.set_fontweight("bold")
    ax.set_xlim(0, 118)
    ax.set_xlabel("Evaluation utterances (count)")
    ax.set_title("A · Language detection accuracy, AUTO condition",
                 loc="left")
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(axis="y", visible=False)

    # ---- Panel B: WER consequence of misdetection ----
    ax2 = fig.add_subplot(gs[0, 1])
    cats = ["Detected correctly\n(uzb)\nn = 19",
            "Misdetected\n(other language tag)\nn = 51"]
    vals = [dw["correct"]["mean"], dw["misdetected"]["mean"]]
    bars = ax2.bar([0, 1], vals, width=0.52,
                   color=[CONDITION_COLORS["AUTO"], "#B0413E"])
    for x, v in zip([0, 1], vals):
        ax2.text(x, v + 0.008, f"{v:.3f}", ha="center", fontsize=11.5,
                 fontweight="bold")
    ax2.annotate("+100% relative WER\nvs correctly detected",
                 xy=(0.38, 0.30), xycoords=("axes fraction", "data"),
                 ha="center", fontsize=10, color="#B0413E",
                 fontweight="bold")
    ax2.set_xticks([0, 1])
    ax2.set_xticklabels(cats, fontsize=10)
    ax2.set_ylabel("Mean word error rate (WER)")
    ax2.set_ylim(0, 0.42)
    ax2.set_title("B · Cost of a wrong detection (Uzbek, AUTO)",
                  loc="left")
    ax2.grid(axis="x", visible=False)

    fig.text(0.07, 0.03,
             "Misdetections are dominated by Turkish (18), English (12), Russian (3); "
             "Cyrillic-script detections produce wrong-script output (WER ≥ 1). "
             "Detection accuracy computed from frozen Phase 3A results.",
             fontsize=8.3, color=TONE_MUTED)

    return save_all(fig, OUT, "01_flagship_uzbek_detection_failure")


# =====================================================================
# FIGURE 2 — DETECTION DETAIL: what Uzbek gets mistaken for
# =====================================================================

def fig_detection_detail():
    det = data.detection_counts()

    fig = plt.figure(figsize=(11, 4.4))
    gs = fig.add_gridspec(1, 2, width_ratios=[1, 1.25], wspace=0.30,
                          left=0.08, right=0.97, top=0.82, bottom=0.14)
    ax = fig.add_subplot(gs[0, 0])
    axl = fig.add_subplot(gs[0, 1])

    fig.suptitle("Language detection outcomes by target language",
                 x=0.08, ha="left", fontsize=14, fontweight="bold")
    fig.text(0.08, 0.87,
             "ElevenLabs Scribe v2, AUTO condition · Phase 3A evaluation split "
             "(Uzbek n=70, Kazakh n=90)",
             fontsize=10, color=TONE_MUTED)

    # Left: accuracy summary
    accs = [det["uz"]["accuracy"], det["kk"]["accuracy"]]
    ns = [det["uz"]["n"], det["kk"]["n"]]
    y = np.arange(2)
    ax.barh(y, [1 - a for a in accs], color="#C4CCD6", height=0.5)
    ax.barh(y, accs, left=[1 - a for a in accs], height=0.5,
            color=[COLOR_UZBEK, COLOR_KAZAKH])
    ax.text(0.02, 0, f"{fmt_pct(1 - accs[0])} misdetected",
            va="center", fontsize=9.5, color="#7A2E2B", fontweight="bold")
    ax.text(1 - accs[0] + 0.02, 0, f"{fmt_pct(accs[0])} correct",
            va="center", fontsize=9.5, color="white", fontweight="bold")
    ax.text(accs[1] - 0.02, 1, f"{fmt_pct(accs[1])}  (n={ns[1]})",
            va="center", ha="right", fontsize=11, fontweight="bold",
            color="white")
    ax.set_yticks(y)
    ax.set_yticklabels(["Uzbek → uzb", "Kazakh → kaz"], fontsize=11)
    ax.set_xlim(0, 1.02)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1])
    ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax.set_title("A · Detection accuracy", loc="left")
    ax.grid(axis="y", visible=False)

    # Right: misdetection targets for Uzbek (Kazakh has only one case)
    misd = det["uz"]["misdetections"]
    items = sorted(misd.items(), key=lambda kv: -kv[1])
    top = items[:7]
    other = sum(v for _, v in items[7:])
    if other:
        top.append(("other", other))

    labels = [f"{code}" + ("  (other)" if code == "other" else "")
              for code, _ in top]
    counts = [v for _, v in top]
    ypos = np.arange(len(top))[::-1]
    axl.barh(ypos, counts, height=0.62, color="#C98A85")
    for yy, cnt in zip(ypos, counts):
        axl.text(cnt + 0.25, yy, str(cnt), va="center", fontsize=9.5,
                 color=TONE_MUTED)
    axl.set_yticks(ypos)
    axl.set_yticklabels(labels, fontsize=10)
    mono_codes = {"tur": "Turkish", "eng": "English", "rus": "Russian",
                  "fin": "Finnish", "est": "Estonian"}
    axl.set_xlim(0, max(counts) * 1.18)
    axl.set_xlabel("Uzbek utterances misclassified (of 51 misdetected)")
    axl.set_title("B · What Uzbek is mistaken for", loc="left")
    axl.grid(axis="y", visible=False)
    # add full-language annotation next to ISO code
    for tick, (code, _) in zip(axl.get_yticklabels(), top):
        if code in mono_codes:
            tick.set_text(tick.get_text() + f" — {mono_codes[code]}")
            tick.set_color(TONE_MUTED)

    fig.text(0.08, 0.025,
             "The single Kazakh misdetection (1 of 90) was Ukrainian. "
             "Counts computed from provider_detected_language in frozen Phase 3A records.",
             fontsize=8.3, color=TONE_MUTED)

    return save_all(fig, OUT, "02_detection_outcomes_by_language")


# =====================================================================
# FIGURE 3 — AUTO vs HINT: paired structure, honestly non-significant
# =====================================================================

def fig_auto_vs_hint():
    recs = data.phase3a_eval(data.load_phase3a())
    pairs = data.pair_by_utterance(recs)
    c = get_conds()

    fig = plt.figure(figsize=(11.5, 5.2))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.15, 1], wspace=0.26,
                          left=0.065, right=0.97, top=0.78, bottom=0.21)

    fig.suptitle("AUTO vs HINT: paired per-utterance differences",
                 x=0.065, ha="left", fontsize=14.5, fontweight="bold")
    fig.text(0.065, 0.875,
             "ElevenLabs Scribe v2 · Phase 3A evaluation split · "
             "160 paired utterances (70 Uzbek, 90 Kazakh)",
             fontsize=10, color=TONE_MUTED)

    # ---- Panel A: mean WER by language & condition with paired deltas ----
    ax = fig.add_subplot(gs[0, 0])

    def lang_wers(pop):
        return ([pairs[u]["auto"]["wer"] for u in pop],
                [pairs[u]["hint"]["wer"] for u in pop])

    uz_pop = [u for u, p in pairs.items() if p["auto"]["language"] == "uz"]
    kk_pop = [u for u, p in pairs.items() if p["auto"]["language"] == "kk"]

    xpos = {"uz": 0, "kk": 1}
    w = 0.30
    for lang, pop in (("uz", uz_pop), ("kk", kk_pop)):
        aw, hw = lang_wers(pop)
        am, hm = np.mean(aw), np.mean(hw)
        x = xpos[lang]
        ax.bar(x - w / 2 - 0.015, am, width=w, color=COLOR_AUTO,
               label="AUTO" if lang == "uz" else None)
        ax.bar(x + w / 2 + 0.015, hm, width=w, color=COLOR_HINT,
               label="HINT" if lang == "uz" else None)
        # paired-utterance slope lines (light, alpha by whether changed)
        for u in pop:
            a, h = pairs[u]["auto"]["wer"], pairs[u]["hint"]["wer"]
            changed = abs(a - h) > 1e-12
            ax.plot([x - w / 2 - 0.015, x + w / 2 + 0.015], [a, h],
                    color=TONE_MUTED if changed else "#E3E7EC",
                    alpha=0.55 if changed else 0.8, lw=0.7 if changed else 0.5,
                    zorder=1)
        d_ah = am - hm
        sym = "−" if d_ah < 0 else "+"
        ax.text(x, max(am, hm) + 0.022,
                f"Δ {sym}{abs(d_ah):.3f}\np = {c[lang]['p_secondary']:.3f} (n.s.)"
                if c[lang]["p_secondary"] >= 0.05 else
                f"Δ {sym}{abs(d_ah):.3f}\np = {c[lang]['p_secondary']:.3f}",
                ha="center", fontsize=9.3, color=TONE_TEXT)

    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Uzbek (n=70)", "Kazakh (n=90)"], fontsize=11)
    for tick, lang in zip(ax.get_xticklabels(), ["uz", "kk"]):
        tick.set_color(LANG_COLOR[lang])
        tick.set_fontweight("bold")
    ax.set_ylabel("Mean WER")
    ax.set_ylim(0, 0.40)
    ax.set_title("A · Mean WER with per-utterance paired lines", loc="left")
    ax.legend(loc="upper right")
    ax.text(0.985, 0.72, "grey lines = utterances where\nconditions differ",
            transform=ax.transAxes, ha="right", fontsize=8,
            color=TONE_MUTED, style="italic")
    ax.grid(axis="x", visible=False)

    # ---- Panel B: distribution of paired differences (AUTO − HINT) ----
    ax2 = fig.add_subplot(gs[0, 1])
    diffs_all = []
    for lang, pop in (("uz", uz_pop), ("kk", kk_pop)):
        diffs_all.extend((pairs[u]["auto"]["wer"] - pairs[u]["hint"]["wer"],
                          lang) for u in pop)

    bins = np.arange(-0.60, 0.65, 0.05)
    uz_d = [d for d, l in diffs_all if l == "uz"]
    kk_d = [d for d, l in diffs_all if l == "kk"]
    ax2.hist(uz_d, bins=bins, alpha=0.75, label=f"Uzbek (n={len(uz_d)})",
             color=COLOR_UZBEK, edgecolor="white", linewidth=0.4)
    ax2.hist(kk_d, bins=bins, bottom=None,
             weights=np.ones(len(kk_d)) / 1.0, alpha=0.75,
             label=f"Kazakh (n={len(kk_d)})", color=COLOR_KAZAKH,
             edgecolor="white", linewidth=0.4)

    ov = c["overall"]
    lo, hi = ov["ci_auto_hint"]
    ax2.axvspan(lo, hi, color=CONDITION_COLORS["ROUTED"], alpha=0.13,
                label="Bootstrap 95% CI of overall mean Δ")
    ax2.axvline(0, color=TONE_MUTED, lw=0.8, ls="--")
    ax2.axvline(ov["d_auto_hint_mean"], color=TONE_TEXT, lw=1.4,
                label=f"overall mean Δ = +{ov['d_auto_hint_mean']:.3f}")

    ax2.set_xlabel("Per-utterance WER difference, AUTO − HINT\n"
                   "(positive ⇒ HINT better)")
    ax2.set_ylabel("Utterances")
    ax2.set_title("B · Distribution of paired differences", loc="left")
    ax2.legend(loc="upper right", fontsize=8.5)

    fig.text(0.065, 0.02,
             "SECONDARY analysis (not the primary hypothesis). Wilcoxon signed-rank, one-tailed: "
             f"overall p={ov['p_secondary']:.3f}; Uzbek p={c['uz']['p_secondary']:.3f}; "
             f"Kazakh p={c['kk']['p_secondary']:.3f}. No comparison reaches p<0.05; "
             "all bootstrap CIs include zero.\nThe descriptive Uzbek HINT advantage should NOT be presented as a proven improvement.",
             fontsize=8.3, color=TONE_MUTED)

    return save_all(fig, OUT, "03_auto_vs_hint_paired")


# =====================================================================
# FIGURE 4 — ROUTING (PRIMARY): routed ≈ HINT, criterion not met
# =====================================================================

def fig_routing():
    c = get_conds()

    fig = plt.figure(figsize=(11.5, 4.6))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.35, 1, 1], wspace=0.28,
                          left=0.07, right=0.97, top=0.74, bottom=0.22)
    axes = [fig.add_subplot(gs[0, i]) for i in range(3)]

    fig.suptitle("R1 routing vs always-HINT (PRIMARY hypothesis): "
                 "routing shows no advantage over always-HINT",
                 x=0.07, ha="left", fontsize=13.5, fontweight="bold")
    fig.text(0.07, 0.845,
             "ElevenLabs Scribe v2 · Phase 3A evaluation split · R1 routes to HINT when AUTO "
             "misdetects the language · success criterion: mean(d) ≤ −0.030 AND p < 0.05 — NOT MET",
             fontsize=9.3, color=TONE_MUTED)

    pops = [("overall", "Overall (n=160)"), ("uz", "Uzbek (n=70)"),
            ("kk", "Kazakh (n=90)")]

    # Panel A: three conditions per population
    ax = axes[0]
    conds_keys = [("auto_mean", "AUTO", COLOR_AUTO),
                  ("hint_mean", "HINT", COLOR_HINT),
                  ("routed_mean", "ROUTED (R1)", COLOR_ROUTED)]
    width = 0.24
    for i, (key, label, colr) in enumerate(conds_keys):
        xs = np.arange(len(pops)) + (i - 1) * (width + 0.02)
        vals = [c[p][key] for p, _ in pops]
        ax.bar(xs, vals, width=width, color=colr, label=label)
        for x, v in zip(xs, vals):
            ax.text(x, v + 0.006, f"{v:.3f}", ha="center", fontsize=8.2,
                    rotation=90, color=TONE_MUTED)
    ax.set_xticks(np.arange(len(pops)))
    ax.set_xticklabels([lbl for _, lbl in pops], fontsize=10)
    for tick, (pop, _) in zip(ax.get_xticklabels()[::-1], pops[::-1]):
        pass
    ax.set_xticklabels(["Overall\n(n=160)", "Uzbek\n(n=70)", "Kazakh\n(n=90)"],
                       fontsize=10)
    ax.set_ylabel("Mean WER")
    ax.set_title("A · Mean WER by condition", loc="left")
    ax.legend(loc="upper right", fontsize=8.5, ncols=1)
    ax.grid(axis="x", visible=False)
    ax.set_ylim(0, 0.40)

    # Panels B/C: routed − HINT delta with CI, per language
    for ax_d, (pop, title) in zip(axes[1:], [("uz", "B · Uzbek"),
                                             ("kk", "C · Kazakh")]):
        diffs = c[pop]["d_routed_hint_mean"]
        p_val = c[pop]["p_primary"]

        # recompute CI deterministically for display
        import data as D
        recs = D.phase3a_eval(D.load_phase3a())
        pairs = D.pair_by_utterance(recs)
        routed = D.wer_routed_from_pairs(pairs)
        pop_uids = [u for u in pairs if pairs[u]["auto"]["language"] ==
                    ("uz" if pop == "uz" else "kk")]
        dd = [routed[u]["wer"] - pairs[u]["hint"]["wer"] for u in pop_uids]
        lo, hi = D.bootstrap_ci_mean(dd)

        ax_d.axhline(0, color=TONE_MUTED, lw=1.0)
        # success threshold at -0.030
        ax_d.axhline(-0.030, color="#B0413E", lw=1.0, ls="--")
        import matplotlib.transforms as mtransforms
        trans = mtransforms.blended_transform_factory(
            ax_d.transAxes, ax_d.transData)
        ax_d.text(0.97, -0.030, "success threshold (−0.030)", fontsize=7.5,
                  color="#B0413E", ha="right", va="bottom", transform=trans)

        xerr_lo = diffs - lo
        xerr_hi = hi - diffs
        ax_d.errorbar([diffs], [0.5],
                      xerr=[[xerr_lo], [xerr_hi]],
                      fmt="o", color=COLOR_ROUTED, capsize=4, ms=7,
                      lw=1.4)
        ax_d.set_yticks([])
        ax_d.set_ylim(0, 1)
        span = 0.05
        ax_d.set_xlim(min(-0.04, lo - 0.01), max(0.04, hi + 0.01))
        ax_d.set_xlabel("mean(routed − HINT)")
        ax_d.set_title(f"{title} · Δ = {diffs:+.4f}, p = {p_val:.3f}",
                       loc="left", fontsize=10.5)
        ax_d.grid(visible=False)
        nz = c[pop]["nz_primary"]
        ax_d.text(0.5, 0.12, f"nonzero pairs: {nz}",
                  transform=ax_d.transAxes, ha="center", fontsize=8,
                  color=TONE_MUTED, style="italic")

    fig.text(0.07, 0.025,
             "Routing converges toward HINT because it already routes most Uzbek utterances to HINT "
             "(73% Uzbek, 1% Kazakh). Routed ≈ HINT everywhere; the pre-specified PRIMARY success "
             "criterion is not met for any population.\nDo not interpret routed-vs-AUTO gains as evidence that routing beats always-HINT.",
             fontsize=8.3, color=TONE_MUTED)

    return save_all(fig, OUT, "04_r1_routing_primary")


# =====================================================================
# FIGURE 5 — PHASE 2 PROVIDER COMPARISON
# =====================================================================

def fig_phase2_providers():
    s = data.phase2_summary()
    lat = data.phase2_latency()

    providers = ["elevenlabs", "google_cloud_stt"]
    langs = ["uz", "kk"]

    fig = plt.figure(figsize=(11, 4.8))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.5, 1], wspace=0.25,
                          left=0.065, right=0.97, top=0.76, bottom=0.16)

    fig.suptitle("Phase 2 provider comparison (descriptive, n=300 per language)",
                 x=0.065, ha="left", fontsize=14, fontweight="bold")
    fig.text(0.065, 0.865,
             "Frozen Phase 2 corpus: 300 Uzbek + 300 Kazakh utterances · both providers × both conditions · "
             "no inferential tests conducted in Phase 2",
             fontsize=9.5, color=TONE_MUTED)

    # Panel A: grouped WER
    ax = fig.add_subplot(gs[0, 0])
    x = np.arange(4)  # EL/uz, EL/kk, GCS/uz, GCS/kk -> regroup instead
    groups = [(p, l) for p in providers for l in langs]
    width = 0.32
    for i, cond in enumerate(("auto", "hint")):
        vals = [s[(p, l, cond)]["mean"] for p, l in groups]
        ns = [s[(p, l, cond)]["n"] for p, l in groups]
        xs = np.arange(len(groups)) + (i - 0.5) * (width + 0.02)
        ax.bar(xs, vals, width=width,
               color=COLOR_AUTO if cond == "auto" else COLOR_HINT,
               label=cond.upper())
        for x_, v in zip(xs, vals):
            ax.text(x_, v + 0.008, f"{v:.3f}", ha="center", fontsize=8.3,
                    color=TONE_MUTED)
    ax.set_xticks(np.arange(len(groups)))
    ax.set_xticklabels(
        [f"{PROVIDER_LABEL[p].splitlines()[0]}\n{LANG_LABEL[l]}"
         for p, l in groups], fontsize=9)
    # color-code language names
    for tick, (_, l) in zip(ax.get_xticklabels()[::-1], groups[::-1]):
        pass
    for j, (tick, (_, l)) in enumerate(zip(ax.get_xticklabels(), groups)):
        pass
    ax.set_ylabel("Mean WER")
    ax.set_title("A · Mean WER by provider, language, and condition", loc="left")
    ax.legend(loc="upper left")
    ax.grid(axis="x", visible=False)
    ax.set_ylim(0, 0.50)

    # annotate the two-phase consistency note under panel A? keep clean.

    # Panel B: latency (mean + P95), Phase 2
    ax2 = fig.add_subplot(gs[0, 1])
    xs = np.arange(len(providers))
    means = [lat[p]["mean"] / 1000 for p in providers]
    p95s = [lat[p]["p95"] / 1000 for p in providers]
    ax2.bar(xs - 0.17, means, width=0.30, color="#7C8798", label="Mean")
    ax2.bar(xs + 0.17, p95s, width=0.30, color="#C4CCD6", label="P95")
    for xx, v in list(zip(xs - 0.17, means)) + list(zip(xs + 0.17, p95s)):
        ax2.text(xx, v + 0.05, f"{v:.2f}", ha="center", fontsize=8.5,
                 color=TONE_MUTED)
    ax2.set_xticks(xs)
    ax2.set_xticklabels([PROVIDER_LABEL[p].splitlines()[0] for p in providers],
                        fontsize=9.5)
    ax2.set_ylabel("Latency (seconds)")
    ax2.set_title("B · Request latency (Phase 2)", loc="left")
    ax2.legend(loc="upper left")
    ax2.grid(axis="x", visible=False)
    ax2.set_ylim(0, 4.8)

    fig.text(0.065, 0.02,
             "ElevenLabs Scribe v2 outperforms Google Cloud STT Chirp 2 in all four cells and is ~2.6× faster. "
             "Phase 2 was descriptive (no pre-specified hypothesis tests); cross-provider WER comparisons here are observational.",
             fontsize=8.3, color=TONE_MUTED)

    return save_all(fig, OUT, "05_phase2_provider_comparison")


# =====================================================================
# FIGURE 6 — RESEARCH DESIGN STORY: Phase 2 → 3A
# =====================================================================

def fig_research_story():
    c = get_conds()
    det = data.detection_counts()

    fig, ax = plt.subplots(figsize=(11, 4.6))
    ax.axis("off")
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 5.2)

    fig.suptitle("Research design: from multi-provider baseline to detection analysis to routing test",
                 x=0.06, ha="left", fontsize=14, fontweight="bold")

    boxes = [
        dict(x=0.3, title="PHASE 2", sub="Multi-provider evaluation",
             lines=["ElevenLabs Scribe v2 vs Google Chirp 2",
                    "600 utterances (300 uz + 300 kk)",
                    "× 2 conditions = 2,400 records",
                    "Descriptive: EL leads in",
                    "all four cells"]),
        dict(x=4.35, title="PHASE 3A · ANALYSIS", sub="Language-detection study",
             lines=["Held-out eval split: 160 utts",
                    "(70 uz + 90 kk)",
                    f"AUTO detection: Uzbek {fmt_pct(det['uz']['accuracy'])},",
                    f"Kazakh {fmt_pct(det['kk']['accuracy'])}",
                    "Uzbek detection failure = the",
                    "strongest defensible finding"]),
        dict(x=8.4, title="PHASE 3A · TEST", sub="R1 routing experiment",
             lines=["R1: use HINT where AUTO",
                    "misdetects the language",
                    f"PRIMARY: routed−HINT =",
                    f"{c['overall']['d_routed_hint_mean']:+.4f}, p={c['overall']['p_primary']:.3f}",
                    "Success criterion NOT MET:",
                    "routing ≈ always-HINT"]),
    ]

    box_colors = ["#EEF2F6", "#FBF3EA", "#EDF3EE"]
    accents = [COLOR_AUTO, COLOR_HINT, COLOR_ROUTED]

    for b, bc, ac in zip(boxes, box_colors, accents):
        rect = plt.Rectangle((b["x"], 0.9), 3.3, 3.5, facecolor=bc,
                             edgecolor=ac, linewidth=1.4, zorder=2)
        ax.add_patch(rect)
        ax.text(b["x"] + 0.18, 4.02, b["title"], fontsize=11.5,
                fontweight="bold", color=ac, zorder=3)
        ax.text(b["x"] + 0.18, 3.68, b["sub"], fontsize=9.5,
                color=TONE_MUTED, style="italic", zorder=3)
        for i, line in enumerate(b["lines"]):
            weight = "bold" if i == len(b["lines"]) - 1 and b is boxes[2] \
                else "normal"
            ax.text(b["x"] + 0.18, 3.20 - i * 0.42, line, fontsize=8.8,
                    color="#1F2430", zorder=3)

    # arrows
    for x0 in (3.68, 7.73):
        ax.annotate("", xy=(x0 + 0.55, 2.6), xytext=(x0, 2.6),
                    arrowprops=dict(arrowstyle="-|>", color=TONE_MUTED, lw=1.6))

    # bottom takeaway strip
    rect = plt.Rectangle((0.3, 0.12), 11.4, 0.55, facecolor="#F5F6F8",
                         edgecolor="none", zorder=2)
    ax.add_patch(rect)
    ax.text(6.0, 0.395,
            "Focused pilot study — Uzbek and Kazakh only · ElevenLabs Scribe v2 in Phases 3A · "
            "contamination risk MEDIUM (public corpora) · no broad Central Asian coverage implied",
            fontsize=8.8, ha="center", color="#1F2430", zorder=3,
            style="italic")

    return save_all(fig, OUT, "06_research_design_overview")


# =====================================================================
# LATENCY vs PERFORMANCE scatter (comparable quantities only)
# =====================================================================

def fig_latency_vs_wer():
    """Phase 2 only: same corpus, same conditions — provider-level mean WER vs
    mean latency are directly comparable across the four measured cells."""
    s = data.phase2_summary()
    lat = data.phase2_latency()

    fig = plt.figure(figsize=(8.6, 5.4))
    ax = fig.add_subplot(111)
    fig.subplots_adjust(left=0.10, right=0.96, top=0.83, bottom=0.14)
    fig.suptitle("Accuracy vs latency, Phase 2 (same corpus, per cell)",
                 x=0.10, ha="left", fontsize=13.5, fontweight="bold")
    fig.text(0.10, 0.875,
             "Each point: one provider × language × condition cell (n=300 each). "
             "Descriptive; Phase 2 included no hypothesis tests.",
             fontsize=9.5, color=TONE_MUTED)

    markers = {"uz": "o", "kk": "s"}
    # label offsets chosen per point to avoid collisions
    offsets = {
        ("elevenlabs", "uz", "auto"): (0.05, 0.012),
        ("elevenlabs", "uz", "hint"): (0.05, -0.024),
        ("elevenlabs", "kk", "auto"): (0.05, 0.012),
        ("elevenlabs", "kk", "hint"): (0.05, -0.024),
        ("google_cloud_stt", "uz", "auto"): (0.06, 0.016),
        ("google_cloud_stt", "uz", "hint"): (0.06, -0.012),
        ("google_cloud_stt", "kk", "auto"): (0.06, 0.020),
        ("google_cloud_stt", "kk", "hint"): (0.06, -0.030),
    }
    for prov in ("elevenlabs", "google_cloud_stt"):
        for lang in ("uz", "kk"):
            wer = s[(prov, lang, "auto")]["mean"]
            wer_h = s[(prov, lang, "hint")]["mean"]
            lat_s = lat[prov]["mean"] / 1000
            name = "ElevenLabs Scribe v2" if prov == "elevenlabs" \
                else "GCS Chirp 2"
            ax.scatter(lat_s, wer, marker=markers[lang], s=110,
                       color=COLOR_AUTO, zorder=3)
            ax.scatter(lat_s, wer_h, marker=markers[lang], s=110,
                       color=COLOR_HINT, zorder=3)
            dx, dy = offsets[(prov, lang, "auto")]
            ha = "left" if dx > 0 else "right"
            ax.annotate(f"{name} · {LANG_LABEL[lang]} AUTO ({wer:.3f})",
                        (lat_s, wer), xytext=(lat_s + dx, wer + dy),
                        ha=ha, fontsize=8.6, color=TONE_MUTED)
            dx, dy = offsets[(prov, lang, "hint")]
            ax.annotate(f"{name} · {LANG_LABEL[lang]} HINT ({wer_h:.3f})",
                        (lat_s, wer_h), xytext=(lat_s + dx, wer_h + dy),
                        ha=ha, fontsize=8.6, color=TONE_MUTED)

    ax.set_xlabel("Mean request latency, Phase 2 (s)")
    ax.set_ylabel("Mean WER")
    ax.set_xlim(0.4, 3.6)
    ax.set_ylim(0, 0.50)

    # legend proxies
    from matplotlib.lines import Line2D
    handles = [
        Line2D([], [], marker="o", ls="", color=TONE_MUTED, label="Uzbek"),
        Line2D([], [], marker="s", ls="", color=TONE_MUTED, label="Kazakh"),
        Line2D([], [], marker="o", ls="", color=COLOR_AUTO, label="AUTO"),
        Line2D([], [], marker="o", ls="", color=COLOR_HINT, label="HINT"),
    ]
    ax.legend(handles=handles, loc="upper right", fontsize=9)

    fig.text(0.10, 0.02,
             "Latency is a provider-level property measured on the shared Phase 2 corpus; "
             "language affects audio duration and therefore latency. No efficiency score is derived.",
             fontsize=8.3, color=TONE_MUTED)

    return save_all(fig, OUT, "07_phase2_accuracy_vs_latency")


if __name__ == "__main__":
    results = [
        fig_flagship(),
        fig_detection_detail(),
        fig_auto_vs_hint(),
        fig_routing(),
        fig_phase2_providers(),
        fig_latency_vs_wer(),
        fig_research_story(),
    ]
    print(f"Generated {len(results)} figures (PNG/SVG/PDF each) in {OUT}")
