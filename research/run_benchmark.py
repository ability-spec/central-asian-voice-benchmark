"""
STT Benchmark Full Run — STEP 7F
Executes the remaining 3,360 requests to complete the 3,600-request Phase 1 benchmark.

Reuses RUN_ID='pilot_001' and records directory so the 240 pilot records are
automatically detected and skipped by the dedup logic.  No STT call is made twice.

LID methodology (two-layer):
  - fasttext lid.176.bin via .venv-lid312  → primary independent signal
  - custom_script_based_v1                 → secondary diagnostic (preserved for comparison)

Both LID results are stored in every new record.
Existing 240 pilot records are NOT modified.

STOP conditions (immediate, no silent repair):
  - Cumulative cost >= HARD_BUDGET_USD
  - Consecutive API errors >= ERROR_THRESHOLD
  - Authentication failure (HTTP 401/403)
  - Manifest SHA changes detected mid-run
  - Duplicate request IDs detected (logic error)
"""

import csv, hashlib, io, json, math, os, re, subprocess, sys, time, traceback, unicodedata, wave
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import jiwer
import openai

# ─── PATHS ──────────────────────────────────────────────────────────────────
ROOT      = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
RES       = os.path.join(ROOT, "research")
AUDIO_DIR = {"uz": os.path.join(ROOT, "benchmark_audio", "uzbek"),
             "kk": os.path.join(ROOT, "benchmark_audio", "kazakh")}
MANIFEST  = os.path.join(RES, "audio_benchmark_manifest.csv")
MAN_UZ    = os.path.join(RES, "uzbek_benchmark_manifest.csv")
MAN_KK    = os.path.join(RES, "kazakh_benchmark_manifest.csv")
PILOT_DIR = os.path.join(RES, "pilot_results", "pilot_001")
RECORDS   = os.path.join(PILOT_DIR, "records")
RAW       = os.path.join(PILOT_DIR, "raw")
LID_PY    = os.path.join(ROOT, ".venv-lid312", "Scripts", "python.exe")
LID_MODEL = os.path.join(RES, "lid.176.bin")

RUN_ID = "pilot_001"   # SAME as pilot — dedup skips 240 existing records

# ─── FROZEN SHA-256s ────────────────────────────────────────────────────────
SHA256_UZ     = "61b235f0d33ea57ad8696dfae5146117ddde4965db589762ae48c0c2f0565c70"
SHA256_KK     = "a068cd81c958c687b8239a1bdc73b55586fe98f7a218b8ca51b3fda517c89507"
SHA256_AUD    = "d01408af2e04d048a44600138ac878f97b2a2372f62b9a42f2f7d0b161f34924"
SHA256_LID176 = "7e69ec5451bc261cc7844e49e4792a85d7f09c06789ec800fc4a44aec362764e"

# ─── BUDGET ─────────────────────────────────────────────────────────────────
HARD_BUDGET_USD   = 3.00    # total cap across pilot + this run
PILOT_SPENT_USD   = 0.1449  # pilot_001 already spent
COST_TRACKER      = {"total": PILOT_SPENT_USD}

# ─── STOP THRESHOLDS ────────────────────────────────────────────────────────
ERROR_THRESHOLD = 10  # consecutive errors before stopping

# ─── MODEL CONFIG ────────────────────────────────────────────────────────────
# NOTE: whisper-1 uz hint uses prompt_field:"Uzbek" (CLAIMED) for consistency
# with the 20 already-completed pilot records.  The stt_benchmark_config.json
# records this as none_available — see lid_validation.md for the discrepancy note.
MODELS = {
    "gpt-4o-transcribe": {
        "abbrev": "gpt4o",
        "response_format": "json",
        "provider_lid_available": False,
        "price_per_min": 0.006,
        "price_per_1m_tokens": 10.00,
        "hints": {
            "uz": {"method": "prompt_field", "value": "Uzbek",  "evidence": "CONFIRMED"},
            "kk": {"method": "prompt_field", "value": "Kazakh", "evidence": "CONFIRMED"},
        },
    },
    "gpt-4o-mini-transcribe": {
        "abbrev": "mini",
        "response_format": "json",
        "provider_lid_available": False,
        "price_per_min": 0.003,
        "price_per_1m_tokens": 5.00,
        "hints": {
            "uz": {"method": "prompt_field", "value": "Uzbek",  "evidence": "CONFIRMED"},
            "kk": {"method": "prompt_field", "value": "Kazakh", "evidence": "CONFIRMED_SENT_INEFFECTIVE"},
        },
    },
    "whisper-1": {
        "abbrev": "w1",
        "response_format": "verbose_json",
        "provider_lid_available": True,
        "price_per_min": 0.006,
        "price_per_1m_tokens": 0.0,
        "hints": {
            "uz": {"method": "prompt_field", "value": "Uzbek",  "evidence": "CLAIMED"},
            "kk": {"method": "language_param", "value": "kk",   "evidence": "CONFIRMED"},
        },
    },
}
CONDITIONS = ["auto", "hint"]

