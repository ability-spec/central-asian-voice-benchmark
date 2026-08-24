"""
Post-processing: fasttext LID + final report generation.
All 3,600 API calls are already complete. This script:
  1. Runs fasttext LID on the 3,360 new records (lid_tool=fasttext_lid.176.bin_v1)
  2. Runs custom_script_based_v1 on those same records as secondary diagnostic
  3. Saves updated records in-place
  4. Generates final_benchmark_report.md, final_benchmark_results.json, final_benchmark_results.csv
Does NOT make any API calls.
"""

import csv, glob, io, json, math, os, re, subprocess, sys, unicodedata
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import jiwer

ROOT      = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
RES       = os.path.join(ROOT, "research")
PILOT_DIR = os.path.join(RES, "pilot_results", "pilot_001")
RECORDS   = os.path.join(PILOT_DIR, "records")
LID_PY    = os.path.join(ROOT, ".venv-lid312", "Scripts", "python.exe")
LID_MODEL = os.path.join(RES, "lid.176.bin")

RUN_ID        = "pilot_001"
SHA256_UZ     = "61b235f0d33ea57ad8696dfae5146117ddde4965db589762ae48c0c2f0565c70"
SHA256_KK     = "a068cd81c958c687b8239a1bdc73b55586fe98f7a218b8ca51b3fda517c89507"
SHA256_AUD    = "d01408af2e04d048a44600138ac878f97b2a2372f62b9a42f2f7d0b161f34924"
SHA256_LID176 = "7e69ec5451bc261cc7844e49e4792a85d7f09c06789ec800fc4a44aec362764e"

# ─── HELPERS ────────────────────────────────────────────────────────────────

_PUNCT = set(".,?!:;…–—")

def normalise(text):
    if not text: return ""
    text = unicodedata.normalize("NFC", text)
    text = text.casefold()
    for apos in "ʻ''`´": text = text.replace(apos, "'")
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
    if total == 0: return "empty"
    dom, share = max([("latin",n_lat),("cyrillic",n_cyr),("arabic",n_ara)], key=lambda x:x[1])
    return dom if share/total >= 0.70 else "mixed"

_KK_ONLY = set("қғұіәһ")
_KK_KY   = set("ңөү")
_EN_WORDS = {"the","a","an","is","are","was","were","of","in","and","to","it",
             "he","she","they","we","you","i","that","this"}

def custom_lid(text):
    if not text or not text.strip(): return "null", 0.0, "no_transcript"
    t = text.lower()
    script = detect_script(t)
    if script == "cyrillic":
        if any(c in _KK_ONLY for c in t): return "kk", 0.90, "kazakh_specific_chars"
        if any(c in _KK_KY   for c in t): return "ky", 0.60, "kk_ky_shared_chars"
        return "ru", 0.55, "standard_cyrillic_only_ambiguous"
    elif script == "latin":
        words = set(re.findall(r"[a-z']+", t))
        uz_score = t.count("o'") + t.count("g'") + sum(1 for w in words if len(w)>3 and any(c in w for c in "qx"))
        en_score = len(words & _EN_WORDS)
        if uz_score > en_score: return "uz", 0.65, "latin_uz_heuristic"
        return "en", 0.70, "english_stopwords"
    elif script == "arabic": return "ar", 0.80, "arabic_script"
    elif script == "mixed":  return "mixed", 0.40, "mixed_script"
    return "null", 0.0, "empty_after_check"

# ─── FASTTEXT LID (batch via subprocess) ────────────────────────────────────

_FT_SCRIPT = r"""
import sys, io, json, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
warnings.filterwarnings('ignore')
import fasttext
model = fasttext.load_model('research/lid.176.bin')
data = json.loads(sys.stdin.buffer.read().decode('utf-8'))
out = []
for text in data:
    if not text or not text.strip():
        out.append({'lang': 'empty', 'conf': 0.0})
        continue
    labels, probs = model.predict(text.replace('\n', ' '), k=1)
    out.append({'lang': labels[0].replace('__label__', ''), 'conf': round(float(probs[0]), 4)})
sys.stdout.write(json.dumps(out))
sys.stdout.flush()
"""

