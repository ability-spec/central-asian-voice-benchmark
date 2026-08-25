"""
Phase 3A Track B Benchmark Execution Script
============================================
200 utterances (100 Uzbek + 100 Kazakh) x 2 conditions = 400 requests

Provider:       ElevenLabs Scribe v2 ONLY (no GCS, Azure, or Gemini in Phase 3A)
Conditions:     auto (no language parameter) | hint (correct language code)
Output:         results/phase3a/phase3a_trackb_results.jsonl
Hard cap:       $0.50 (2.5x estimate computed from actual manifest durations)
Benchmark ver:  phase3a_trackb_v1

Safe to restart: yes. Loads prior state (committed_spend, completed combinations)
from the output file on startup. Skips already-completed (utterance_id, provider,
language_condition) tuples. Failed combinations are eligible for re-attempt.

Deduplication key: (utterance_id, provider, language_condition)

Pre-conditions (verify before running):
  1. ELEVENLABS_API_KEY env var set (ASCII-clean — no invisible Unicode)
  2. All 200 audio files present at paths in research/phase3a_audio_manifest.csv
  3. research/phase3a_audio_manifest.csv SHA-256 matches MANIFEST_SHA256 below
  4. jiwer installed (pip install jiwer)

DO NOT run before pre-conditions are satisfied.
DO NOT run the full 200-utterance set before the 40-utterance pilot is approved.
DO NOT modify the Phase 2 frozen manifests or results.
DO NOT modify research/phase3a_audio_manifest.csv after it is committed.
"""

import csv
import hashlib
import json
import os
import re
import sys
import time
import traceback
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------
REPO_ROOT    = Path(__file__).resolve().parent.parent.parent
MANIFEST_CSV = REPO_ROOT / "research" / "phase3a_audio_manifest.csv"
RESULTS_DIR  = Path(__file__).parent
RESULTS_FILE = RESULTS_DIR / "phase3a_trackb_results.jsonl"

# SHA-256 of research/phase3a_audio_manifest.csv.
# Computed by prepare_phase3a.py. Script aborts if actual hash does not match.
MANIFEST_SHA256 = "4e2ab89f7c30afebbb0fe756cc5deab2c171a9fbeefd65879bff5afd4ff6eddc"

BENCHMARK_VERSION = "phase3a_trackb_v1"
HARD_CAP          = 0.50   # USD — max(round(0.14974 * 2.5, 2), 0.50) = $0.50
MAX_RETRIES       = 3      # max attempts per utterance/condition
EL_RATE_PER_MIN   = 0.00367  # CONFIRMED: ElevenLabs list price (phase2_provider_matrix.json)

EL_MODEL    = "scribe_v2"
LANG_BCP47  = {"uz": "uz-UZ", "kk": "kk-KZ"}
LANG_HINT   = {"uz": "uz",    "kk": "kk"}   # ISO-639-1 codes for EL language_code param

# Global committed-spend tracker — loaded from output file on startup
committed_spend: float = 0.0

# ---------------------------------------------------------------------------
# Normalisation pipeline (methodology_proposal.md §C — identical to Phase 1/2)
# ---------------------------------------------------------------------------
_PUNCT = re.compile(r"[^\w\s']", re.UNICODE)
_APOS  = re.compile(r"[''ʼ`]")
_WS    = re.compile(r'\s+')