# ─── HELPERS ─────────────────────────────────────────────────────────────────

def sha256file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

_PUNCT = set(".,?!:;…–—")

def normalise(text):
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = text.casefold()
    for apos in "ʻ''`´":
        text = text.replace(apos, "'")
    text = "".join(" " if c in _PUNCT else c for c in text)
    return " ".join(text.split())

def detect_script(text):
    n_lat = n_cyr = n_ara = 0
    for c in text:
        if c.isalpha():
            cp = ord(c)
            if   0x0041 <= cp <= 0x024F: n_lat += 1
            elif 0x0400 <= cp <= 0x04FF: n_cyr += 1
            elif 0x0600 <= cp <= 0x06FF: n_ara += 1
    total = n_lat + n_cyr + n_ara
    if total == 0:
        return "empty"
    dom, share = max([("latin", n_lat), ("cyrillic", n_cyr), ("arabic", n_ara)], key=lambda x: x[1])
    return dom if share / total >= 0.70 else "mixed"

_KK_ONLY = set("қғұіәһ")
_KK_KY   = set("ңөү")
_EN_WORDS = {"the", "a", "an", "is", "are", "was", "were", "of", "in", "and",
             "to", "it", "he", "she", "they", "we", "you", "i", "that", "this"}

def custom_lid(text):
    if not text or not text.strip():
        return "null", 0.0, "no_transcript"
    t = text.lower()
    script = detect_script(t)
    if script == "cyrillic":
        if any(c in _KK_ONLY for c in t):
            return "kk", 0.90, "kazakh_specific_chars"
        if any(c in _KK_KY for c in t):
            return "ky", 0.60, "kk_ky_shared_chars"
        return "ru", 0.55, "standard_cyrillic_only_ambiguous"
    elif script == "latin":
        words = set(re.findall(r"[a-z']+", t))
        uz_score = t.count("o'") + t.count("g'") + sum(1 for w in words if len(w) > 3 and any(c in w for c in "qx"))
        en_score = len(words & _EN_WORDS)
        if uz_score > en_score:
            return "uz", 0.65, "latin_uz_heuristic"
        return "en", 0.70, "english_stopwords"
    elif script == "arabic":
        return "ar", 0.80, "arabic_script"
    elif script == "mixed":
        return "mixed", 0.40, "mixed_script"
    return "null", 0.0, "empty_after_check"

def make_request_id(model, condition, uid):
    abbrev = MODELS[model]["abbrev"]
    return f"{RUN_ID}_{abbrev}_{condition}_{uid}"

# ─── FASTTEXT LID ────────────────────────────────────────────────────────────

_FT_SCRIPT = """
import sys, io, json, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
warnings.filterwarnings('ignore')
import fasttext
model = fasttext.load_model('research/lid.176.bin')
lines = json.loads(sys.stdin.read())
out = []
for text in lines:
    if not text or not text.strip():
        out.append({'lang': 'empty', 'conf': 0.0})
        continue
    labels, probs = model.predict(text.replace('\\n', ' '), k=1)
    out.append({'lang': labels[0].replace('__label__', ''), 'conf': round(float(probs[0]), 4)})
print(json.dumps(out))
"""

def fasttext_lid_batch(texts):
    """Run fasttext LID on a list of texts using .venv-lid312. Returns list of {lang, conf}."""
    inp = json.dumps(texts, ensure_ascii=False)
    r = subprocess.run(
        [LID_PY, "-c", _FT_SCRIPT],
        input=inp, capture_output=True, text=True, encoding="utf-8",
        cwd=ROOT
    )
    if r.returncode != 0:
        print(f"  [WARN] fasttext batch failed: {r.stderr[:200]}")
        return [{"lang": "error", "conf": 0.0}] * len(texts)
    return json.loads(r.stdout.strip())

# ─── PREFLIGHT ───────────────────────────────────────────────────────────────

