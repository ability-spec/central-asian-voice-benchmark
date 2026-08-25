"""
Phase 2 Track B Full Benchmark Execution Script

600 utterances (300 Uzbek + 300 Kazakh) x 2 conditions x 2 providers = 2,400 requests

Providers:      ElevenLabs Scribe v2 | Google Cloud STT Chirp 2
Conditions:     auto (no language parameter) | hint (correct language code)
Output:         results/phase2_full/phase2_trackb_results.jsonl
Hard cap:       $12.00 (abort before any call whose projected cost would breach this)
Benchmark ver:  phase2_trackb_v1

Safe to restart: yes. Loads prior state (committed_spend, completed combinations)
from the output file on startup. Only re-attempts failed or missing combinations.

Micro-pilot isolation: this script never reads from or writes to
results/phase2_micropilot/micropilot_results.jsonl. Records use
benchmark_version = "phase2_trackb_v1" which is distinct from the micro-pilot's
"phase2_micropilot_v1".

Pre-conditions (verify before running):
  1. ELEVENLABS_API_KEY env var set — must be ASCII-clean (no invisible Unicode)
  2. GOOGLE_APPLICATION_CREDENTIALS env var points to the service account JSON
  3. GCS project has Cloud Speech-to-Text API enabled
  4. Service account has roles/speech.client on the project
  5. All 600 audio files present at absolute paths in audio_benchmark_manifest.csv

DO NOT run before pre-conditions are satisfied.
DO NOT modify the frozen benchmark manifests.
DO NOT call APIs in test or import mode.
"""

import csv
import hashlib
import json
import math
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
REPO_ROOT     = Path(__file__).resolve().parent.parent.parent
MANIFEST_CSV  = REPO_ROOT / "research" / "audio_benchmark_manifest.csv"
RESULTS_DIR   = Path(__file__).parent
RESULTS_FILE  = RESULTS_DIR / "phase2_trackb_results.jsonl"
RUN_META_FILE = RESULTS_DIR / "phase2_trackb_manifest.json"

# SHA-256 of research/audio_benchmark_manifest.csv (frozen; verified against
# phase2_methodology.md). Script aborts if actual SHA-256 does not match.
MANIFEST_SHA256 = "d01408af2e04d048a44600138ac878f97b2a2372f62b9a42f2f7d0b161f34924"

BENCHMARK_VERSION  = "phase2_trackb_v1"
HARD_CAP           = 12.00    # USD; abort before any call that would exceed this
MAX_RETRIES        = 3        # maximum attempts per utterance/provider/condition
EL_RATE_PER_MIN    = 0.00367  # CONFIRMED: phase2_provider_matrix.json
GCS_RATE_PER_SEC   = 0.00035  # CONFIRMED: phase2_provider_matrix.json
GCS_BILLING_INCR_S = 15       # GCS V2 bills in 15-second increments

GCS_REGION  = "asia-southeast1"
GCS_MODEL   = "chirp_2"
EL_MODEL    = "scribe_v2"

LANG_BCP47 = {"uz": "uz-UZ", "kk": "kk-KZ"}

# ---------------------------------------------------------------------------
# Global committed-spend tracker
# Maintained by check_and_reserve(). Loaded from output file on startup.
# ---------------------------------------------------------------------------
committed_spend: float = 0.0

# ---------------------------------------------------------------------------
# Normalisation pipeline (methodology_proposal.md §C — identical to Phase 1)
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
# Cost estimation (confirmed rates; matches micro-pilot billing exactly)
# ---------------------------------------------------------------------------
def estimate_cost(duration_s: float, provider: str) -> float:
    if provider == "elevenlabs":
        return (duration_s / 60.0) * EL_RATE_PER_MIN
    if provider == "google_cloud_stt":
        # GCS bills at ceiling of 15-second increments regardless of success/failure
        billed_s = math.ceil(duration_s / GCS_BILLING_INCR_S) * GCS_BILLING_INCR_S
        return billed_s * GCS_RATE_PER_SEC
    raise ValueError(f"Unknown provider: {provider!r}")


