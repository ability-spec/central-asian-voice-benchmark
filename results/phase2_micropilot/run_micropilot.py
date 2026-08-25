"""
Phase 2 Micro-Pilot Execution Script
4 utterances x 2 conditions x 2 providers = 16 requests maximum

Run ONLY after confirming:
  1. ELEVENLABS_API_KEY is set (for ElevenLabs)
  2. GOOGLE_APPLICATION_CREDENTIALS points to a valid service account key (for GCS)
  3. Estimated spend ($0.046) is within the $2 hard cap

DO NOT modify the frozen benchmark.
DO NOT run the full pilot from this script.
"""

import os
import sys
import json
import time
import math
import hashlib
import unicodedata
import re
import uuid
import traceback
from datetime import datetime, timezone
from pathlib import Path

try:
    import jiwer
except ImportError:
    print("ERROR: jiwer not installed. Run: pip install jiwer")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST_PATH = Path(__file__).parent / "micropilot_manifest.json"
RESULTS_DIR   = Path(__file__).parent
RESULTS_FILE  = RESULTS_DIR / "micropilot_results.jsonl"

# ---------------------------------------------------------------------------
# Normalisation pipeline (methodology_proposal.md §C)
# ---------------------------------------------------------------------------
_PUNCT = re.compile(r"[^\w\s']", re.UNICODE)
_APOS  = re.compile(r"[‘’ʼ`]")
_WS    = re.compile(r'\s+')

def normalise(text):
    if not isinstance(text, str) or not text.strip():
        return ''
    text = unicodedata.normalize('NFC', text)
    text = text.casefold()
    text = _APOS.sub("'", text)
    text = _PUNCT.sub(' ', text)
    text = _WS.sub(' ', text).strip()
    return text

def compute_wer(ref, hyp):
    r, h = normalise(ref), normalise(hyp)
    if not r:
        return None
    return round(jiwer.wer(r, h), 6)

def compute_cer(ref, hyp):
    r, h = normalise(ref), normalise(hyp)
    if not r:
        return None
    return round(jiwer.cer(r, h), 6)

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()

# ---------------------------------------------------------------------------
# Result record builder
# ---------------------------------------------------------------------------
RUN_ID = f"micropilot_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"

def make_record(provider, model, utterance, condition, hint_value,
                raw_transcription, http_status, error_type, error_message,
                latency_ms, cost_usd, retry_count, extra_params=None,
                provider_detected_language=None):
    ref = utterance["reference_transcript"]
    hyp = raw_transcription or ""
    norm_hyp = normalise(hyp) if raw_transcription else None

    audio_path = REPO_ROOT / utterance["canonical_audio_path"]

    return {
        "call_id":                    str(uuid.uuid4()),
        "run_id":                     RUN_ID,
        "benchmark_version":          "phase2_micropilot_v1",
        "timestamp_utc":              datetime.now(timezone.utc).isoformat(),
        "provider":                   provider,
        "model":                      model,
        "language_condition":         condition,
        "language_hint":              hint_value,
        "utterance_id":               utterance["utterance_id"],
        "audio_id":                   utterance["utterance_id"],
        "audio_sha256":               sha256_file(audio_path) if audio_path.exists() else None,
        "audio_duration_s":           utterance["duration_seconds"],
        "language":                   utterance["language"],
        "language_bcp47":             utterance["language_bcp47"],
        "corpus_source":              "ISSAI_USC_v1_murodbek_hf" if utterance["language"] == "uz" else "ISSAI_KSC",
        "contamination_risk":         "MEDIUM",
        "track":                      "B",
        "fleurs_id":                  None,
        "fleurs_subset":              None,
        "reference_transcript":       ref,
        "raw_transcription":          raw_transcription,
        "normalized_transcription":   norm_hyp,
        "wer":                        compute_wer(ref, raw_transcription) if raw_transcription else None,
        "cer":                        compute_cer(ref, raw_transcription) if raw_transcription else None,
        "provider_detected_language": provider_detected_language,
        "independent_detected_language": None,
        "dominant_script":            None,
        "latency_ms":                 latency_ms,
        "http_status":                http_status,
        "error_type":                 error_type,
        "error_message":              error_message,
        "retry_count":                retry_count,
        "cost_usd":                   cost_usd,
        "cost_list_price_usd":        cost_usd,
        "request_params":             extra_params or {},
    }

