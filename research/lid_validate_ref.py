import sys, io, fasttext, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
warnings.filterwarnings('ignore')

model = fasttext.load_model('research/lid.176.bin')
print('Model loaded OK')

tests = [
    ('Қазір болған аумаққа қаладағы коммуналдық қызмет',   'kk'),
    ('Азыр болгон аумакка каладагы коммуналдык кызмат',     'ky'),
    ('Bugun kechki paytda biz kutubxonaga bordik',           'uz'),
    ("O'zbekiston Respublikasi demokratik davlat",           'uz'),
    ('Сегодня хорошая погода в Москве',                      'ru'),
    ('The quick brown fox jumps over the lazy dog',          'en'),
    ('Клин қаласына арнайын шақыртумен келген',              'kk'),
    ('سابق باشلىقىنىڭ گەپلىرى بۇ قۇلاقتىن',               'ug'),
]

print()
header = f"{'Text':<50} {'Expected':<10} {'Got':<10} {'Conf':>6}  Pass?"
print(header)
print('-' * 90)
all_pass = True
for text, expected in tests:
    labels, probs = model.predict(text, k=1)
    lang = labels[0].replace('__label__', '')
    conf = float(probs[0])
    ok = 'PASS' if lang == expected else 'FAIL'
    if ok == 'FAIL':
        all_pass = False
    snippet = text[:47] + '...' if len(text) > 47 else text
    print(f"{snippet:<50} {expected:<10} {lang:<10} {conf:>6.3f}  {ok}")

print()
if all_pass:
    print('All 8 reference tests PASSED.')
else:
    print('Some reference tests FAILED.')
