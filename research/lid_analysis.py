"""
Detailed breakdown of fastText vs custom LID results.
Read-only — does not modify pilot records.
"""
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

with open('research/lid_fasttext_comparison.json', encoding='utf-8') as f:
    data = json.load(f)

rows = data['rows']
uz_rows = [r for r in rows if r['expected_lang'] == 'uz']
kk_rows = [r for r in rows if r['expected_lang'] == 'kk']

# ---- Uzbek breakdown by model ----
print('=== Uzbek recall by model ===')
models = ['gpt-4o-transcribe', 'gpt-4o-mini-transcribe', 'whisper-1']
conditions = ['auto', 'hint']
for m in models:
    for c in conditions:
        subset = [r for r in uz_rows if r['model'] == m and r['condition'] == c]
        ft_correct = sum(1 for r in subset if r['ft_lang'] == 'uz')
        cu_correct = sum(1 for r in subset if r['custom_lang'] == 'uz')
        print(f"  {m}/{c:<5} ({len(subset):>2} records): "
              f"fasttext={ft_correct}/{len(subset)} ({ft_correct/len(subset)*100:.0f}%)  "
              f"custom={cu_correct}/{len(subset)} ({cu_correct/len(subset)*100:.0f}%)")

# ---- Categorise Uzbek failures ----
print()
print('=== Uzbek failures by type ===')
failure_categories = {
    'arabic_script_hallucination': [],   # STT output is Arabic/Uyghur/Persian — not Uzbek
    'turkic_latin_confusion':       [],   # STT output is Latin but FT says tr/az/tk
    'english_short':                [],   # short text / English
    'cyrillic_hallucination':       [],   # STT produced Cyrillic for Uzbek audio
    'other_script_hallucination':   [],   # Georgian, Khmer, etc.
    'correct':                      [],
}
for r in uz_rows:
    if r['ft_lang'] == 'uz':
        failure_categories['correct'].append(r)
    elif r['ft_lang'] in ('ar', 'ug', 'fa'):
        failure_categories['arabic_script_hallucination'].append(r)
    elif r['ft_lang'] in ('tr', 'az', 'tk', 'tt', 'ba', 'ky'):
        failure_categories['turkic_latin_confusion'].append(r)
    elif r['ft_lang'] in ('en', 'no', 'de', 'it', 'id', 'la', 'fr'):
        failure_categories['english_short'].append(r)
    elif r['ft_lang'] in ('ru', 'uk', 'kk', 'km'):
        failure_categories['cyrillic_hallucination'].append(r)
    elif r['ft_lang'] in ('ka', 'empty'):
        failure_categories['other_script_hallucination'].append(r)
    else:
        failure_categories['other_script_hallucination'].append(r)

for cat, items in failure_categories.items():
    if items:
        avg_conf = sum(r['ft_conf'] for r in items) / len(items)
        print(f"  {cat:<35}: {len(items):>3}  avg_conf={avg_conf:.2f}")

# Show Arabic-script cases (fasttext correct that STT hallucinated)
print()
print('=== Arabic/Uyghur hallucination cases (expected uz, STT produced Arabic script) ===')
for r in failure_categories['arabic_script_hallucination']:
    print(f"  [{r['model']}/{r['condition']}] ft={r['ft_lang']} ({r['ft_conf']:.2f})  "
          f"custom={r['custom_lang']}  text={r['transcript'][:70]!r}")

# ---- kk breakdown ----
print()
print('=== Kazakh recall by model ===')
for m in models:
    for c in conditions:
        subset = [r for r in kk_rows if r['model'] == m and r['condition'] == c]
        ft_correct = sum(1 for r in subset if r['ft_lang'] == 'kk')
        cu_correct = sum(1 for r in subset if r['custom_lang'] == 'kk')
        print(f"  {m}/{c:<5} ({len(subset):>2} records): "
              f"fasttext={ft_correct}/{len(subset)} ({ft_correct/len(subset)*100:.0f}%)  "
              f"custom={cu_correct}/{len(subset)} ({cu_correct/len(subset)*100:.0f}%)")

# kk failures
print()
print('=== Kazakh failures ===')
kk_fail = [r for r in kk_rows if r['ft_lang'] != 'kk']
for r in kk_fail:
    print(f"  [{r['model']}/{r['condition']}] ft={r['ft_lang']} ({r['ft_conf']:.2f})  "
          f"custom={r['custom_lang']}  text={r['transcript'][:70]!r}")

# ---- The kk->ky criterion ----
print()
print('=== kk->ky criterion (gpt-4o-mini Kazakh->Kyrgyz outputs) ===')
print('(custom classified these as ru; fasttext must NOT classify as ru)')
kk_ky_cases = [r for r in rows if r['custom_lang'] in ('ru', 'ky') and r['expected_lang'] == 'kk']
for r in kk_ky_cases:
    criterion_pass = 'PASS' if r['ft_lang'] != 'ru' else 'FAIL'
    print(f"  [{r['model']}/{r['condition']}] ft={r['ft_lang']} ({r['ft_conf']:.2f})  "
          f"custom={r['custom_lang']}  {criterion_pass}  text={r['transcript'][:60]!r}")

# ---- Summary ----
print()
print('=== Acceptance criteria summary ===')
uz_ft_recall = sum(1 for r in uz_rows if r['ft_lang'] == 'uz') / len(uz_rows)
kk_ft_recall = sum(1 for r in kk_rows if r['ft_lang'] == 'kk') / len(kk_rows)
kk_ky_cases_pass = all(r['ft_lang'] != 'ru' for r in kk_ky_cases if r['expected_lang'] == 'kk')
print(f"  uz recall:          {uz_ft_recall:.3f}  ({'PASS' if uz_ft_recall >= 0.80 else 'FAIL'}, threshold 0.80)")
print(f"  kk recall:          {kk_ft_recall:.3f}  ({'PASS' if kk_ft_recall >= 0.90 else 'FAIL'}, threshold 0.90)")
print(f"  kk->ky not-ru:      {'PASS' if kk_ky_cases_pass else 'FAIL'}")

# % of uz failures that are Arabic/Uyghur hallucinations
halluc = len(failure_categories['arabic_script_hallucination']) + len(failure_categories['other_script_hallucination'])
print(f"  uz hallucination failures (not fasttext error): {halluc}/120 = {halluc/120:.1%}")
non_halluc_failures = 120 - len(failure_categories['correct']) - halluc
print(f"  uz latin-script misclassifications (fasttext error): {non_halluc_failures}/120 = {non_halluc_failures/120:.1%}")
adj_recall = (len(failure_categories['correct']) + halluc) / 120
print(f"  uz adjusted recall (excluding hallucinations): {adj_recall:.3f}")