def append_record(record):
    with open(RESULTS_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')

# ---------------------------------------------------------------------------
# ElevenLabs Scribe v2
# ---------------------------------------------------------------------------
def run_elevenlabs(utterances):
    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        print("  BLOCKED: ELEVENLABS_API_KEY not set")
        return False

    try:
        from elevenlabs import ElevenLabs
    except ImportError:
        print("  BLOCKED: elevenlabs SDK not installed. Run: pip install elevenlabs")
        return False

    client = ElevenLabs(api_key=api_key)
    model_id = "scribe_v2"
    rate_per_min = 0.00367

    print(f"  Provider: ElevenLabs  Model: {model_id}")

    for utterance in utterances:
        audio_path = REPO_ROOT / utterance["canonical_audio_path"]

        for condition in ("auto", "hint"):
            if condition == "hint":
                hint_value = utterance["language"]  # "uz" or "kk"
            else:
                hint_value = None

            # Record only the parameters actually sent to the SDK (omit means not sent)
            params = {"model_id": model_id}
            if condition == "hint":
                params["language_code"] = hint_value

            t0 = time.monotonic()
            raw, http_status, error_type, error_message, retry_count = None, 200, None, None, 0
            detected_lang = None

            for attempt in range(3):
                retry_count = attempt
                try:
                    with open(audio_path, "rb") as audio_file:
                        kwargs = {"model_id": model_id}
                        if condition == "hint":
                            kwargs["language_code"] = hint_value
                        result = client.speech_to_text.convert(
                            file=audio_file,
                            **kwargs
                        )
                    raw = result.text if hasattr(result, "text") else str(result)
                    detected_lang = getattr(result, "language_code", None)
                    break
                except Exception as e:
                    error_message = str(e)
                    error_type = type(e).__name__
                    http_status = None
                    if attempt < 2:
                        time.sleep(2 ** attempt)

            latency_ms = round((time.monotonic() - t0) * 1000)
            cost_usd = (utterance["duration_seconds"] / 60) * rate_per_min

            record = make_record(
                provider="elevenlabs",
                model=model_id,
                utterance=utterance,
                condition=condition,
                hint_value=hint_value,
                raw_transcription=raw,
                http_status=http_status,
                error_type=error_type,
                error_message=error_message,
                latency_ms=latency_ms,
                cost_usd=round(cost_usd, 6),
                retry_count=retry_count,
                extra_params=params,
                provider_detected_language=detected_lang,
            )
            append_record(record)

            status = "OK" if raw else f"ERROR({error_type})"
            wer_str = f"WER={record['wer']:.3f}" if record['wer'] is not None else "WER=N/A"
            print(f"    [{condition:4s}] {utterance['utterance_id']}  {status}  {wer_str}  {latency_ms}ms")

    return True

# ---------------------------------------------------------------------------
# Google Cloud STT Chirp 2
# ---------------------------------------------------------------------------
def run_gcs_chirp2(utterances):
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if not creds_path:
        print("  BLOCKED: GOOGLE_APPLICATION_CREDENTIALS not set")
        return False
    if not os.path.exists(creds_path):
        print(f"  BLOCKED: credentials file not found: {creds_path}")
        return False

    try:
        from google.cloud.speech_v2 import SpeechClient
        from google.cloud.speech_v2.types import cloud_speech
        from google.api_core import exceptions as gapi_exceptions
    except ImportError:
        print("  BLOCKED: google-cloud-speech not installed. Run: pip install google-cloud-speech")
        return False

    # Project ID is required for V2 API
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
    if not project_id:
        # Try to read from credentials file
        try:
            with open(creds_path) as f:
                creds_data = json.load(f)
            project_id = creds_data.get("project_id", "")
        except Exception:
            pass
    if not project_id:
        print("  BLOCKED: GOOGLE_CLOUD_PROJECT not set and could not read from credentials file")
        return False

    REGION = "asia-southeast1"
    MODEL  = "chirp_2"
    RECOGNIZER = f"projects/{project_id}/locations/{REGION}/recognizers/_"
    RATE_PER_SEC = 0.00035

    print(f"  Provider: Google Cloud STT  Model: {MODEL}  Region: {REGION}")

    client = SpeechClient(client_options={"api_endpoint": f"{REGION}-speech.googleapis.com"})

    for utterance in utterances:
        audio_path = REPO_ROOT / utterance["canonical_audio_path"]
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()

        for condition in ("auto", "hint"):
            if condition == "hint":
                hint_value = utterance["language_bcp47"]  # "uz-UZ" or "kk-KZ"
                language_codes = [hint_value]
            else:
                hint_value = None
                language_codes = ["auto"]

            params = {
                "model": MODEL,
                "region": REGION,
                "language_codes": language_codes,
            }

            t0 = time.monotonic()
            raw, http_status, error_type, error_message, retry_count = None, 200, None, None, 0

            for attempt in range(3):
                retry_count = attempt
                try:
                    config = cloud_speech.RecognitionConfig(
                        auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
                        language_codes=language_codes,
                        model=MODEL,
                    )
                    request = cloud_speech.RecognizeRequest(
                        recognizer=RECOGNIZER,
                        config=config,
                        content=audio_bytes,
                    )
                    response = client.recognize(request=request)
                    parts = []
                    detected_lang = None
                    for result in response.results:
                        if result.alternatives:
                            parts.append(result.alternatives[0].transcript)
                        if result.language_code:
                            detected_lang = result.language_code
                    raw = " ".join(parts) if parts else ""
                    break
                except gapi_exceptions.GoogleAPICallError as e:
                    error_message = str(e)
                    error_type = type(e).__name__
                    http_status = getattr(e, 'code', None)
                    if attempt < 2:
                        time.sleep(2 ** attempt)
                except Exception as e:
                    error_message = str(e)
                    error_type = type(e).__name__
                    if attempt < 2:
                        time.sleep(2 ** attempt)

            latency_ms = round((time.monotonic() - t0) * 1000)
            billed_s = math.ceil(utterance["duration_seconds"] / 15) * 15
            cost_usd = billed_s * RATE_PER_SEC

            record = make_record(
                provider="google_cloud_stt",
                model=MODEL,
                utterance=utterance,
                condition=condition,
                hint_value=hint_value,
                raw_transcription=raw,
                http_status=http_status,
                error_type=error_type,
                error_message=error_message,
                latency_ms=latency_ms,
                cost_usd=round(cost_usd, 6),
                retry_count=retry_count,
                extra_params=params,
                provider_detected_language=detected_lang,
            )
            append_record(record)

            status = "OK" if (raw is not None and error_type is None) else f"ERROR({error_type})"
            wer_str = f"WER={record['wer']:.3f}" if record['wer'] is not None else "WER=N/A"
            print(f"    [{condition:4s}] {utterance['utterance_id']}  {status}  {wer_str}  {latency_ms}ms")

    return True

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print(f"=== Phase 2 Micro-Pilot  run_id={RUN_ID} ===")
    print(f"Hard cap: $2.00  Estimated spend: $0.046 (2 providers)")
    print(f"Results file: {RESULTS_FILE}")
    print()

    with open(MANIFEST_PATH, encoding='utf-8') as f:
        manifest = json.load(f)
    utterances = manifest["utterances"]

    # Pre-flight: verify all audio files exist
    missing = []
    for u in utterances:
        p = REPO_ROOT / u["canonical_audio_path"]
        if not p.exists():
            missing.append(str(p))
    if missing:
        print("ABORT: missing audio files:")
        for m in missing:
            print(f"  {m}")
        sys.exit(1)
    print(f"Audio files: {len(utterances)}/{len(utterances)} present")
    print()

    # Azure: skip — pricing NEEDS_VERIFICATION
    print("Azure Fast Transcription: SKIPPED — pricing not yet verified")
    # Gemini: skip — no API key
    gemini_key = os.environ.get("GOOGLE_API_KEY", "").strip() or os.environ.get("GEMINI_API_KEY", "").strip()
    if not gemini_key:
        print("Gemini 2.5 Flash: SKIPPED — no GOOGLE_API_KEY or GEMINI_API_KEY in environment")
    print()

    results = {}

    print("--- ElevenLabs Scribe v2 ---")
    results["elevenlabs"] = run_elevenlabs(utterances)
    print()

    print("--- Google Cloud STT Chirp 2 ---")
    results["google_cloud_stt"] = run_gcs_chirp2(utterances)
    print()

    # Summary
    print("=== SUMMARY ===")
    for provider, success in results.items():
        status = "RAN" if success else "BLOCKED"
        print(f"  {provider}: {status}")

    if RESULTS_FILE.exists():
        import pandas as pd
        df = pd.read_json(RESULTS_FILE, lines=True)
        print(f"\nRecords written: {len(df)}")
        if 'wer' in df.columns and df['wer'].notna().any():
            print("\nWER summary:")
            print(df.groupby(['provider', 'model', 'language', 'language_condition'])['wer']
                    .mean().reset_index().to_string(index=False))
        if 'cost_usd' in df.columns:
            print(f"\nActual total spend: ${df['cost_usd'].sum():.5f}")
    else:
        print("\nNo results written (all providers blocked).")

if __name__ == "__main__":
    main()