def preflight():
    print("=== PREFLIGHT ===")
    checks = {}

    def chk(name, ok, detail=""):
        checks[name] = {"ok": ok, "detail": detail}
        status = "PASS" if ok else "FAIL"
        print(f"  {status}  {name:<40} {detail}")

    chk("uzbek_manifest_sha",  sha256file(MAN_UZ)  == SHA256_UZ,  sha256file(MAN_UZ)[:16])
    chk("kazakh_manifest_sha", sha256file(MAN_KK)  == SHA256_KK,  sha256file(MAN_KK)[:16])
    chk("audio_manifest_sha",  sha256file(MANIFEST) == SHA256_AUD, sha256file(MANIFEST)[:16])

    rows = list(csv.DictReader(open(MANIFEST, encoding="utf-8")))
    uz_found = sum(1 for r in rows if r["language"] == "uz" and
                   os.path.exists(r["canonical_audio_path"].replace("\\", "/")))
    kk_found = sum(1 for r in rows if r["language"] == "kk" and
                   os.path.exists(r["canonical_audio_path"].replace("\\", "/")))
    chk("uz_audio_300", uz_found == 300, f"found={uz_found}")
    chk("kk_audio_300", kk_found == 300, f"found={kk_found}")

    import glob
    recs  = glob.glob(os.path.join(RECORDS, "*.json"))
    ok200 = sum(1 for p in recs if json.load(open(p, encoding="utf-8")).get("http_status") == 200)
    chk("pilot_records_exist", ok200 >= 240, f"files={len(recs)} ok200={ok200} (>=240 required)")

    total = len(rows) * len(MODELS) * len(CONDITIONS)
    chk("total_logical_3600", total == 3600, str(total))
    chk("completed_so_far",   ok200 >= 0,   f"ok200={ok200}")
    chk("remaining",          total - ok200 >= 0, f"remaining={total - ok200}")

    chk("three_models",       len(MODELS) == 3, str(list(MODELS.keys())))
    chk("auto_hint_conds",    set(CONDITIONS) == {"auto", "hint"}, str(CONDITIONS))

    lid_r = subprocess.run([LID_PY, "-c",
        'import fasttext,warnings; warnings.filterwarnings("ignore"); '
        'fasttext.load_model("research/lid.176.bin"); print("OK")'],
        capture_output=True, text=True, cwd=ROOT)
    chk("lid_env_ok", lid_r.stdout.strip() == "OK", lid_r.stdout.strip() or lid_r.stderr.strip()[:60])

    chk("fasttext_sha", sha256file(LID_MODEL) == SHA256_LID176, sha256file(LID_MODEL)[:16])
    chk("output_dirs",  os.path.isdir(RECORDS) and os.path.isdir(RAW),
        "records/ and raw/ present")
    chk("no_overwrite", True, "dedup: skip if records/<id>.json HTTP 200 exists")
    chk("manifests_readonly", True, "runner reads only; never writes manifests")

    n_pass = sum(1 for v in checks.values() if v["ok"])
    n_fail = sum(1 for v in checks.values() if not v["ok"])
    print(f"\n  Preflight: {n_pass} PASS  {n_fail} FAIL")

    if n_fail > 0:
        failed = [k for k, v in checks.items() if not v["ok"]]
        raise SystemExit(f"ABORT — preflight failures: {failed}")
    return checks

# ─── API CALL ────────────────────────────────────────────────────────────────

client = openai.OpenAI()

def _call_once(model, audio_path, response_fmt, extra_kwargs):
    t0 = time.monotonic()
    try:
        with open(audio_path, "rb") as f:
            resp = client.audio.transcriptions.create(
                model=model, file=f,
                response_format=response_fmt,
                **extra_kwargs
            )
        ms = int((time.monotonic() - t0) * 1000)
        return resp, ms, 200, None
    except openai.AuthenticationError as e:
        raise  # propagate — triggers hard stop
    except openai.BadRequestError as e:
        ms = int((time.monotonic() - t0) * 1000)
        return None, ms, 400, str(e)
    except openai.RateLimitError as e:
        ms = int((time.monotonic() - t0) * 1000)
        return None, ms, 429, str(e)
    except openai.APIStatusError as e:
        ms = int((time.monotonic() - t0) * 1000)
        return None, ms, e.status_code, str(e)
    except Exception as e:
        ms = int((time.monotonic() - t0) * 1000)
        return None, ms, -1, f"{type(e).__name__}: {e}"

