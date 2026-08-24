"""
Run fastText LID on the 240 pilot transcripts and compare against custom_script_based_v1.
Does NOT modify the original pilot records — writes results to a separate report file.
Does NOT make any STT API calls.
"""
import sys, io, json, glob, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
warnings.filterwarnings('ignore')

import fasttext

RECORDS_DIR = 'research/pilot_results/pilot_001/records'
MODEL_PATH  = 'research/lid.176.bin'
OUT_PATH    = 'research/lid_fasttext_comparison.json'

print(f'Loading {MODEL_PATH} ...')
model = fasttext.load_model(MODEL_PATH)
print('Model loaded.')

records = sorted(glob.glob(f'{RECORDS_DIR}/*.json'))
print(f'Found {len(records)} pilot records.')

results = []
mismatches = []

# counters for recall
lang_totals   = {}  # expected_lang -> total
lang_correct  = {}  # expected_lang -> fasttext correct
cust_correct  = {}  # expected_lang -> custom correct

for path in records:
    with open(path, encoding='utf-8') as f:
        rec = json.load(f)

    expected_lang    = rec['language']           # 'uz' or 'kk'
    transcript       = rec.get('normalized_transcription') or rec.get('raw_transcription') or ''
    custom_lang      = rec['independent_detected_language']
    custom_conf      = rec['independent_lid_confidence']
    custom_note      = rec['independent_lid_note']
    model_name       = rec['model']
    condition        = rec['condition']
    utterance_id     = rec['utterance_id']
    request_id       = rec['request_id']

    if not transcript.strip():
        ft_lang = 'empty'
        ft_conf = 0.0
    else:
        labels, probs = model.predict(transcript.replace('\n', ' '), k=1)
        ft_lang = labels[0].replace('__label__', '')
        ft_conf = float(probs[0])

    # tally
    lang_totals[expected_lang]  = lang_totals.get(expected_lang, 0) + 1
    if ft_lang == expected_lang:
        lang_correct[expected_lang] = lang_correct.get(expected_lang, 0) + 1
    if custom_lang == expected_lang:
        cust_correct[expected_lang] = cust_correct.get(expected_lang, 0) + 1

    agree = (ft_lang == custom_lang)

    row = {
        'request_id':      request_id,
        'model':           model_name,
        'condition':       condition,
        'utterance_id':    utterance_id,
        'expected_lang':   expected_lang,
        'ft_lang':         ft_lang,
        'ft_conf':         round(ft_conf, 4),
        'custom_lang':     custom_lang,
        'custom_conf':     custom_conf,
        'custom_note':     custom_note,
        'agree':           agree,
        'transcript':      transcript[:120],
    }
    results.append(row)
    if not agree:
        mismatches.append(row)

# ---- print summary ----
print()
print('=== fastText vs custom_script_based_v1 comparison ===')
print()
print(f'Total records:  {len(results)}')
print(f'Agreements:     {len(results) - len(mismatches)}')
print(f'Disagreements:  {len(mismatches)}')
print()

# Recall table
print(f"{'Lang':<6} {'FT correct':<12} {'FT total':<10} {'FT recall':<12} {'Cust correct':<14} {'Cust recall':<12}")
print('-' * 70)
for lang in sorted(lang_totals):
    total = lang_totals[lang]
    ft_c  = lang_correct.get(lang, 0)
    cu_c  = cust_correct.get(lang, 0)
    ft_r  = ft_c / total if total else 0
    cu_r  = cu_c / total if total else 0
    ok    = 'OK' if (lang == 'uz' and ft_r >= 0.80) or (lang == 'kk' and ft_r >= 0.90) else 'BELOW THRESHOLD'
    print(f"{lang:<6} {ft_c:<12} {total:<10} {ft_r:<12.3f} {cu_c:<14} {cu_r:<12.3f}  {ok}")

print()
print('=== Disagreements ===')
# Group by mismatch type
mismatch_types = {}
for m in mismatches:
    key = f"{m['custom_lang']} -> {m['ft_lang']} (expected {m['expected_lang']})"
    mismatch_types[key] = mismatch_types.get(key, 0) + 1

for k, v in sorted(mismatch_types.items(), key=lambda x: -x[1]):
    print(f"  {v:>3}x  {k}")

print()
print('=== Key disagreements (kk/uz involved) ===')
key_types = ['kk', 'ky', 'uz', 'en', 'ru']
for m in mismatches:
    if m['expected_lang'] in key_types or m['ft_lang'] in key_types or m['custom_lang'] in key_types:
        print(f"  [{m['model']}/{m['condition']}] expected={m['expected_lang']}  "
              f"ft={m['ft_lang']}({m['ft_conf']:.2f})  "
              f"custom={m['custom_lang']}  "
              f"text={m['transcript'][:60]!r}")

# Save full results
with open(OUT_PATH, 'w', encoding='utf-8') as f:
    json.dump({
        'total': len(results),
        'agreements': len(results) - len(mismatches),
        'disagreements': len(mismatches),
        'lang_recall_fasttext': {k: round(lang_correct.get(k,0)/lang_totals[k], 4) for k in lang_totals},
        'lang_recall_custom':   {k: round(cust_correct.get(k,0)/lang_totals[k], 4) for k in lang_totals},
        'mismatch_types': mismatch_types,
        'rows': results,
    }, f, ensure_ascii=False, indent=2)

print()
print(f'Full results saved to {OUT_PATH}')