def fasttext_lid_batch(texts):
    inp_bytes = json.dumps(texts, ensure_ascii=False).encode("utf-8")
    r = subprocess.run(
        [LID_PY, "-c", _FT_SCRIPT],
        input=inp_bytes,
        capture_output=True,
        cwd=ROOT,
        timeout=120,
    )
    if r.returncode != 0:
        stderr_txt = (r.stderr or b"").decode("utf-8", errors="replace")[:300]
        stdout_txt = (r.stdout or b"").decode("utf-8", errors="replace")[:300]
        print(f"  [WARN] fasttext batch returncode={r.returncode}")
        print(f"    stderr: {stderr_txt}")
        print(f"    stdout: {stdout_txt}")
        return [{"lang": "error", "conf": 0.0}] * len(texts)
    return json.loads(r.stdout.decode("utf-8"))

# ─── METRICS ────────────────────────────────────────────────────────────────

_LANG_NAME_TO_ISO = {
    "kazakh":"kk","uzbek":"uz","kyrgyz":"ky","russian":"ru","english":"en",
    "turkish":"tr","tajik":"tg","azerbaijani":"az","georgian":"ka","mongolian":"mn",
    "arabic":"ar","persian":"fa","pashto":"ps","tatar":"tt","chinese":"zh","japanese":"ja",
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

    latencies = sorted(r["latency_ms"] for r in records if r.get("latency_ms",0) > 0)
    def pct(lst, p):
        if not lst: return None
        return lst[max(0, int(math.ceil(p/100*len(lst)))-1)]

    lang = records[0]["language"] if records else "?"
    expected_script = {"uz":"latin","kk":"cyrillic"}
    correct_script   = sum(1 for r in ok if r.get("dominant_script") == expected_script.get(lang))
    correct_ft_lid   = sum(1 for r in ok if r.get("independent_detected_language") == lang)
    correct_cust_lid = sum(1 for r in ok if r.get("custom_lid_diagnostic", r.get("independent_detected_language")) == lang)
    correct_prov_lid = sum(1 for r in ok if _norm_lang(r.get("provider_detected_language")) == lang)
    has_prov_lid     = sum(1 for r in ok if r.get("provider_detected_language") is not None)

    return {
        "n_total":             total,
        "n_success":           n_ok,
        "api_success_rate":    n_ok/total if total>0 else 0,
        "wer_mean":            sum(wers)/len(wers) if wers else None,
        "cer_mean":            sum(cers)/len(cers) if cers else None,
        "script_accuracy":     correct_script/n_ok if n_ok>0 else None,
        "ft_lid_accuracy":     correct_ft_lid/n_ok if n_ok>0 else None,
        "custom_lid_accuracy": correct_cust_lid/n_ok if n_ok>0 else None,
        "provider_lid_accuracy": correct_prov_lid/has_prov_lid if has_prov_lid>0 else None,
        "latency_p50_ms":      pct(latencies, 50),
        "latency_p95_ms":      pct(latencies, 95),
        "total_cost_usd":      sum(r.get("cost_usd",0) for r in records),
    }

# ─── FINAL REPORT ───────────────────────────────────────────────────────────

def build_final_report(all_records):
    groups = {}
    for r in all_records:
        key = (r["model"], r["language"], r["condition"])
        groups.setdefault(key, []).append(r)

    summary_rows = []
    all_metrics  = {}
    for (model, lang, cond), recs in sorted(groups.items()):
        m = compute_group_metrics(recs)
        all_metrics[f"{model}|{lang}|{cond}"] = m
        def fmt(v): return round(v, 4) if v is not None else None
        summary_rows.append({
            "model":      model, "language": lang, "condition": cond,
            "n":          m["n_total"], "success": m["n_success"],
            "wer":        fmt(m["wer_mean"]),  "cer": fmt(m["cer_mean"]),
            "script_acc": fmt(m["script_accuracy"]),
            "ft_lid":     fmt(m["ft_lid_accuracy"]),
            "cust_lid":   fmt(m["custom_lid_accuracy"]),
            "prov_lid":   fmt(m["provider_lid_accuracy"]),
            "p50_ms":     m["latency_p50_ms"], "p95_ms": m["latency_p95_ms"],
            "cost_usd":   round(m["total_cost_usd"], 4),
        })

    total_cost = sum(r.get("cost_usd",0) for r in all_records)

    # JSON
    results_json = {
        "benchmark_version": "1.0", "run_id": RUN_ID,
        "total_records": len(all_records), "total_cost_usd": round(total_cost, 4),
        "manifest_sha256": {"uzbek": SHA256_UZ, "kazakh": SHA256_KK, "audio": SHA256_AUD},
        "lid_tool_primary": "fasttext_lid.176.bin",
        "lid_tool_sha256": SHA256_LID176,
        "lid_note": "240 pilot records: independent_detected_language=custom_script_based_v1; fasttext in custom_lid_diagnostic. 3360 new records: independent_detected_language=fasttext; custom in custom_lid_diagnostic.",
        "metrics": all_metrics, "summary": summary_rows,
    }
    out_json = os.path.join(RES, "final_benchmark_results.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(results_json, f, ensure_ascii=False, indent=2)
    print(f"  JSON: {out_json}")

    # CSV
    out_csv = os.path.join(RES, "final_benchmark_results.csv")
    fields = ["model","language","condition","n","success","wer","cer",
              "script_acc","ft_lid","cust_lid","prov_lid","p50_ms","p95_ms","cost_usd"]
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(summary_rows)
    print(f"  CSV: {out_csv}")

    # Markdown
    def fv(v): return f"{v:.3f}" if v is not None else "—"
    A = []
    A.append("# Phase 1 STT Benchmark — Final Report\n\n")
    A.append(f"**Run ID:** `{RUN_ID}`  \n")
    A.append(f"**Total records:** {len(all_records)} / 3,600 logical  \n")
    A.append(f"**Total cost:** ${total_cost:.4f}  \n")
    A.append(f"**Languages:** Uzbek (uz) · Kazakh (kk)  \n")
    A.append(f"**Models:** gpt-4o-transcribe · gpt-4o-mini-transcribe · whisper-1  \n")
    A.append(f"**Conditions:** AUTO (no hint) · HINT (language supplied)  \n")
    A.append(f"**Contamination risk:** MEDIUM (ISSAI CC BY 4.0 corpora)  \n\n")
    A.append("---\n\n")

    A.append("## Summary Table\n\n")
    A.append("| Model | Lang | Cond | WER | CER | Script | FT-LID | Cust-LID | Prov-LID | P50ms | P95ms | Cost$ |\n")
    A.append("|---|---|---|---|---|---|---|---|---|---|---|---|\n")
    for row in summary_rows:
        A.append(f"| {row['model']} | {row['language']} | {row['condition']} "
                 f"| {fv(row['wer'])} | {fv(row['cer'])} | {fv(row['script_acc'])} "
                 f"| {fv(row['ft_lid'])} | {fv(row['cust_lid'])} | {fv(row['prov_lid'])} "
                 f"| {row['p50_ms'] or '—'} | {row['p95_ms'] or '—'} | {row['cost_usd']:.4f} |\n")

    A.append("\n---\n\n")
    A.append("## Key Findings\n\n")

    # Auto vs Hint
    A.append("### AUTO vs HINT\n\n")
    for lang in ("uz", "kk"):
        for model in ("gpt-4o-transcribe", "gpt-4o-mini-transcribe", "whisper-1"):
            auto_m = all_metrics.get(f"{model}|{lang}|auto", {})
            hint_m = all_metrics.get(f"{model}|{lang}|hint", {})
            if auto_m.get("wer_mean") is not None and hint_m.get("wer_mean") is not None:
                delta = hint_m["wer_mean"] - auto_m["wer_mean"]
                direction = "worse" if delta > 0.01 else "better" if delta < -0.01 else "similar"
                A.append(f"- **{model} {lang}**: AUTO WER={auto_m['wer_mean']:.3f}, "
                         f"HINT WER={hint_m['wer_mean']:.3f} → HINT is {direction} "
                         f"(Δ={delta:+.3f})  \n")
    A.append("\n")

    # gpt-4o-mini Kazakh failure
    A.append("### gpt-4o-mini-transcribe Kazakh — CONFIRMED FAIL\n\n")
    mini_kk_auto = all_metrics.get("gpt-4o-mini-transcribe|kk|auto", {})
    mini_kk_hint = all_metrics.get("gpt-4o-mini-transcribe|kk|hint", {})
    A.append(f"gpt-4o-mini-transcribe produces Kyrgyz Cyrillic output for Kazakh audio. "
             f"Hint sent (prompt='Kazakh') but CONFIRMED_SENT_INEFFECTIVE.  \n")
    A.append(f"- AUTO: WER={fv(mini_kk_auto.get('wer_mean'))} Script={fv(mini_kk_auto.get('script_accuracy'))} "
             f"FT-LID={fv(mini_kk_auto.get('ft_lid_accuracy'))}  \n")
    A.append(f"- HINT: WER={fv(mini_kk_hint.get('wer_mean'))} Script={fv(mini_kk_hint.get('script_accuracy'))} "
             f"FT-LID={fv(mini_kk_hint.get('ft_lid_accuracy'))}  \n\n")

    A.append("---\n\n")
    A.append("## LID Methodology\n\n")
    A.append("Two-layer independent LID (neither is ground truth):\n\n")
    A.append(f"**Layer 1 — fastText `lid.176.bin`** (primary for new records)  \n")
    A.append(f"SHA-256: `{SHA256_LID176}`  \n")
    A.append(f"Python 3.12.10 · fasttext-wheel==0.9.2 · numpy==1.26.4  \n")
    A.append(f"- kk recall (pilot): **95.0%** ✓  \n")
    A.append(f"- uz recall (pilot): **32.5%** ✗ (fastText misclassifies Uzbek Latin as Turkish/Azerbaijani)  \n")
    A.append(f"- kk→ky correctly identified (improvement over custom)  \n\n")
    A.append("**Layer 2 — `custom_script_based_v1`** (secondary diagnostic / pilot primary)  \n")
    A.append("Unicode character analysis. uz recall (pilot): 67.5%.  \n")
    A.append("240 pilot records: `independent_detected_language` = custom result. 3,360 new records: `independent_detected_language` = fasttext, `custom_lid_diagnostic` = custom.  \n\n")
    A.append("**Uzbek LID caveat:** Neither tool meets the 80% uz recall threshold. Results are diagnostic only.  \n\n")

    A.append("---\n\n")
    A.append("## Known Limitations\n\n")
    A.append("1. **Contamination risk: MEDIUM** — ISSAI corpora CC BY 4.0; models may have seen this data.  \n")
    A.append("2. **Uzbek LID unreliable** — fastText 32.5%, custom 67.5%; neither meets 80% threshold.  \n")
    A.append("3. **gpt-4o-mini Kazakh: FAIL** — produces Kyrgyz Cyrillic; hint ineffective.  \n")
    A.append("4. **whisper-1 Uzbek hint: CLAIMED** — `prompt='Uzbek'` sent; effectiveness unconfirmed. ISO `language='uz'` rejected by API.  \n")
    A.append("5. **Provider LID unavailable** for gpt-4o-transcribe and gpt-4o-mini-transcribe.  \n")
    A.append("6. **Uyghur Arabic hallucinations** in Uzbek audio — gpt-4o models produce Uyghur Arabic script for some Uzbek utterances.  \n")
    A.append("7. **Mixed LID methodology** — pilot (240) uses custom LID; new records (3,360) use fasttext primary.  \n")
    A.append("8. **AUTO=HINT for whisper-1 Uzbek** — both conditions send `prompt='Uzbek'` (CLAIMED hint). Effectively same condition.  \n\n")
    A.append("---\n\n")
    A.append("## Methodology\n\n")
    A.append("- Audio: 16kHz mono 16-bit PCM WAV; 300 Uzbek (21.8 min) + 300 Kazakh (37.2 min)  \n")
    A.append("- Normalisation: NFC → casefold → apostrophe unification → punctuation strip → whitespace  \n")
    A.append("- WER/CER: `jiwer` library  \n")
    A.append("- Cost: audio_minutes × price_per_min + output_tokens/1M × token_rate  \n")
    A.append("- Dedup: deterministic request IDs; existing records never overwritten  \n")
    A.append("- AUTO and HINT never averaged — reported separately  \n\n")

    out_md = os.path.join(RES, "final_benchmark_report.md")
    with open(out_md, "w", encoding="utf-8") as f:
        f.writelines(A)
    print(f"  MD:  {out_md}")

    return summary_rows

# ─── MAIN ───────────────────────────────────────────────────────────────────

def main():
    # Load all records
    all_paths = sorted(glob.glob(os.path.join(RECORDS, "*.json")))
    print(f"Loading {len(all_paths)} records...")
    all_records = []
    for p in all_paths:
        with open(p, encoding="utf-8") as f:
            all_records.append(json.load(f))

    ok_records = [r for r in all_records if r.get("http_status") == 200]
    print(f"HTTP 200: {len(ok_records)} / {len(all_records)}")

    # Find new records needing fasttext LID
    needs_ft = [r for r in ok_records
                if r.get("lid_tool") == "fasttext_lid.176.bin_v1"
                and r.get("independent_detected_language") is None]
    print(f"Records needing fasttext LID: {len(needs_ft)}")

    if needs_ft:
        print(f"\n=== FASTTEXT LID PASS ({len(needs_ft)} records) ===")
        batch_size = 100  # smaller batches to avoid stdin buffer issues
        processed = 0
        for i in range(0, len(needs_ft), batch_size):
            batch = needs_ft[i:i + batch_size]
            texts = [r.get("raw_transcription") or "" for r in batch]
            ft_results = fasttext_lid_batch(texts)
            for rec, ft in zip(batch, ft_results):
                rec["independent_detected_language"] = ft["lang"]
                rec["independent_lid_confidence"]    = ft["conf"]
                rec["independent_lid_note"]          = "fasttext_lid.176.bin"
                c_lang, c_conf, c_note = custom_lid(rec.get("raw_transcription") or "")
                rec["custom_lid_diagnostic"] = c_lang
                rec["custom_lid_confidence"] = c_conf
                rec["custom_lid_note"]       = c_note
                rec_path = os.path.join(RECORDS, f"{rec['request_id']}.json")
                with open(rec_path, "w", encoding="utf-8") as f:
                    json.dump(rec, f, ensure_ascii=False, indent=2)
            processed += len(batch)
            print(f"  {processed}/{len(needs_ft)}", end="\r", flush=True)
        print(f"\n  fasttext LID complete.")
    else:
        print("  All new records already have fasttext LID.")

    # For pilot records (custom LID), populate custom_lid_diagnostic if missing
    pilot_records = [r for r in ok_records if r.get("lid_tool") == "custom_script_based_v1"]
    needs_cust_field = [r for r in pilot_records if r.get("custom_lid_diagnostic") is None]
    if needs_cust_field:
        print(f"\nBack-filling custom_lid_diagnostic on {len(needs_cust_field)} pilot records...")
        for rec in needs_cust_field:
            # Move independent_detected_language → custom_lid_diagnostic for pilot records
            rec["custom_lid_diagnostic"] = rec.get("independent_detected_language")
            rec["custom_lid_confidence"] = rec.get("independent_lid_confidence")
            rec["custom_lid_note"]       = rec.get("independent_lid_note")
            rec_path = os.path.join(RECORDS, f"{rec['request_id']}.json")
            with open(rec_path, "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False, indent=2)
        print(f"  Done.")

    # Reload updated records for report
    all_records = []
    for p in sorted(glob.glob(os.path.join(RECORDS, "*.json"))):
        with open(p, encoding="utf-8") as f:
            all_records.append(json.load(f))

    total_cost = sum(r.get("cost_usd", 0) for r in all_records)
    print(f"\nTotal records: {len(all_records)}")
    print(f"Total cost:    ${total_cost:.4f}")

    print("\n=== GENERATING FINAL REPORT ===")
    summary = build_final_report(all_records)

    print("\n=== SUMMARY TABLE ===")
    print(f"{'Model':<25} {'Lang':<5} {'Cond':<5} {'WER':>7} {'CER':>7} {'Script':>7} {'FT-LID':>7} {'Cost$':>8}")
    print("-" * 80)
    for row in summary:
        def fv(v): return f"{v:.3f}" if v is not None else "  —  "
        print(f"{row['model']:<25} {row['language']:<5} {row['condition']:<5} "
              f"{fv(row['wer']):>7} {fv(row['cer']):>7} {fv(row['script_acc']):>7} "
              f"{fv(row['ft_lid']):>7} {row['cost_usd']:>8.4f}")

    print("\nDone.")

if __name__ == "__main__":
    main()