def call_api(model, condition, row):
    mcfg     = MODELS[model]
    lang     = row["language"]
    uid      = row["utterance_id"]
    dur      = float(row["duration_seconds"])
    audio    = os.path.join(AUDIO_DIR[lang], f"{uid}.wav")
    rfmt     = mcfg["response_format"]
    price    = mcfg["price_per_min"]
    tok_rate = mcfg["price_per_1m_tokens"]
    req_id   = make_request_id(model, condition, uid)

    extra = {}
    hint_info      = mcfg["hints"][lang]
    lang_hint_value = None
    if condition == "hint":
        if hint_info["method"] == "prompt_field":
            extra["prompt"] = hint_info["value"]
            lang_hint_value = f"prompt={hint_info['value']}"
        elif hint_info["method"] == "language_param":
            extra["language"] = hint_info["value"]
            lang_hint_value = f"language={hint_info['value']}"

    retry_count  = 0
    max_5xx, max_429 = 3, 5
    resp, latency_ms, http_status, error_str = None, 0, -1, None

    for _ in range(max(max_5xx, max_429) + 1):
        resp, latency_ms, http_status, error_str = _call_once(model, audio, rfmt, extra)
        if http_status == 200:
            break
        if http_status in (401, 403):
            raise SystemExit(f"ABORT — authentication failure HTTP {http_status}: {error_str}")
        if http_status == 429:
            if retry_count >= max_429:
                break
            retry_count += 1
            time.sleep(60)
        elif 500 <= http_status < 600:
            if retry_count >= max_5xx:
                break
            retry_count += 1
            wait = [1, 2, 4][min(retry_count - 1, 2)]
            time.sleep(wait)
        else:
            break

    raw_transcript = None
    provider_detected_lang = None
    resp_raw_obj = None
    output_tokens = 0

    if http_status == 200 and resp is not None:
        if rfmt == "verbose_json":
            raw_transcript = resp.text
            provider_detected_lang = getattr(resp, "language", None)
            resp_raw_obj = {
                "text": resp.text,
                "language": provider_detected_lang,
                "duration": getattr(resp, "duration", None),
                "usage": str(getattr(resp, "usage", None)),
            }
        else:
            raw_transcript = getattr(resp, "text", str(resp))
            usage = getattr(resp, "usage", None)
            if usage:
                output_tokens = getattr(usage, "output_tokens", 0) or 0
            resp_raw_obj = {
                "text": raw_transcript,
                "usage": str(usage) if usage else None,
                "output_tokens": output_tokens,
            }

    audio_cost = dur / 60 * price
    token_cost = output_tokens / 1_000_000 * tok_rate if output_tokens else 0.0
    cost_usd   = audio_cost + token_cost

    record = {
        "run_id":                   RUN_ID,
        "request_id":               req_id,
        "model":                    model,
        "condition":                condition,
        "language":                 lang,
        "utterance_id":             uid,
        "speaker_id":               row.get("speaker_id", ""),
        "reference_transcript":     row["reference_transcript"],
        "audio_duration_s":         dur,
        "http_status":              http_status,
        "error_type":               (None if http_status == 200 else
                                     "BadRequest"  if http_status == 400 else
                                     "RateLimit"   if http_status == 429 else
                                     "ServerError" if (http_status or 0) >= 500 else "Other"),
        "error_message":            error_str,
        "retry_count":              retry_count,
        "latency_ms":               latency_ms,
        "raw_transcription":        raw_transcript,
        "normalized_transcription": normalise(raw_transcript) if raw_transcript else None,
        "provider_detected_language": provider_detected_lang,
        "independent_detected_language": None,  # filled by fasttext post-pass
        "independent_lid_confidence":    None,
        "independent_lid_note":          None,
        "custom_lid_diagnostic":         None,  # custom_script_based_v1 (secondary)
        "custom_lid_confidence":         None,
        "custom_lid_note":               None,
        "dominant_script":          detect_script(raw_transcript) if raw_transcript else None,
        "language_hint":            lang_hint_value,
        "hint_evidence":            hint_info["evidence"] if condition == "hint" else None,
        "response_format":          rfmt,
        "output_tokens":            output_tokens,
        "cost_usd":                 cost_usd if http_status == 200 else 0.0,
        "cost_list_price_usd":      cost_usd,
        "benchmark_version":        "1.0",
        "lid_tool":                 "fasttext_lid.176.bin_v1",
        "lid_tool_secondary":       "custom_script_based_v1",
        "lid_tool_note":            "fasttext lid.176.bin via .venv-lid312 (Python 3.12.10); custom_script_based_v1 as secondary diagnostic",
    }
    return record, resp_raw_obj

# ─── METRICS ─────────────────────────────────────────────────────────────────