# ---------------------------------------------------------------------------
# Hard cap enforcement
# ---------------------------------------------------------------------------
class CapExceeded(Exception):
    pass


def check_and_reserve(projected: float, label: str = "") -> float:
    """
    Check that committed_spend + projected does not exceed HARD_CAP.
    If safe: increment committed_spend and return projected.
    If not safe: raise CapExceeded (caller must write an abort record and exit).

    Called before EVERY API attempt including retries. For GCS, each network
    attempt is a billing event; for ElevenLabs, retries that fail are not
    billed but the check is still enforced conservatively.
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


# RUN_ID is fixed at import time so it is consistent across make_record calls
# within a single execution. Each execution (including restarts) gets a new
# RUN_ID. Deduplication uses (utterance_id, provider, condition), not run_id.
RUN_ID = f"phase2_trackb_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"


# ---------------------------------------------------------------------------
# Record schema (Phase 2 extension of Phase 1 schema per methodology §Result Schema)
# ---------------------------------------------------------------------------
def make_record(
    row: dict,
    provider: str,
    model: str,
    condition: str,
    hint_value,           # str for hint condition; None for auto
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
        "provider":                      provider,
        "model":                         model,
        "language_condition":            condition,
        "language_hint":                 hint_value,
        "utterance_id":                  row["utterance_id"],
        "audio_id":                      row["utterance_id"],
        "audio_sha256":                  row.get("_audio_sha256"),  # precomputed in load_manifest
        "audio_duration_s":              float(row["duration_seconds"]),
        "language":                      row["language"],
        "language_bcp47":                LANG_BCP47[row["language"]],
        "corpus_source":                 row["source_dataset"],
        "contamination_risk":            "MEDIUM",
        "track":                         "B",
        "fleurs_id":                     None,
        "fleurs_subset":                 None,
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
# State management: load prior run from output file
# ---------------------------------------------------------------------------
def load_state() -> tuple:
    """
    Returns (prior_committed_spend, done).

    prior_committed_spend: sum of cost_usd for every record already in the file.
        Includes failed GCS records (GCS bills per attempt even on failure).
        ElevenLabs failure records have cost_usd=0 so they don't inflate spend.

    done: set of (utterance_id, provider, language_condition) for records where
        error_type IS NULL only. Failed combinations are NOT in done and are
        eligible for re-attempt on restart (within the hard cap).
    """
    spend = 0.0
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
                print(f"  WARNING: results file line {lineno} is not valid JSON: {e}",
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
    """
    Verify SHA-256 of audio_benchmark_manifest.csv against the frozen value
    from phase2_methodology.md. Abort if mismatch. Load all 600 rows.
    Precomputes audio SHA-256 for each file (once, not per call).
    """
    actual_sha = sha256_file(MANIFEST_CSV)
    if actual_sha != MANIFEST_SHA256:
        print("ABORT: audio_benchmark_manifest.csv SHA-256 mismatch — frozen manifest may have been altered.")
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

    if len(uz_rows) != 300 or len(kk_rows) != 300:
        print(f"ABORT: Expected 300 Uzbek + 300 Kazakh; got {len(uz_rows)} + {len(kk_rows)}.")
        sys.exit(1)

    print(f"Manifest: {len(uz_rows)} Uzbek + {len(kk_rows)} Kazakh = {len(rows)} utterances")

    # Precompute audio SHA-256 (600 files, done once rather than 4× per file)
    print("Computing audio SHA-256 hashes (600 files)...", end="", flush=True)
    for row in rows:
        p = Path(row["canonical_audio_path"])
        row["_audio_sha256"] = sha256_file(p) if p.exists() else None
    print(" done.")

    return rows


# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------
def preflight(rows: list) -> bool:
    """
    Checks credentials, SDK imports, audio files, and jiwer.
    Returns True if all checks pass; False otherwise (print failures to stderr).
    Does not make any API calls.
    """
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
                  "(invisible Unicode from copy-paste); re-set with PowerShell single-quotes",
                  file=sys.stderr)
            ok = False

    # GCS credentials
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if not creds_path:
        print("  FAIL: GOOGLE_APPLICATION_CREDENTIALS not set", file=sys.stderr)
        ok = False
    elif not Path(creds_path).exists():
        print(f"  FAIL: credentials file not found: {creds_path}", file=sys.stderr)
        ok = False
    else:
        print(f"  OK  : GOOGLE_APPLICATION_CREDENTIALS -> {Path(creds_path).name}")

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

    # Google Cloud Speech SDK
    try:
        from google.cloud.speech_v2 import SpeechClient  # noqa: F401
        print("  OK  : google-cloud-speech SDK installed")
    except ImportError:
        print("  FAIL: google-cloud-speech not installed (pip install google-cloud-speech)",
              file=sys.stderr)
        ok = False

    return ok


# ---------------------------------------------------------------------------
# ElevenLabs Scribe v2 — single utterance/condition call
# ---------------------------------------------------------------------------
def call_elevenlabs(row: dict, condition: str, hint_value, el_client) -> dict:
    """
    Execute one ElevenLabs STT call with retry and cap enforcement.

    Cap enforcement: check_and_reserve is called before every attempt
    (including retries). ElevenLabs does not bill for failed requests, so
    cost_usd in the returned dict is projected only on success, 0.0 on failure.
    committed_spend may be slightly over-reserved for failed EL retries; this
    is conservative and corrects itself on script restart.

    Returns a dict with keys:
        raw, http_status, error_type, error_message, latency_ms,
        retry_count, detected_lang, request_params, cost_usd
    """
    projected = estimate_cost(float(row["duration_seconds"]), "elevenlabs")

    request_params = {"model_id": EL_MODEL}
    if condition == "hint":
        request_params["language_code"] = hint_value  # ISO-639-1: "uz" or "kk"

    raw            = None
    http_status    = None
    error_type     = None
    error_message  = None
    detected_lang  = None
    attempts_made  = 0
    t0             = time.monotonic()

    for attempt in range(MAX_RETRIES):
        # Cap check before every attempt (conservative: reserves even if EL won't bill on failure)
        try:
            check_and_reserve(projected,
                              f"ElevenLabs {row['utterance_id']} {condition} attempt={attempt}")
        except CapExceeded as e:
            latency_ms = round((time.monotonic() - t0) * 1000)
            return {
                "raw": None, "http_status": None,
                "error_type": "CapAborted", "error_message": str(e),
                "latency_ms": latency_ms, "retry_count": attempt,
                "detected_lang": None, "request_params": request_params,
                "cost_usd": 0.0,  # EL not billed; check_and_reserve already incremented committed_spend
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
                    f"ElevenLabs response missing expected 'text' field; "
                    f"SDK may have changed schema. Got type={type(result).__name__}. "
                    f"Public attrs: {[a for a in dir(result) if not a.startswith('_')]}"
                )
            raw           = result.text
            detected_lang = getattr(result, "language_code", None)
            http_status   = 200
            error_type    = None
            error_message = None
            break
        except Exception as e:
            error_message = str(e)
            error_type    = type(e).__name__
            http_status   = None
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)  # 1s, 2s between attempts

    latency_ms = round((time.monotonic() - t0) * 1000)
    # ElevenLabs bills only for successful transcriptions
    cost_usd = projected if raw is not None else 0.0

    return {
        "raw": raw, "http_status": http_status,
        "error_type": error_type, "error_message": error_message,
        "latency_ms": latency_ms, "retry_count": attempts_made - 1,
        "detected_lang": detected_lang, "request_params": request_params,
        "cost_usd": cost_usd,
    }


# ---------------------------------------------------------------------------
# Google Cloud STT Chirp 2 — single utterance/condition call
# ---------------------------------------------------------------------------
def call_gcs(row: dict, condition: str, hint_value, gcs_client, project_id: str) -> dict:
    """
    Execute one GCS Chirp 2 STT call with retry and cap enforcement.

    Cap enforcement: check_and_reserve is called before EVERY attempt because
    GCS bills per network call regardless of success or failure. cost_usd in
    the returned dict equals projected * attempts_made (total GCS billing for
    this utterance/condition).

    detected_lang is populated from result.language_code (GCS V2 response field).
    This was confirmed absent in the micro-pilot pre-fix; the fix is present here.
    """
    from google.cloud.speech_v2.types import cloud_speech
    from google.api_core import exceptions as gapi_exceptions

    RECOGNIZER = f"projects/{project_id}/locations/{GCS_REGION}/recognizers/_"
    projected  = estimate_cost(float(row["duration_seconds"]), "google_cloud_stt")

    if condition == "hint":
        language_codes = [hint_value]  # BCP-47: "uz-UZ" or "kk-KZ"
    else:
        language_codes = ["auto"]

    request_params = {
        "model": GCS_MODEL, "region": GCS_REGION, "language_codes": language_codes
    }

    # Read audio bytes once; reused across all retry attempts
    with open(row["canonical_audio_path"], "rb") as f:
        audio_bytes = f.read()

    raw           = None
    http_status   = None
    error_type    = None
    error_message = None
    detected_lang = None
    total_cost    = 0.0
    t0            = time.monotonic()

    for attempt in range(MAX_RETRIES):
        # Cap check before every GCS attempt — GCS bills this regardless of outcome
        try:
            check_and_reserve(projected,
                              f"GCS {row['utterance_id']} {condition} attempt={attempt}")
        except CapExceeded as e:
            latency_ms = round((time.monotonic() - t0) * 1000)
            return {
                "raw": None, "http_status": None,
                "error_type": "CapAborted", "error_message": str(e),
                "latency_ms": latency_ms, "retry_count": attempt,
                "detected_lang": None, "request_params": request_params,
                "cost_usd": total_cost,  # cost accumulated up to this abort
            }

        total_cost += projected  # this attempt will be billed by GCS regardless of outcome

        try:
            config  = cloud_speech.RecognitionConfig(
                auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
                language_codes=language_codes,
                model=GCS_MODEL,
            )
            req = cloud_speech.RecognizeRequest(
                recognizer=RECOGNIZER,
                config=config,
                content=audio_bytes,
            )
            response = gcs_client.recognize(request=req)

            parts = []
            for result in response.results:
                if result.alternatives:
                    parts.append(result.alternatives[0].transcript)
                # Extract detected language from GCS V2 result (field added in micro-pilot fix)
                if result.language_code:
                    detected_lang = result.language_code

            raw           = " ".join(parts) if parts else ""
            http_status   = 200
            error_type    = None
            error_message = None
            break

        except gapi_exceptions.GoogleAPICallError as e:
            error_message = str(e)
            error_type    = type(e).__name__
            http_status   = getattr(e, 'code', None)
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
        except Exception as e:
            error_message = str(e)
            error_type    = type(e).__name__
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)

    latency_ms = round((time.monotonic() - t0) * 1000)
    return {
        "raw": raw, "http_status": http_status,
        "error_type": error_type, "error_message": error_message,
        "latency_ms": latency_ms,
        "retry_count": min(attempt, MAX_RETRIES - 1),
        "detected_lang": detected_lang, "request_params": request_params,
        "cost_usd": total_cost,  # sum of all GCS billing events for this call
    }


# ---------------------------------------------------------------------------
# Run one provider across all 600 utterances
# ---------------------------------------------------------------------------
def run_provider(
    rows: list,
    provider: str,
    done: set,
    el_client=None,
    gcs_client=None,
    project_id: str = "",
) -> None:
    model = EL_MODEL if provider == "elevenlabs" else GCS_MODEL
    total_calls = len(rows) * 2  # 2 conditions
    completed = skipped = 0

    print(f"\n{'─' * 72}")
    print(f"Provider : {provider}   Model: {model}")
    print(f"Calls    : {total_calls} ({len(rows)} utterances × 2 conditions)")
    print(f"Committed: ${committed_spend:.5f} / ${HARD_CAP:.2f} at provider start")
    print(f"{'─' * 72}")

    for i, row in enumerate(rows):
        for condition in ("auto", "hint"):
            key = (row["utterance_id"], provider, condition)

            # Deduplication: skip already-successful combinations
            if key in done:
                skipped += 1
                continue

            # Derive hint_value (the value stored in language_hint field and sent to provider)
            if condition == "hint":
                hint_value = row["language"] if provider == "elevenlabs" \
                    else LANG_BCP47[row["language"]]
            else:
                hint_value = None

            # Dispatch to provider-specific call function
            if provider == "elevenlabs":
                result = call_elevenlabs(row, condition, hint_value, el_client)
            else:
                result = call_gcs(row, condition, hint_value, gcs_client, project_id)

            record = make_record(
                row=row,
                provider=provider,
                model=model,
                condition=condition,
                hint_value=hint_value,
                raw_transcription=result["raw"],
                http_status=result["http_status"],
                error_type=result["error_type"],
                error_message=result["error_message"],
                latency_ms=result["latency_ms"],
                cost_usd=result["cost_usd"],
                retry_count=result["retry_count"],
                request_params=result["request_params"],
                provider_detected_language=result["detected_lang"],
            )
            write_record(record)

            # Hard abort on cap breach — record was written for audit trail
            if result["error_type"] == "CapAborted":
                print(f"\nABORT: Hard cap ${HARD_CAP:.2f} enforced before "
                      f"{row['utterance_id']} {condition}.")
                print(f"  committed_spend at abort: ${committed_spend:.5f}")
                print(f"  Restart the script to resume (dedup will skip completed calls).")
                sys.exit(1)

            if result["error_type"] is None:
                done.add(key)
            completed += 1

            status_str = "OK" if result["error_type"] is None else f"ERR({result['error_type']})"
            wer_str    = f"WER={record['wer']:.3f}" if record['wer'] is not None else "WER=N/A"
            print(
                f"  [{condition:4s}] {row['utterance_id'][:22]:22s}"
                f"  {status_str:22s}  {wer_str}  {result['latency_ms']:5d}ms"
                f"  ${result['cost_usd']:.5f}  total=${committed_spend:.4f}"
            )

        # Progress summary every 50 utterances
        if (i + 1) % 50 == 0:
            pct = 100 * committed_spend / HARD_CAP
            print(
                f"  ── progress: {i+1}/{len(rows)} utterances  "
                f"committed=${committed_spend:.4f}/${HARD_CAP:.2f} ({pct:.1f}%) ──"
            )

    print(f"\n  {provider}: {completed} calls executed, {skipped} skipped (already done)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    global committed_spend

    sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 72)
    print(f"Phase 2 Track B Benchmark")
    print(f"run_id           = {RUN_ID}")
    print(f"benchmark_version= {BENCHMARK_VERSION}")
    print(f"hard_cap         = ${HARD_CAP:.2f}")
    print(f"max_retries      = {MAX_RETRIES}")
    print(f"output           = {RESULTS_FILE}")
    print("=" * 72)
    print()

    # 1. Load and verify frozen manifest
    rows = load_and_verify_manifest()

    # 2. Load prior run state (restart safety)
    prior_spend, done = load_state()
    committed_spend = prior_spend

    if prior_spend > 0:
        print(f"\nResuming prior run:")
        print(f"  Prior committed spend : ${prior_spend:.5f}")
        print(f"  Completed combinations: {len(done)}")
        if prior_spend >= HARD_CAP:
            print(f"\nABORT: prior committed spend ${prior_spend:.5f} already at or above "
                  f"hard cap ${HARD_CAP:.2f}. No budget remaining.")
            sys.exit(1)
        print(f"  Remaining budget      : ${HARD_CAP - prior_spend:.5f}")
    else:
        print("\nStarting fresh run (no prior results file).")
    print()

    # 3. Preflight checks (no API calls)
    print("Preflight checks:")
    if not preflight(rows):
        print("\nABORT: Fix preflight failures before running.", file=sys.stderr)
        sys.exit(1)
    print("Preflight: PASS\n")

    # 4. Write run manifest (idempotent; overwrites on restart with updated run_id)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    run_meta = {
        "run_id":                  RUN_ID,
        "benchmark_version":       BENCHMARK_VERSION,
        "timestamp_utc":           datetime.now(timezone.utc).isoformat(),
        "hard_cap":                HARD_CAP,
        "manifest_sha256":         MANIFEST_SHA256,
        "utterance_count":         len(rows),
        "providers":               [f"elevenlabs/{EL_MODEL}", f"google_cloud_stt/{GCS_MODEL}"],
        "conditions":              ["auto", "hint"],
        "gcs_region":              GCS_REGION,
        "el_rate_per_min":         EL_RATE_PER_MIN,
        "gcs_rate_per_sec":        GCS_RATE_PER_SEC,
        "gcs_billing_increment_s": GCS_BILLING_INCR_S,
        "prior_committed_spend":   prior_spend,
    }
    RUN_META_FILE.write_text(
        json.dumps(run_meta, indent=2, ensure_ascii=False), encoding='utf-8'
    )
    print(f"Run manifest written: {RUN_META_FILE.name}")

    # 5. Initialise provider clients
    el_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    from elevenlabs import ElevenLabs
    el_client = ElevenLabs(api_key=el_key)

    from google.cloud.speech_v2 import SpeechClient
    gcs_client = SpeechClient(
        client_options={"api_endpoint": f"{GCS_REGION}-speech.googleapis.com"}
    )

    # Derive GCS project_id from credentials file (same logic as micro-pilot)
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    try:
        with open(creds_path, encoding='utf-8') as f:
            project_id = json.load(f).get("project_id", "")
    except Exception:
        project_id = ""
    if not project_id:
        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
    if not project_id:
        print("ABORT: Cannot determine GCS project_id from credentials file or "
              "GOOGLE_CLOUD_PROJECT env var.", file=sys.stderr)
        sys.exit(1)
    print(f"GCS project: {project_id}\n")

    # 6. Execute providers — ElevenLabs first (cheaper, faster feedback), then GCS
    run_provider(rows, "elevenlabs",       done, el_client=el_client)
    run_provider(rows, "google_cloud_stt", done, gcs_client=gcs_client, project_id=project_id)

    # 7. Final summary
    print("\n" + "=" * 72)
    print("Run complete.")
    print(f"Total committed spend: ${committed_spend:.5f} / ${HARD_CAP:.2f} cap")

    if RESULTS_FILE.exists():
        try:
            import pandas as pd
            df = pd.read_json(RESULTS_FILE, lines=True)
            df_v = df[df["benchmark_version"] == BENCHMARK_VERSION]
            ok   = df_v[df_v["error_type"].isna()]
            print(f"\nRecords (this version): {len(df_v)}")
            print(f"Successful            : {len(ok)}")
            print(f"Failed / null         : {len(df_v) - len(ok)}")
            if len(df_v) > 0:
                print(f"Null rate             : {(1 - len(ok) / len(df_v)):.1%}")
            if not ok.empty and "wer" in ok.columns and ok["wer"].notna().any():
                print("\nWER summary (successful records, mean per group):")
                summary = (
                    ok.groupby(["provider", "model", "language", "language_condition"])["wer"]
                    .mean()
                    .reset_index()
                )
                print(summary.to_string(index=False))
            # Aggregation audit
            bad_ok   = ok[ok["wer"].isna() | ok["cer"].isna()]
            bad_fail = df_v[df_v["error_type"].notna() & (df_v["wer"].notna() | df_v["cer"].notna())]
            print(f"\nAggregation audit:")
            print(f"  Successful records with null WER/CER : {len(bad_ok)} (expect 0)")
            print(f"  Failed records with non-null WER/CER : {len(bad_fail)} (expect 0)")
            audit_pass = len(bad_ok) == 0 and len(bad_fail) == 0
            print(f"  Result: {'PASS' if audit_pass else 'FAIL'}")
        except ImportError:
            print("(pandas not installed — skipping summary table)")


if __name__ == "__main__":
    main()
