"""Verify every computed number against the frozen final benchmark report.

Run:  python verify_against_report.py
Fails loudly if any recomputed value deviates from the published report values
(beyond rounding tolerance). This is the traceability guarantee for figures.
"""

import sys

import data

TOL = 5e-4
checks = []


def check(name, computed, expected, tol=TOL):
    ok = abs(computed - expected) <= tol
    checks.append((name, computed, expected, ok))


def main():
    p2 = data.phase2_summary()
    check("P2 EL uz AUTO WER", p2[("elevenlabs", "uz", "auto")]["mean"], 0.3416)
    check("P2 EL uz HINT WER", p2[("elevenlabs", "uz", "hint")]["mean"], 0.2446)
    check("P2 EL kk AUTO WER", p2[("elevenlabs", "kk", "auto")]["mean"], 0.0534)
    check("P2 EL kk HINT WER", p2[("elevenlabs", "kk", "hint")]["mean"], 0.0510)
    check("P2 GCS uz AUTO WER", p2[("google_cloud_stt", "uz", "auto")]["mean"], 0.4227)
    check("P2 GCS uz HINT WER", p2[("google_cloud_stt", "uz", "hint")]["mean"], 0.2602)
    check("P2 GCS kk AUTO WER", p2[("google_cloud_stt", "kk", "auto")]["mean"], 0.2666)
    check("P2 GCS kk HINT WER", p2[("google_cloud_stt", "kk", "hint")]["mean"], 0.2112)
    check("P2 EL n per cell", p2[("elevenlabs", "uz", "auto")]["n"], 300, tol=0)

    lat = data.phase2_latency()
    check("P2 EL mean latency", lat["elevenlabs"]["mean"], 899, tol=1.5)
    check("P2 GCS mean latency", lat["google_cloud_stt"]["mean"], 2364, tol=1.5)

    det = data.detection_counts()
    check("Uzbek detection accuracy", det["uz"]["accuracy"], 19 / 70, tol=1e-9)
    check("Uzbek detection n", det["uz"]["n"], 70, tol=0)
    check("Uzbek detection correct", det["uz"]["correct"], 19, tol=0)
    check("Kazakh detection accuracy", det["kk"]["accuracy"], 89 / 90, tol=1e-9)
    check("Kazakh detection n", det["kk"]["n"], 90, tol=0)
    check("Kazakh detection correct", det["kk"]["correct"], 89, tol=0)

    conds = data.phase3a_conditions()
    ov = conds["overall"]
    check("3A overall AUTO mean", ov["auto_mean"], 0.1664)
    check("3A overall HINT mean", ov["hint_mean"], 0.1534)
    check("3A overall routed mean", ov["routed_mean"], 0.1539)
    check("3A d(AUTO-HINT) overall", ov["d_auto_hint_mean"], 0.0130)
    check("3A d(routed-HINT) overall", ov["d_routed_hint_mean"], 0.0005)
    # report p-values: SECONDARY overall 0.075, PRIMARY overall 0.820
    check("SECONDARY p overall", ov["p_secondary"], 0.075, tol=0.005)
    check("PRIMARY p overall", ov["p_primary"], 0.820, tol=0.005)
    check("routing rate overall", ov["routing_rate"], 52 / 160, tol=1e-9)

    uz = conds["uz"]
    check("3A Uzbek AUTO mean", uz["auto_mean"], 0.2906)
    check("3A Uzbek HINT mean", uz["hint_mean"], 0.2662)
    check("3A Uzbek routed mean", uz["routed_mean"], 0.2620)
    check("SECONDARY p Uzbek", uz["p_secondary"], 0.103, tol=0.005)
    check("PRIMARY p Uzbek", uz["p_primary"], 0.642, tol=0.005)
    check("Uzbek routing rate", uz["routing_rate"], 51 / 70, tol=1e-9)

    kk = conds["kk"]
    check("3A Kazakh AUTO mean", kk["auto_mean"], 0.0699)
    check("3A Kazakh HINT mean", kk["hint_mean"], 0.0657)
    check("3A Kazakh routed mean", kk["routed_mean"], 0.0699)
    check("SECONDARY p Kazakh", kk["p_secondary"], 0.245, tol=0.005)
    check("PRIMARY p Kazakh", kk["p_primary"], 0.755, tol=0.005)
    check("Kazakh routing rate", kk["routing_rate"], 1 / 90, tol=1e-9)

    dw = data.detection_wer_split()
    check("AUTO WER when detected", dw["correct"]["mean"], 0.168, tol=5e-4)
    check("AUTO WER misdetected", dw["misdetected"]["mean"], 0.336, tol=5e-4)
    check("n detected correct", dw["correct"]["n"], 19, tol=0)
    check("n misdetected", dw["misdetected"]["n"], 51, tol=0)

    failed = [c for c in checks if not c[3]]
    for name, comp, exp, ok in checks:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}: computed={comp:.6f} expected={exp}")
    print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