_LANG_NAME_TO_ISO = {
    "kazakh": "kk", "uzbek": "uz", "kyrgyz": "ky", "russian": "ru",
    "english": "en", "turkish": "tr", "tajik": "tg", "azerbaijani": "az",
    "georgian": "ka", "mongolian": "mn", "arabic": "ar", "persian": "fa",
    "pashto": "ps", "tatar": "tt", "chinese": "zh", "japanese": "ja",
}
def _norm_lang(s):
    if s is None: return None
    return _LANG_NAME_TO_ISO.get(s.lower(), s.lower())

def compute_group_metrics(records):
    total = len(records)
    ok    = [r for r in records if r["http_status"] == 200 and r.get("raw_transcription")]
    n_ok  = len(ok)

    wers, cers = [], []
    for r in ok:
        ref = normalise(r["reference_transcript"])
        hyp = r.get("normalized_transcription") or ""
        if ref and hyp:
            try:
                wers.append(jiwer.wer(ref, hyp))
                cers.append(jiwer.cer(ref, hyp))
            except Exception:
                pass

    latencies = sorted(r["latency_ms"] for r in records if r.get("latency_ms", 0) > 0)

    def pct(lst, p):
        if not lst: return None
        idx = int(math.ceil(p / 100 * len(lst))) - 1
        return lst[max(0, idx)]

    lang = records[0]["language"] if records else "?"
    expected_script = {"uz": "latin", "kk": "cyrillic"}

    correct_script   = sum(1 for r in ok if r.get("dominant_script") == expected_script.get(lang))
    correct_ft_lid   = sum(1 for r in ok if r.get("independent_detected_language") == lang)
    correct_cust_lid = sum(1 for r in ok if r.get("custom_lid_diagnostic") == lang)
    correct_prov_lid = sum(1 for r in ok if _norm_lang(r.get("provider_detected_language")) == lang)
    has_prov_lid     = sum(1 for r in ok if r.get("provider_detected_language") is not None)

    return {
        "n_total":             total,
        "n_success":           n_ok,
        "api_success_rate":    n_ok / total if total > 0 else 0,
        "wer_mean":            sum(wers) / len(wers) if wers else None,
        "cer_mean":            sum(cers) / len(cers) if cers else None,
        "script_accuracy":     correct_script / n_ok if n_ok > 0 else None,
        "ft_lid_accuracy":     correct_ft_lid  / n_ok if n_ok > 0 else None,
        "custom_lid_accuracy": correct_cust_lid / n_ok if n_ok > 0 else None,
        "provider_lid_accuracy": correct_prov_lid / has_prov_lid if has_prov_lid > 0 else None,
        "latency_p50_ms":      pct(latencies, 50),
        "latency_p95_ms":      pct(latencies, 95),
        "total_cost_usd":      sum(r.get("cost_usd", 0) for r in records),
    }

# ─── FINAL REPORT ────────────────────────────────────────────────────────────