def normalise(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        return ''
    text = unicodedata.normalize('NFC', text)
    text = text.casefold()
    text = _APOS.sub("'", text)
    text = _PUNCT.sub(' ', text)
    text = _WS.sub(' ', text).strip()
    return text


def compute_wer(ref: str, hyp: str):
    r, h = normalise(ref), normalise(hyp)
    if not r:
        return None
    try:
        import jiwer
        return round(jiwer.wer(r, h), 6)
    except Exception:
        return None


def compute_cer(ref: str, hyp: str):
    r, h = normalise(ref), normalise(hyp)
    if not r:
        return None
    try:
        import jiwer
        return round(jiwer.cer(r, h), 6)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------
def estimate_cost(duration_s: float) -> float:
    return (duration_s / 60.0) * EL_RATE_PER_MIN


# ---------------------------------------------------------------------------
# Hard cap enforcement
# ---------------------------------------------------------------------------
class CapExceeded(Exception):
    pass


def check_and_reserve(projected: float, label: str = "") -> float:
    """
    Check that committed_spend + projected does not exceed HARD_CAP.
    If safe: increment committed_spend and return projected.
    If not safe: raise CapExceeded.

    ElevenLabs does not bill for failed requests. check_and_reserve is called
    before every attempt conservatively — committed_spend may be slightly
    over-reserved for failed retries and corrects on script restart.
    """
    global committed_spend
    if committed_spend + projected > HARD_CAP:
        raise CapExceeded(
            f"Hard cap ${HARD_CAP:.2f} would be exceeded: "
            f"committed=${committed_spend:.5f} + projected=${projected:.6f} [{label}]"
        )
    committed_spend += projected
    return projected


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


RUN_ID = f"phase3a_trackb_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"


# ---------------------------------------------------------------------------
# Record schema (same fields as Phase 2 for cross-phase comparability)
# ---------------------------------------------------------------------------
def make_record(
    row: dict,
    condition: str,
    hint_value,           # str for hint; None for auto
    raw_transcription,    # str or None
    http_status,
    error_type,
    error_message,
    latency_ms: int,
    cost_usd: float,
    retry_count: int,
    request_params: dict,
    provider_detected_language=None,
) -> dict:
    ref  = row["reference_transcript"]
    hyp  = raw_transcription or ""
    norm = normalise(hyp) if raw_transcription is not None else None

    return {
        "call_id":                       str(uuid.uuid4()),
        "run_id":                        RUN_ID,
        "benchmark_version":             BENCHMARK_VERSION,
        "timestamp_utc":                 datetime.now(timezone.utc).isoformat(),
        "provider":                      "elevenlabs",
        "model":                         EL_MODEL,
        "language_condition":            condition,
        "language_hint":                 hint_value,
        "utterance_id":                  row["utterance_id"],
        "audio_id":                      row["utterance_id"],
        "audio_sha256":                  row.get("_audio_sha256"),
        "audio_duration_s":              float(row["duration_seconds"]),
        "language":                      row["language"],
        "language_bcp47":                LANG_BCP47[row["language"]],
        "corpus_source":                 row["source_dataset"],
        "contamination_risk":            "MEDIUM",
        "track":                         "B",
        "fleurs_id":                     None,
        "fleurs_subset":                 None,
        "pilot_stratum":                 row.get("pilot_stratum", ""),
        "is_pilot":                      row.get("is_pilot", "false") == "true",
        "reference_transcript":          ref,
        "raw_transcription":             raw_transcription,
        "normalized_transcription":      norm,
        "wer":                           compute_wer(ref, raw_transcription) if raw_transcription is not None else None,
        "cer":                           compute_cer(ref, raw_transcription) if raw_transcription is not None else None,
        "provider_detected_language":    provider_detected_language,
        "independent_detected_language": None,
        "dominant_script":               None,
        "latency_ms":                    latency_ms,
        "http_status":                   http_status,
        "error_type":                    error_type,
        "error_message":                 error_message,
        "retry_count":                   retry_count,
        "cost_usd":                      round(cost_usd, 6),
        "cost_list_price_usd":           round(cost_usd, 6),
        "request_params":                request_params,
    }


def write_record(record: dict) -> None:
    with open(RESULTS_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------
def load_state() -> tuple:
    """
    Returns (prior_committed_spend, done).

    prior_committed_spend: sum of cost_usd for every record already in the file.
        ElevenLabs failure records have cost_usd=0, so they don't inflate spend.

    done: set of (utterance_id, provider, language_condition) for records where
        error_type IS NULL. Failed combinations are NOT in done and are eligible
        for re-attempt on restart (within the hard cap).
    """
    spend: float = 0.0
    done: set = set()
    if not RESULTS_FILE.exists():
        return spend, done

    with open(RESULTS_FILE, encoding='utf-8') as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"  WARNING: results file line {lineno} not valid JSON: {e}",
                      file=sys.stderr)
                continue
            spend += r.get("cost_usd") or 0.0
            if r.get("error_type") is None:
                done.add((r["utterance_id"], r["provider"], r["language_condition"]))

    return spend, done


# ---------------------------------------------------------------------------
# Manifest loading and verification
# ---------------------------------------------------------------------------
def load_and_verify_manifest() -> list:
    actual_sha = sha256_file(MANIFEST_CSV)
    if actual_sha != MANIFEST_SHA256:
        print("ABORT: phase3a_audio_manifest.csv SHA-256 mismatch.")
        print(f"  Expected: {MANIFEST_SHA256}")
        print(f"  Actual:   {actual_sha}")
        sys.exit(1)
    print(f"Manifest SHA-256: OK  ({MANIFEST_SHA256[:16]}...)")

    rows = []
    with open(MANIFEST_CSV, encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f):
            rows.append(row)

    uz_rows = [r for r in rows if r["language"] == "uz"]
    kk_rows = [r for r in rows if r["language"] == "kk"]

    if len(uz_rows) != 100 or len(kk_rows) != 100:
        print(f"ABORT: Expected 100 Uzbek + 100 Kazakh; got {len(uz_rows)} + {len(kk_rows)}.")
        sys.exit(1)

    pilot_rows = [r for r in rows if r.get("is_pilot") == "true"]
    eval_rows  = [r for r in rows if r.get("is_pilot") == "false"]
    if len(pilot_rows) != 40 or len(eval_rows) != 160:
        print(f"ABORT: Expected 40 pilot + 160 eval; got {len(pilot_rows)} + {len(eval_rows)}.")
        sys.exit(1)

    print(f"Manifest: {len(uz_rows)} Uzbek + {len(kk_rows)} Kazakh = {len(rows)} utterances")
    print(f"          {len(pilot_rows)} pilot + {len(eval_rows)} evaluation")

    # Precompute audio SHA-256 (done once per file, not per call)
    print(f"Computing audio SHA-256 hashes ({len(rows)} files)...", end="", flush=True)
    for row in rows:
        p = Path(row["canonical_audio_path"])
        row["_audio_sha256"] = sha256_file(p) if p.exists() else None
    print(" done.")

    return rows


# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------
def preflight(rows: list) -> bool:
    ok = True

    # ElevenLabs API key
    el_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not el_key:
        print("  FAIL: ELEVENLABS_API_KEY not set", file=sys.stderr)
        ok = False
    else:
        try:
            el_key.encode("ascii")
            print(f"  OK  : ELEVENLABS_API_KEY set, ASCII-clean, length={len(el_key)}")
        except UnicodeEncodeError:
            print("  FAIL: ELEVENLABS_API_KEY contains non-ASCII characters "
                  "(copy-paste artifact); re-set via PowerShell single-quotes",
                  file=sys.stderr)
            ok = False

    # Audio files
    missing = [r for r in rows if not Path(r["canonical_audio_path"]).exists()]
    if missing:
        print(f"  FAIL: {len(missing)} audio files missing:", file=sys.stderr)
        for r in missing[:5]:
            print(f"        {r['canonical_audio_path']}", file=sys.stderr)
        if len(missing) > 5:
            print(f"        ... and {len(missing) - 5} more", file=sys.stderr)
        ok = False
    else:
        print(f"  OK  : All {len(rows)} audio files present")

    # jiwer
    try:
        import jiwer  # noqa: F401
        print("  OK  : jiwer installed")
    except ImportError:
        print("  FAIL: jiwer not installed (pip install jiwer)", file=sys.stderr)
        ok = False

    # ElevenLabs SDK
    try:
        from elevenlabs import ElevenLabs  # noqa: F401
        print("  OK  : elevenlabs SDK installed")
    except ImportError:
        print("  FAIL: elevenlabs SDK not installed (pip install elevenlabs)", file=sys.stderr)
        ok = False

    return ok


# ---------------------------------------------------------------------------
# ElevenLabs Scribe v2 — single utterance/condition call
# ---------------------------------------------------------------------------
def call_elevenlabs(row: dict, condition: str, hint_value, el_client) -> dict:
    """
    Execute one ElevenLabs STT call with retry and cap enforcement.
    Returns dict with: raw, http_status, error_type, error_message, latency_ms,
    retry_count, detected_lang, request_params, cost_usd.
    """
    projected = estimate_cost(float(row["duration_seconds"]))

    request_params = {"model_id": EL_MODEL}
    if condition == "hint":
        request_params["language_code"] = hint_value

    raw           = None
    http_status   = None
    error_type    = None
    error_message = None
    detected_lang = None
    attempts_made = 0
    t0            = time.monotonic()

    for attempt in range(MAX_RETRIES):
        try:
            check_and_reserve(projected,
                              f"EL {row['utterance_id']} {condition} attempt={attempt}")
        except CapExceeded as e:
            latency_ms = round((time.monotonic() - t0) * 1000)
            return {
                "raw": None, "http_status": None,
                "error_type": "CapAborted", "error_message": str(e),
                "latency_ms": latency_ms, "retry_count": attempt,
                "detected_lang": None, "request_params": request_params,
                "cost_usd": 0.0,
            }

        attempts_made = attempt + 1
        try:
            with open(row["canonical_audio_path"], "rb") as audio_file:
                kwargs = {"model_id": EL_MODEL}
                if condition == "hint":
                    kwargs["language_code"] = hint_value
                result = el_client.speech_to_text.convert(file=audio_file, **kwargs)

            if not hasattr(result, "text"):
                raise AttributeError(
                    f"ElevenLabs response missing 'text' field; SDK may have changed schema. "
                    f"Got type={type(result).__name__}. "
                    f"Public attrs: {[a for a in dir(result) if not a.startswith('_')]}"
                )
            raw           = result.text
            detected_lang = getattr(result, "language_code", None)
            http_status   = 200
            error_type    = None
            error_message = None
            break
        except AttributeError:
            raise   # schema change — do not retry
        except Exception as e:
            error_message = str(e)
            error_type    = type(e).__name__
            http_status   = None
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)

    latency_ms = round((time.monotonic() - t0) * 1000)
    cost_usd   = projected if raw is not None else 0.0

    return {
        "raw": raw, "http_status": http_status,
        "error_type": error_type, "error_message": error_message,
        "latency_ms": latency_ms, "retry_count": attempts_made - 1,
        "detected_lang": detected_lang, "request_params": request_params,
        "cost_usd": cost_usd,
    }


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main() -> None:
    global committed_spend

    print("=" * 72)
    print(f"Phase 3A Track B — ElevenLabs Scribe v2")
    print(f"run_id           = {RUN_ID}")
    print(f"benchmark_version= {BENCHMARK_VERSION}")
    print(f"hard_cap         = ${HARD_CAP:.2f}")
    print(f"max_retries      = {MAX_RETRIES}")
    print("=" * 72)
    print()

    # Load and verify manifest
    rows = load_and_verify_manifest()
    print()

    # Load prior state
    prior_spend, done = load_state()
    committed_spend   = prior_spend
    print(f"Prior state: {len(done)} completed tuples, committed_spend=${committed_spend:.5f}")
    print()

    # Preflight
    print("Preflight checks:")
    if not preflight(rows):
        print()
        print("ABORT: preflight failed. Fix the issues above before running.")
        sys.exit(1)
    print()

    # Determine run mode
    pilot_rows  = [r for r in rows if r.get("is_pilot") == "true"]
    all_rows    = rows  # runs full 200 by default; caller controls which rows to pass

    # -----------------------------------------------------------------------
    # CLI mode: --pilot or --full must be explicit.
    # Bare invocation or unknown flags must not reach the API call path.
    # -----------------------------------------------------------------------
    _USAGE = "Usage: python run_phase3a_trackb.py --pilot | --full"
    _known_flags = {"--pilot", "--full"}
    _extra = [a for a in sys.argv[1:] if a not in _known_flags]
    if _extra:
        print(_USAGE)
        sys.exit(1)
    if "--pilot" in sys.argv and "--full" in sys.argv:
        print(_USAGE)
        sys.exit(1)
    if "--pilot" not in sys.argv and "--full" not in sys.argv:
        print(_USAGE)
        sys.exit(1)
    if "--pilot" in sys.argv:
        target_rows = pilot_rows
        mode_label  = "PILOT (40 utterances, 80 calls)"
    else:
        target_rows = all_rows
        mode_label  = "FULL (200 utterances, 400 calls)"

    total_calls = len(target_rows) * 2  # AUTO + HINT
    print(f"Run mode: {mode_label}")
    print(f"Calls    : {total_calls} ({len(target_rows)} utterances x 2 conditions)")
    print(f"Committed: ${committed_spend:.5f} / ${HARD_CAP:.2f} at provider start")
    print("-" * 72)

    # Initialize ElevenLabs client
    el_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    from elevenlabs import ElevenLabs
    el_client = ElevenLabs(api_key=el_key)

    # Main execution loop
    cap_aborted = False
    utterances_run = 0

    for i, row in enumerate(target_rows):
        uid     = row["utterance_id"]
        lang    = row["language"]
        hint_v  = LANG_HINT[lang]     # "uz" or "kk"
        stratum = row.get("pilot_stratum", "")

        for condition in ("auto", "hint"):
            hint_value = hint_v if condition == "hint" else None
            dedup_key  = (uid, "elevenlabs", condition)

            if dedup_key in done:
                continue

            result = call_elevenlabs(row, condition, hint_value, el_client)

            record = make_record(
                row            = row,
                condition      = condition,
                hint_value     = hint_value,
                raw_transcription       = result["raw"],
                http_status    = result["http_status"],
                error_type     = result["error_type"],
                error_message  = result["error_message"],
                latency_ms     = result["latency_ms"],
                cost_usd       = result["cost_usd"],
                retry_count    = result["retry_count"],
                request_params = result["request_params"],
                provider_detected_language = result["detected_lang"],
            )
            write_record(record)

            if result["error_type"] is None:
                done.add(dedup_key)

            status  = "OK" if result["error_type"] is None else f"ERROR({result['error_type']})"
            wer_str = f"WER={record['wer']:.3f}" if record["wer"] is not None else "WER=N/A"
            stratum_tag = f"[{stratum}]" if stratum else ""
            print(f"  [{condition:4s}] {uid}  {lang}  {status}  {wer_str}  "
                  f"{result['latency_ms']}ms  {stratum_tag}")

            if result["error_type"] == "CapAborted":
                cap_aborted = True
                break

        if cap_aborted:
            print(f"\nABORT: Hard cap ${HARD_CAP:.2f} enforced before {uid}.")
            print(f"  committed_spend at abort: ${committed_spend:.5f}")
            break

        utterances_run += 1
        if (utterances_run % 25 == 0):
            pct = 100 * committed_spend / HARD_CAP
            print(f"  -- progress: {utterances_run}/{len(target_rows)} utterances  "
                  f"committed=${committed_spend:.4f}/${HARD_CAP:.2f} ({pct:.1f}%) --")

    # Final summary
    print()
    print("=" * 72)
    print("RUN COMPLETE")
    print("=" * 72)
    print(f"run_id           = {RUN_ID}")
    print(f"benchmark_version= {BENCHMARK_VERSION}")
    print(f"hard_cap         = ${HARD_CAP:.2f}")
    print(f"committed_spend  = ${committed_spend:.5f}")
    print(f"utterances_run   = {utterances_run} / {len(target_rows)}")
    print(f"completed_tuples = {len(done)}")

    if RESULTS_FILE.exists():
        total_records = sum(1 for _ in open(RESULTS_FILE, encoding='utf-8'))
        error_records = 0
        actual_spend  = 0.0
        with open(RESULTS_FILE, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                    actual_spend += r.get("cost_usd") or 0.0
                    if r.get("error_type") is not None:
                        error_records += 1
                except Exception:
                    pass
        print(f"total_records    = {total_records}")
        print(f"error_records    = {error_records}")
        print(f"actual_spend     = ${actual_spend:.5f}")
        print(f"results_file     = {RESULTS_FILE}")

    if "--pilot" in sys.argv:
        print()
        print("PILOT RUN COMPLETE.")
        print("Review pilot results before running full evaluation.")
        print("To run full 200-utterance evaluation: python run_phase3a_trackb.py --full")


if __name__ == "__main__":
    main()
