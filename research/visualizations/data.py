"""Load frozen benchmark JSONL results and compute every number used in figures.

Rules:
- Reads ONLY the frozen results files. Never writes to results/.
- All WER/detection/latency/cost values shown in any figure are computed here.
- Statistical annotations (Wilcoxon p-values) are recomputed with the same
  manual implementation as the benchmark (average-rank tie handling,
  large-sample normal approximation), then cross-checked against the
  report's published values in tests/verify_against_report.py.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P2_JSONL = ROOT / "results" / "phase2_full" / "phase2_trackb_results.jsonl"
P3A_JSONL = ROOT / "results" / "phase3a" / "phase3a_trackb_results.jsonl"

EXPECTED_LANG = {"uz": "uzb", "kk": "kaz"}


def load_jsonl(path):
    recs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    return recs


def load_phase2():
    """Successful Phase 2 records only (error records excluded, as in the report)."""
    recs = [r for r in load_jsonl(P2_JSONL)
            if r.get("wer") is not None and r.get("http_status") == 200]
    return recs


def load_phase3a():
    return load_jsonl(P3A_JSONL)


def phase3a_eval(recs):
    """Evaluation-split successful records (is_pilot=false)."""
    return [r for r in recs
            if r.get("is_pilot") is False and r.get("wer") is not None]


# ---------- paired helpers ----------

def pair_by_utterance(records):
    """Return {utterance_id: {cond: record}} for records having both conds."""
    d = {}
    for r in records:
        uid = r["utterance_id"]
        d.setdefault(uid, {})[r["language_condition"]] = r
    return {u: c for u, c in d.items()
            if "auto" in c and "hint" in c}


def wer_routed_from_pairs(pairs):
    """R1 routing applied analytically per utterance.

    Route to HINT when provider_detected_language != expected code
    (null/missing counts as mismatch), else AUTO — identical to the report.
    """
    routed = {}
    for uid, conds in pairs.items():
        auto = conds["auto"]
        expected = EXPECTED_LANG[auto["language"]]
        det = auto.get("provider_detected_language")
        routed[uid] = conds["hint"] if det != expected else auto
    return routed


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs)


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    if n == 0:
        return float("nan")
    m = n // 2
    return xs[m] if n % 2 else (xs[m - 1] + xs[m]) / 2


def percentile(xs, q):
    """Linear-interpolated percentile (numpy 'linear' method equivalent)."""
    xs = sorted(xs)
    if not xs:
        return float("nan")
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q / 100.0
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    frac = pos - lo
    return xs[lo] * (1 - frac) + xs[hi] * frac


def wilcoxon_signed_rank(diffs, alternative):
    """Manual Wilcoxon signed-rank on nonzero diffs; large-sample normal approx
    with average-rank tie handling. Same formulation as the benchmark report.
    Returns (z, p_one_tailed, n_nonzero)."""
    import math

    nz = [d for d in diffs if d != 0]
    n = len(nz)
    if n == 0:
        return 0.0, 1.0, 0
    ranked = sorted(range(n), key=lambda i: abs(nz[i]))
    ranks = [0.0] * n
    i = 0
    # average ranks within tie groups
    while i < n:
        j = i
        while j + 1 < n and abs(nz[ranked[j + 1]]) == abs(nz[ranked[i]]):
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[ranked[k]] = avg
        i = j + 1
    w_plus = sum(r for d, r in zip(nz, ranks) if d > 0)
    w_minus = sum(r for d, r in zip(nz, ranks) if d < 0)
    w = w_plus  # statistic reported as W+ in the report

    # tie correction
    from collections import Counter
    tie_groups = Counter(abs(d) for d in nz)
    t_term = sum((t ** 3 - t) for t in tie_groups.values() if t > 1)

    mu = n * (n + 1) / 4
    var = n * (n + 1) * (2 * n + 1) / 24 - t_term / 48
    z = (w - mu) / math.sqrt(var)

    def phi(zval):
        # Abramowitz & Stegun normal CDF approximation
        t = 1.0 / (1.0 + 0.2316419 * abs(zval))
        poly = (t * (0.319381530 + t * (-0.356563782 +
                t * (1.781477937 + t * (-1.821255978 + t * 1.330274429)))))
        cdf = 1.0 - (math.exp(-zval * zval / 2) / math.sqrt(2 * math.pi)) * poly
        return cdf if zval >= 0 else 1.0 - cdf

    if alternative == "less":
        p = phi(z)
    elif alternative == "greater":
        p = 1.0 - phi(z)
    else:
        p = 2 * min(phi(z), 1 - phi(z))
    return z, p, n


def bootstrap_ci_mean(diffs, n_resamples=5000, seed=42):
    """Percentile bootstrap 95% CI on the mean of paired differences.
    Deterministic seed; used only where the figure displays a CI."""
    import random
    rnd = random.Random(seed)
    diffs = list(diffs)
    n = len(diffs)
    means = []
    for _ in range(n_resamples):
        means.append(mean(rnd.choice(diffs) for _ in range(n)))
    means.sort()
    lo = means[int(0.025 * n_resamples)]
    hi = means[min(int(0.975 * n_resamples), n_resamples - 1)]
    return lo, hi


# ---------- derived datasets ----------

def phase2_summary():
    """WER by provider x language x condition (Phase 2 only)."""
    recs = load_phase2()
    out = {}
    for r in recs:
        key = (r["provider"], r["language"], r["language_condition"])
        out.setdefault(key, []).append(r["wer"])
    summary = {}
    for (prov, lang, cond), wers in out.items():
        summary[(prov, lang, cond)] = {
            "n": len(wers), "mean": mean(wers),
        }
    return summary


def phase2_latency():
    recs = load_phase2()
    out = {}
    for r in recs:
        out.setdefault(r["provider"], []).append(r["latency_ms"])
    return {
        prov: {"mean": mean(v), "p50": percentile(v, 50), "p95": percentile(v, 95)}
        for prov, v in out.items()
    }


def detection_counts():
    """AUTO-condition language-detection correctness on the eval split."""
    recs = phase3a_eval(load_phase3a())
    auto = [r for r in recs if r["language_condition"] == "auto"]
    res = {}
    for lang in ("uz", "kk"):
        sub = [r for r in auto if r["language"] == lang]
        correct = [r for r in sub
                   if r.get("provider_detected_language") == EXPECTED_LANG[lang]]
        misdetect = {}
        for r in sub:
            det = r.get("provider_detected_language")
            if det != EXPECTED_LANG[lang]:
                misdetect[det or "none"] = misdetect.get(det or "none", 0) + 1
        res[lang] = {
            "n": len(sub),
            "correct": len(correct),
            "accuracy": len(correct) / len(sub),
            "misdetections": misdetect,
        }
    return res


def detection_wer_split():
    """AUTO WER split by detection outcome, Uzbek only (report Section 11)."""
    recs = phase3a_eval(load_phase3a())
    auto_uz = [r for r in recs
               if r["language_condition"] == "auto" and r["language"] == "uz"]
    corr, mis = [], []
    for r in auto_uz:
        (corr if r.get("provider_detected_language") == "uzb" else mis).append(r["wer"])
    return {"correct": {"n": len(corr), "mean": mean(corr)},
            "misdetected": {"n": len(mis), "mean": mean(mis)}}


def phase3a_conditions():
    """Per-language AUTO/HINT/ROUTED WER means + paired stats, eval split."""
    recs = phase3a_eval(load_phase3a())
    pairs = pair_by_utterance(recs)
    routed = wer_routed_from_pairs(pairs)

    def sel(pop_filter):
        uids = [u for u in pairs if pop_filter(pairs[u]["auto"])]
        return uids

    pops = {
        "overall": sel(lambda a: True),
        "uz": sel(lambda a: a["language"] == "uz"),
        "kk": sel(lambda a: a["language"] == "kk"),
    }
    out = {}
    for pop, uids in pops.items():
        auto_w = [pairs[u]["auto"]["wer"] for u in uids]
        hint_w = [pairs[u]["hint"]["wer"] for u in uids]
        rout_w = [routed[u]["wer"] for u in uids]

        d_secondary = [pairs[u]["auto"]["wer"] - pairs[u]["hint"]["wer"] for u in uids]
        d_primary = [routed[u]["wer"] - pairs[u]["hint"]["wer"] for u in uids]

        _, p_sec, nz_sec = wilcoxon_signed_rank(d_secondary, "greater")
        _, p_prim, nz_prim = wilcoxon_signed_rank(d_primary, "less")
        ci_sec = bootstrap_ci_mean(d_secondary)

        routing_rate = mean(
            [1.0 if routed[u]["language_condition"] == "hint" else 0.0 for u in uids])

        out[pop] = {
            "n": len(uids),
            "auto_mean": mean(auto_w), "hint_mean": mean(hint_w),
            "routed_mean": mean(rout_w),
            "d_auto_hint_mean": mean(d_secondary),
            "p_secondary": p_sec, "nz_secondary": nz_sec,
            "ci_auto_hint": ci_sec,
            "d_routed_hint_mean": mean(d_primary),
            "p_primary": p_prim, "nz_primary": nz_prim,
            "routing_rate": routing_rate,
        }
    return out


def latency_phase3a():
    recs = phase3a_eval(load_phase3a())
    by_lang = {}
    for r in recs:
        by_lang.setdefault((r["language"]), []).append(
            (r["audio_duration_s"], r["latency_ms"]))
    return {lang: {"n": len(v),
                   "mean_dur": mean(x[0] for x in v),
                   "mean_lat": mean(x[1] for x in v)}
            for lang, v in by_lang.items()}