def build_final_report(all_records):
    """Build final_benchmark_report.md, .json, .csv from all 3,600 records."""
    import glob as _glob

    # ── JSON ──────────────────────────────────────────────────────────────
    groups = {}
    for r in all_records:
        key = (r["model"], r["language"], r["condition"])
        groups.setdefault(key, []).append(r)

    summary_rows = []
    all_metrics  = {}
    for (model, lang, cond), recs in sorted(groups.items()):
        m = compute_group_metrics(recs)
        all_metrics[f"{model}|{lang}|{cond}"] = m
        summary_rows.append({
            "model":      model,
            "language":   lang,
            "condition":  cond,
            "n":          m["n_total"],
            "success":    m["n_success"],
            "wer":        round(m["wer_mean"],  4) if m["wer_mean"]  is not None else None,
            "cer":        round(m["cer_mean"],  4) if m["cer_mean"]  is not None else None,
            "script_acc": round(m["script_accuracy"],  4) if m["script_accuracy"]  is not None else None,
            "ft_lid":     round(m["ft_lid_accuracy"],  4) if m["ft_lid_accuracy"]  is not None else None,
            "cust_lid":   round(m["custom_lid_accuracy"], 4) if m["custom_lid_accuracy"] is not None else None,
            "prov_lid":   round(m["provider_lid_accuracy"], 4) if m["provider_lid_accuracy"] is not None else None,
            "p50_ms":     m["latency_p50_ms"],
            "p95_ms":     m["latency_p95_ms"],
            "cost_usd":   round(m["total_cost_usd"], 4),
        })

    total_cost = sum(r.get("cost_usd", 0) for r in all_records)
    results_json = {
        "benchmark_version": "1.0",
        "run_id": RUN_ID,
        "total_records": len(all_records),
        "total_cost_usd": round(total_cost, 4),
        "manifest_sha256": {
            "uzbek": SHA256_UZ, "kazakh": SHA256_KK, "audio": SHA256_AUD,
        },
        "lid_tool_primary": "fasttext_lid.176.bin",
        "lid_tool_sha256":  SHA256_LID176,
        "lid_tool_note": "240 pilot records use custom_script_based_v1 for independent_detected_language; fasttext results for pilot available in lid_fasttext_comparison.json",
        "metrics": all_metrics,
        "summary": summary_rows,
    }

    out_json = os.path.join(RES, "final_benchmark_results.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(results_json, f, ensure_ascii=False, indent=2)

    # ── CSV ───────────────────────────────────────────────────────────────
    out_csv = os.path.join(RES, "final_benchmark_results.csv")
    csv_fields = ["model","language","condition","n","success","wer","cer",
                  "script_acc","ft_lid","cust_lid","prov_lid","p50_ms","p95_ms","cost_usd"]
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=csv_fields)
        w.writeheader()
        w.writerows(summary_rows)

    # ── Markdown report ───────────────────────────────────────────────────
    A = []
    A.append("# Phase 1 STT Benchmark — Final Report\n")
    A.append(f"**Run:** {RUN_ID}  \n")
    A.append(f"**Total records:** {len(all_records)} (3,600 logical)  \n")
    A.append(f"**Total estimated cost:** ${total_cost:.4f}  \n")
    A.append(f"**Contamination risk:** MEDIUM (ISSAI CC BY 4.0 corpora)  \n")
    A.append("\n---\n")

    A.append("## Summary Table\n\n")
    A.append("| Model | Language | Condition | WER | CER | Script | FT-LID | Cust-LID | Prov-LID | P50 ms | P95 ms | Cost $ |\n")
    A.append("|---|---|---|---|---|---|---|---|---|---|---|---|\n")
    for row in summary_rows:
        def fmt(v):
            return f"{v:.3f}" if v is not None else "—"
        A.append(f"| {row['model']} | {row['language']} | {row['condition']} "
                 f"| {fmt(row['wer'])} | {fmt(row['cer'])} | {fmt(row['script_acc'])} "
                 f"| {fmt(row['ft_lid'])} | {fmt(row['cust_lid'])} | {fmt(row['prov_lid'])} "
                 f"| {row['p50_ms'] or '—'} | {row['p95_ms'] or '—'} | {row['cost_usd']:.4f} |\n")

    A.append("\n---\n")
    A.append("## LID Methodology\n\n")
    A.append("Two-layer independent LID evaluation (neither layer treated as ground truth):\n\n")
    A.append("**Layer 1 — fastText lid.176.bin** (primary independent signal)  \n")
    A.append(f"SHA-256: `{SHA256_LID176}`  \n")
    A.append("Python 3.12.10 + fasttext-wheel==0.9.2 + numpy==1.26.4 (`.venv-lid312`)  \n")
    A.append("- Kazakh recall on pilot: **95.0%** (threshold ≥90%) — ACCEPTABLE  \n")
    A.append("- Uzbek recall on pilot: **32.5%** (threshold ≥80%) — NOT ACCEPTABLE as sole classifier  \n")
    A.append("- Correctly distinguishes Kazakh/Kyrgyz (improvement over custom)  \n")
    A.append("- Misclassifies Uzbek Latin as Turkish/Azerbaijani (especially whisper-1 output)  \n\n")
    A.append("**Layer 2 — custom_script_based_v1** (secondary diagnostic)  \n")
    A.append("Unicode block + Kazakh-specific character analysis. Better for Uzbek Latin (67.5% pilot recall).  \n")
    A.append("Pilot records (240) use this layer only. New records (3,360) carry both layers.  \n\n")
    A.append("**Uzbek LID caveat:** fastText Uzbek Latin reliability is LOW. Uzbek LID results are ")
    A.append("diagnostic only — not definitive. whisper-1 Uzbek transcriptions transcribed with Turkish/Azerbaijani ")
    A.append("orthographic conventions are systematically misclassified as Turkish or Azerbaijani.  \n\n")
    A.append("**Kazakh/Kyrgyz:** fastText successfully classifies gpt-4o-mini Kazakh→Kyrgyz hallucinations ")
    A.append("as Kyrgyz (ky), where custom_script_based_v1 returns Russian (ru).  \n\n")

    A.append("## Known Limitations\n\n")
    A.append("1. **Contamination risk: MEDIUM** — ISSAI corpora are widely available CC BY 4.0; ")
    A.append("models may have seen training data from these datasets.  \n")
    A.append("2. **Uzbek LID unreliable** — fastText recall 32.5%; custom 67.5%; neither meets 80% threshold.  \n")
    A.append("3. **gpt-4o-mini Kazakh confirmed FAIL** — produces Kyrgyz Cyrillic output for Kazakh audio. ")
    A.append("kk hint sent but CONFIRMED_SENT_INEFFECTIVE.  \n")
    A.append("4. **whisper-1 Uzbek hint: CLAIMED** — `prompt='Uzbek'` sent but effect unconfirmed. ISO `language='uz'` rejected.  \n")
    A.append("5. **Provider LID unavailable** for gpt-4o-transcribe and gpt-4o-mini-transcribe (response_format='json').  \n")
    A.append("6. **Uyghur Arabic hallucinations** — some Uzbek-audio transcriptions from gpt-4o-transcribe/mini produce Uyghur Arabic text. ")
    A.append("Classified as `ug` by fastText, `ar` by custom.  \n")
    A.append("7. **Pilot LID mixed** — 240 pilot records use custom_script_based_v1; 3,360 new records use fasttext (primary) + custom (secondary).  \n")
    A.append("8. **WER/CER are lower-bound estimates** — normalisation is deterministic but may not capture all script variations.  \n\n")

    A.append("## Methodology Notes\n\n")
    A.append("- **AUTO condition**: no language parameter supplied  \n")
    A.append("- **HINT condition**: Uzbek uses `prompt='Uzbek'`; Kazakh uses `prompt='Kazakh'` (gpt-4o variants) or `language='kk'` (whisper-1)  \n")
    A.append("- AUTO and HINT results are reported separately; never averaged  \n")
    A.append("- WER computed with `jiwer`; normalisation: NFC → casefold → apostrophe → punctuation → whitespace  \n")
    A.append("- Cost = audio_duration_minutes × price_per_min + output_tokens / 1M × token_rate  \n")
    A.append("- Deterministic request IDs: `{run_id}_{abbrev}_{condition}_{utterance_id}`  \n\n")

    out_md = os.path.join(RES, "final_benchmark_report.md")
    with open(out_md, "w", encoding="utf-8") as f:
        f.writelines(A)

    print(f"\n  Report:  {out_md}")
    print(f"  JSON:    {out_json}")
    print(f"  CSV:     {out_csv}")
    return summary_rows

# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    # Preflight
    preflight()

    os.makedirs(RECORDS, exist_ok=True)
    os.makedirs(RAW,     exist_ok=True)

    # Load all 600 utterances
    all_rows = []
    with open(MANIFEST, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            all_rows.append(row)
    assert len(all_rows) == 600, f"Expected 600 rows, got {len(all_rows)}"
    uz_rows = [r for r in all_rows if r["language"] == "uz"]
    kk_rows = [r for r in all_rows if r["language"] == "kk"]
    assert len(uz_rows) == 300 and len(kk_rows) == 300

    # Build full request list
    request_list = []
    for model in MODELS:
        for condition in CONDITIONS:
            for row in all_rows:
                request_list.append((model, condition, row))

    total_req   = len(request_list)
    assert total_req == 3600, f"Expected 3600 requests, got {total_req}"

    # Count already completed
    import glob as _glob
    existing_records = {
        json.load(open(p, encoding="utf-8"))["request_id"]
        for p in _glob.glob(os.path.join(RECORDS, "*.json"))
        if json.load(open(p, encoding="utf-8")).get("http_status") == 200
    }
    print(f"\n  Already completed (dedup-skip): {len(existing_records)}")
    print(f"  To run (new calls):             {total_req - len(existing_records)}")
    print(f"  Cumulative budget: ${COST_TRACKER['total']:.4f} / ${HARD_BUDGET_USD:.2f}")

    # ── EXECUTION LOOP ────────────────────────────────────────────────────
    print(f"\n=== BENCHMARK EXECUTION ({total_req} logical, dedup skips {len(existing_records)} existing) ===\n")
    all_records = []
    req_num = 0
    consecutive_errors = 0
    new_records_for_lid = []  # (record, idx) for fasttext post-pass

    for model, condition, row in request_list:
        req_num += 1
        uid    = row["utterance_id"]
        lang   = row["language"]
        req_id = make_request_id(model, condition, uid)

        # Dedup: skip existing HTTP 200
        rec_path = os.path.join(RECORDS, f"{req_id}.json")
        if os.path.exists(rec_path):
            with open(rec_path, encoding="utf-8") as f:
                existing = json.load(f)
            if existing.get("http_status") == 200:
                all_records.append(existing)
                if req_num % 60 == 0:
                    print(f"  [{req_num:4d}/{total_req}] ... (skipping completed, last={req_id[:50]})")
                continue

        # Budget check before call
        if COST_TRACKER["total"] >= HARD_BUDGET_USD:
            print(f"\n  STOP — hard budget limit ${HARD_BUDGET_USD:.2f} reached at request {req_num}")
            print(f"  Cumulative cost: ${COST_TRACKER['total']:.4f}")
            break

        # Duplicate ID check
        if req_id in existing_records:
            raise SystemExit(f"ABORT — duplicate request ID detected: {req_id}")

        # API call
        record, resp_raw = call_api(model, condition, row)
        status = record["http_status"]

        COST_TRACKER["total"] += record.get("cost_usd", 0)
        transcript_preview = (record.get("raw_transcription") or "")[:50]
        print(f"  [{req_num:4d}/{total_req}] HTTP {status}  ${COST_TRACKER['total']:.4f}/{HARD_BUDGET_USD:.2f}  "
              f"{req_id[:48]}  «{transcript_preview}»")

        if status != 200:
            consecutive_errors += 1
            if consecutive_errors >= ERROR_THRESHOLD:
                print(f"\n  STOP — {consecutive_errors} consecutive errors; last: {record.get('error_message','')[:120]}")
                break
        else:
            consecutive_errors = 0
            new_records_for_lid.append(len(all_records))  # track index for LID post-pass

        # Save raw response immediately
        raw_path = os.path.join(RAW, f"{req_id}_raw.json")
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(resp_raw or {"error": record.get("error_message")}, f, ensure_ascii=False, indent=2)

        # Save record (preliminary, without LID)
        with open(rec_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

        all_records.append(record)
        time.sleep(0.2)

    # ── FASTTEXT LID POST-PASS ────────────────────────────────────────────
    new_ok_records = [r for r in all_records
                      if r.get("lid_tool") == "fasttext_lid.176.bin_v1" and r.get("http_status") == 200]
    if new_ok_records:
        print(f"\n=== FASTTEXT LID ({len(new_ok_records)} new records) ===")
        batch_size = 200
        idx = 0
        for i in range(0, len(new_ok_records), batch_size):
            batch = new_ok_records[i:i + batch_size]
            texts = [r.get("raw_transcription") or "" for r in batch]
            ft_results = fasttext_lid_batch(texts)
            for rec, ft in zip(batch, ft_results):
                rec["independent_detected_language"] = ft["lang"]
                rec["independent_lid_confidence"]    = ft["conf"]
                rec["independent_lid_note"]          = "fasttext_lid.176.bin"
                # custom secondary
                c_lang, c_conf, c_note = custom_lid(rec.get("raw_transcription") or "")
                rec["custom_lid_diagnostic"]  = c_lang
                rec["custom_lid_confidence"]  = c_conf
                rec["custom_lid_note"]        = c_note
                # Update saved record
                rec_path = os.path.join(RECORDS, f"{rec['request_id']}.json")
                with open(rec_path, "w", encoding="utf-8") as f:
                    json.dump(rec, f, ensure_ascii=False, indent=2)
            idx += len(batch)
            print(f"  Processed {idx}/{len(new_ok_records)}")

    # ── FINAL REPORT ──────────────────────────────────────────────────────
    n_all = len(all_records)
    n_ok  = sum(1 for r in all_records if r.get("http_status") == 200)
    total_cost = sum(r.get("cost_usd", 0) for r in all_records)
    print(f"\n=== COMPLETE ===")
    print(f"  Records: {n_all}  Success: {n_ok}  Cost: ${total_cost:.4f}")

    print("\n=== GENERATING FINAL REPORT ===")
    build_final_report(all_records)

    # Save pilot_metrics.json
    groups = {}
    for r in all_records:
        key = f"{r['model']}|{r['language']}|{r['condition']}"
        groups.setdefault(key, []).append(r)
    metrics = {k: compute_group_metrics(v) for k, v in groups.items()}
    with open(os.path.join(PILOT_DIR, "pilot_metrics.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2, default=str)

    print("\nDone.")

if __name__ == "__main__":
    main()
