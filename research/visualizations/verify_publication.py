"""Verify the publication / Kaggle-hub figures against the frozen report.

Every displayed number in figures/publication/ is computed from frozen JSONL
by data.py; this script cross-checks the key derived values against the
published final_benchmark_report.md (and the existing 41/41 gate), so the
new figure layer is traceable to the same single source of truth.

Run:  .venv/Scripts/python.exe verify_publication.py
"""

import sys

import data

TOL = 5e-4
checks = []


def check(name, computed, expected, tol=TOL):
    ok = abs(computed - expected) <= tol
    checks.append((name, computed, expected, ok))


def main():
    # ---- Dataset integrity (report §8) ----
    rc = data.reproducibility_counts()
    check("P3A total records", rc["p3a_total"], 468, tol=0)
    check("P3A successful", rc["p3a_successful"], 400, tol=0)
    check("P3A historical errors", rc["p3a_historical_error"], 68, tol=0)
    check("P3A eval records", rc["p3a_eval"], 320, tol=0)
    check("P3A eval AUTO", rc["p3a_eval_auto"], 160, tol=0)
    check("P3A eval HINT", rc["p3a_eval_hint"], 160, tol=0)
    check("P3A Uzbek eval", rc["p3a_uz_eval"], 140, tol=0)
    check("P3A Kazakh eval", rc["p3a_kk_eval"], 180, tol=0)
    check("Phase 2 total records", rc["p2_total"], 2400, tol=0)
    check("Phase 2 successful", rc["p2_successful"], 2400, tol=0)

    # ---- Phase 3A conditions (report §8, §9, §10) ----
    c = data.phase3a_conditions()
    ov = c["overall"]
    uz = c["uz"]
    kk = c["kk"]
    check("3A overall AUTO mean", ov["auto_mean"], 0.1664)
    check("3A overall HINT mean", ov["hint_mean"], 0.1534)
    check("3A overall routed mean", ov["routed_mean"], 0.1539)
    check("3A d(AUTO-HINT) overall", ov["d_auto_hint_mean"], 0.0130)
    check("3A d(routed-HINT) overall", ov["d_routed_hint_mean"], 0.0005)
    check("SECONDARY p overall", ov["p_secondary"], 0.075, tol=0.005)
    check("PRIMARY p overall", ov["p_primary"], 0.820, tol=0.005)
    check("routing rate overall", ov["routing_rate"], 52 / 160, tol=1e-9)
    check("3A Uzbek AUTO mean", uz["auto_mean"], 0.2906)
    check("3A Uzbek HINT mean", uz["hint_mean"], 0.2662)
    check("3A Uzbek routed mean", uz["routed_mean"], 0.2620)
    check("SECONDARY p Uzbek", uz["p_secondary"], 0.103, tol=0.005)
    check("PRIMARY p Uzbek", uz["p_primary"], 0.642, tol=0.005)
    check("Uzbek routing rate", uz["routing_rate"], 51 / 70, tol=1e-9)
    check("3A Kazakh AUTO mean", kk["auto_mean"], 0.0699)
    check("3A Kazakh HINT mean", kk["hint_mean"], 0.0657)
    check("3A Kazakh routed mean", kk["routed_mean"], 0.0699)
    check("SECONDARY p Kazakh", kk["p_secondary"], 0.245, tol=0.005)
    check("PRIMARY p Kazakh", kk["p_primary"], 0.755, tol=0.005)
    check("Kazakh routing rate", kk["routing_rate"], 1 / 90, tol=1e-9)

    # ---- Detection (report §11, §12) ----
    det = data.detection_counts()
    check("Uzbek detection accuracy", det["uz"]["accuracy"], 19 / 70, tol=1e-9)
    check("Uzbek detection n", det["uz"]["n"], 70, tol=0)
    check("Uzbek detection correct", det["uz"]["correct"], 19, tol=0)
    check("Uzbek misdetections", sum(det["uz"]["misdetections"].values()), 51, tol=0)
    check("Kazakh detection accuracy", det["kk"]["accuracy"], 89 / 90, tol=1e-9)
    check("Kazakh detection correct", det["kk"]["correct"], 89, tol=0)
    dw = data.detection_wer_split()
    check("AUTO WER when detected", dw["correct"]["mean"], 0.168, tol=5e-4)
    check("AUTO WER misdetected", dw["misdetected"]["mean"], 0.336, tol=5e-4)

    # ---- Phase 2 (report §7) ----
    p2 = data.phase2_summary()
    check("P2 EL uz AUTO WER", p2[("elevenlabs", "uz", "auto")]["mean"], 0.3416)
    check("P2 EL uz HINT WER", p2[("elevenlabs", "uz", "hint")]["mean"], 0.2446)
    check("P2 EL kk AUTO WER", p2[("elevenlabs", "kk", "auto")]["mean"], 0.0534)
    check("P2 EL kk HINT WER", p2[("elevenlabs", "kk", "hint")]["mean"], 0.0510)
    check("P2 GCS uz AUTO WER", p2[("google_cloud_stt", "uz", "auto")]["mean"], 0.4227)
    check("P2 GCS uz HINT WER", p2[("google_cloud_stt", "uz", "hint")]["mean"], 0.2602)
    check("P2 GCS kk AUTO WER", p2[("google_cloud_stt", "kk", "auto")]["mean"], 0.2666)
    check("P2 GCS kk HINT WER", p2[("google_cloud_stt", "kk", "hint")]["mean"], 0.2112)
    lat = data.phase2_latency()
    check("P2 EL mean latency", lat["elevenlabs"]["mean"], 899, tol=1.5)
    check("P2 GCS mean latency", lat["google_cloud_stt"]["mean"], 2364, tol=1.5)

    # ---- Cost (report §7) ----
    p2cost = data.cost_phase2()
    check("P2 EL total spend", p2cost["elevenlabs"]["total"], 0.4332, tol=1e-3)
    check("P2 GCS total spend", p2cost["google_cloud_stt"]["total"], 6.3630, tol=1e-3)

    # ---- Error analysis (report §13) ----
    errs = data.error_records_wer_ge_1(eval_only=True)
    check("WER>=1.0 eval records", len(errs), 15, tol=0)
    uz_err = [e for e in errs if e["language"] == "uz"]
    check("WER>=1.0 all Uzbek", len(uz_err), 15, tol=0)
    stripped, ref_apos = data.apostrophe_confound_uzbek_hint()
    check("apostrophe stripped records", len(stripped), 7, tol=0)
    check("apostrophe-bearing HINT refs", ref_apos, 45, tol=0)

    # ---- Determinism: re-run yields identical condition table ----
    c2 = data.phase3a_conditions()
    check("determinism overall d(routed-HINT)", c2["overall"]["d_routed_hint_mean"],
          ov["d_routed_hint_mean"])

    failed = [c for c in checks if not c[3]]
    for name, comp, exp, ok in checks:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}: computed={comp:.6f} expected={exp}")
    print(f"\n{len(checks) - len(failed)}/{len(checks)} publication checks passed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
