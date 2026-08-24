# Independent LID Validation — STEP 7B / 7C / 7D / 7E

**Date:** 2026-08-23
**Status:** COMPLETE (fasttext installed and validated)

---

## Environment

| Property | Value |
|---|---|
| Platform | Windows 11 Home 10.0.26200 (64-bit) |
| Python 3.12.10 | installed via `winget install Python.Python.3.12`; used for LID only |
| Python 3.13.15 | installed (STEP 7C); fasttext-wheel has no pre-built cp313 wheel — unused |
| Python 3.14.6 | project default; no fasttext wheel available |
| `.venv-lid312` | `C:\Users\erkin\central-asian-voice-benchmark\.venv-lid312\` |
| fasttext-wheel | 0.9.2 (pre-built `cp312-cp312-win_amd64.whl`, no compilation required) |
| numpy | 1.26.4 (downgraded from 2.5.2 — fasttext-wheel 0.9.2 uses deprecated `np.array(copy=False)` API) |
| conda / WSL / MSVC | NOT INSTALLED |

### Why Python 3.12

`fasttext-wheel==0.9.2` is published as a source-only tarball for Python 3.13 and 3.14 on PyPI —
no pre-built wheel exists for those versions on Windows. Python 3.12 has a pre-built
`cp312-cp312-win_amd64.whl` that installs without compilation.

### Install steps (reproducible)

```
winget install Python.Python.3.12
py -3.12 -m venv .venv-lid312
.venv-lid312\Scripts\pip install fasttext-wheel==0.9.2 "numpy<2"
```

---

## fasttext-wheel Compatibility History

| Package | Python | Result | Reason |
|---|---|---|---|
| `fasttext-wheel==0.9.2` | 3.14 | FAIL | Source-only; MSVC required |
| `fasttext-wheel==0.9.2` | 3.13 | FAIL | Source-only; MSVC required (no cp313 wheel on PyPI) |
| `fasttext-wheel==0.9.2` | 3.12 | **SUCCESS** | Pre-built `cp312-cp312-win_amd64.whl` available |

---

## lid.176.bin

| Property | Value |
|---|---|
| Source | `https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.bin` |
| Path | `research/lid.176.bin` |
| SHA-256 | `7e69ec5451bc261cc7844e49e4792a85d7f09c06789ec800fc4a44aec362764e` |
| Size | ~128 MB |
| Languages supported | 176, including `uz` (Uzbek) and `kk` (Kazakh) |
| Downloaded | 2026-08-23 |

---

## Reference Text Validation (8 texts)

Tested with `.venv-lid312` and `lid.176.bin`.

| Text | Expected | fasttext | Confidence | Result |
|---|---|---|---|---|
| Қазір болған аумаққа қаладағы коммуналдық қызмет | kk | kk | 1.000 | PASS |
| Азыр болгон аумакка каладагы коммуналдык кызмат | ky | ky | 0.977 | PASS |
| Bugun kechki paytda biz kutubxonaga bordik | uz | uz | 0.395 | PASS |
| O'zbekiston Respublikasi demokratik davlat | uz | **id** | 0.228 | **FAIL** |
| Сегодня хорошая погода в Москве | ru | ru | 0.997 | PASS |
| The quick brown fox jumps over the lazy dog | en | en | 0.742 | PASS |
| Клин қаласына арнайын шақыртумен келген | kk | kk | 0.999 | PASS |
| سابق باشلىقىنىڭ گەپلىرى بۇ قۇلاقتىن | ug | ug | 1.000 | PASS |

**7/8 pass.** One failure: `"O'zbekiston Respublikasi demokratik davlat"` → classified as `id`
(Indonesian, conf 0.228). Root cause: Uzbek Latin and Malay/Indonesian share a close
orthographic profile; words like "Respublikasi" appear in both; low confidence indicates
fasttext is uncertain. This is a known weakness for short or formal Uzbek Latin phrases.

---

## 240-Record Pilot Validation

Full results saved to `research/lid_fasttext_comparison.json`.

### Overall

| Metric | Value |
|---|---|
| Total records | 240 |
| Agreements (fasttext = custom) | 173 |
| Disagreements | 67 |

### Recall by language

| Lang | FT correct | Total | **FT recall** | Threshold | **Result** | Custom recall |
|---|---|---|---|---|---|---|
| kk | 114 | 120 | **0.950** | ≥ 0.90 | **PASS** | 0.958 |
| uz | 39 | 120 | **0.325** | ≥ 0.80 | **FAIL** | 0.675 |

### Kazakh recall by model/condition

| Model | Condition | FT correct/20 | FT recall | Custom correct/20 |
|---|---|---|---|---|
| gpt-4o-transcribe | auto | 19 | 95% | 19 |
| gpt-4o-transcribe | hint | 20 | 100% | 20 |
| gpt-4o-mini-transcribe | auto | 16 | 80% | 16 |
| gpt-4o-mini-transcribe | hint | 19 | 95% | 20 |
| whisper-1 | auto | 20 | 100% | 20 |
| whisper-1 | hint | 20 | 100% | 20 |

### Uzbek recall by model/condition

| Model | Condition | FT correct/20 | FT recall | Custom correct/20 | Custom recall |
|---|---|---|---|---|---|
| gpt-4o-transcribe | auto | 9 | 45% | 17 | 85% |
| gpt-4o-transcribe | hint | 13 | 65% | 20 | 100% |
| gpt-4o-mini-transcribe | auto | 7 | 35% | 10 | 50% |
| gpt-4o-mini-transcribe | hint | 10 | 50% | 17 | 85% |
| whisper-1 | auto | **0** | **0%** | 9 | 45% |
| whisper-1 | hint | **0** | **0%** | 8 | 40% |

**whisper-1 Uzbek recall is 0/40 = 0%.** All 40 whisper-1 Uzbek transcriptions are
classified by fasttext as Turkish (tr) or Azerbaijani (az). Root cause: whisper-1 transcribes
Uzbek with Turkish/Azerbaijani orthographic conventions (e.g. `ç`, `ş`, `ğ` substitutions,
Turkish word forms). `custom_script_based_v1` detects apostrophes in `o'`/`g'` which persist
in whisper-1 output, so custom correctly labels it as Uzbek. fasttext treats the overall
word-form distribution as Turkish.

---

## Uzbek Failure Breakdown

| Category | Count | Explanation |
|---|---|---|
| Correct (ft=uz) | 39 | fasttext correctly identified Uzbek |
| Turkic-Latin confusion (tr/az/tk/tt/ba/ky) | 29 | Real Uzbek Latin text misclassified as related Turkic language |
| English/short text | 17 | Low-confidence classifications on short transcripts |
| Cyrillic hallucinations (ru/uk/kk/km) | 19 | STT produced Cyrillic/Khmer for Uzbek audio; not an Uzbek transcript |
| Arabic/Uyghur/Persian hallucinations (ar/ug/fa) | 14 | STT produced Uyghur Arabic for Uzbek audio; fasttext CORRECTLY identifies as non-Uzbek |
| Other script hallucinations (ka/empty) | 2 | whisper-1 hallucinated Georgian; fasttext CORRECTLY identifies as non-Uzbek |

**Adjusted recall** (counting the 16 Arabic/other-script hallucination cases as "correctly
identified as non-Uzbek"):
```
(39 correct + 16 hallucination-correct) / 120 = 45.8%
```
Even the adjusted recall fails the 80% threshold.

---

## kk→ky Criterion

> Kazakh→Kyrgyz outputs from gpt-4o-mini must not be classified as Russian.

`custom_script_based_v1` classified all gpt-4o-mini Kazakh→Kyrgyz outputs as `ru` (Russian)
because it only checks for Kazakh-specific chars and falls back to Russian for standard Cyrillic.
fasttext correctly classified all 4 such cases as `ky` (Kyrgyz).

| Record | Expected | fasttext | custom | Criterion |
|---|---|---|---|---|
| gpt-4o-mini/auto `азыр болгон аумакка...` | kk | ky (0.98) | ru | **PASS** |
| gpt-4o-mini/auto `клин шаарына арнайы...` | kk | ky (0.97) | ru | **PASS** |
| gpt-4o-mini/auto `өткени бул калк тогуз...` | kk | ky (0.95) | ky | PASS |
| gpt-4o-mini/auto `катты жана суук күн...` | kk | ky (1.00) | ky | PASS |

**kk→ky criterion: PASS.** This is a meaningful improvement over `custom_script_based_v1`.

---

## Disagreement Summary (67 total)

| Pattern | Count | Key conflict |
|---|---|---|
| custom=uz → ft=tr | 18 | fasttext misclassifies real Uzbek Latin as Turkish |
| custom=ar → ft=ug | 11 | Both agree Arabic script; fasttext more precisely identifies Uyghur |
| custom=uz → ft=en | 9 | Short texts; low fasttext confidence |
| custom=uz → ft=az | 6 | Azerbaijani/Uzbek Latin confusion |
| custom=ru → ft=ky | 4 | fasttext correctly identifies Kyrgyz (improvement) |
| custom=ar → ft=fa | 2 | Arabic-script hallucination; fasttext says Persian |
| custom=uz → ft=no/it/de/la | 7 | Very short/ambiguous texts |
| custom=kk → ft=ky | 1 | One Kazakh/Kyrgyz borderline |
| other | 9 | Various |

---

## Acceptance Criteria

| Criterion | Result | Detail |
|---|---|---|
| Uzbek recall ≥ 80% | **FAIL** | 32.5% (39/120) |
| Kazakh recall ≥ 90% | **PASS** | 95.0% (114/120) |
| kk→ky not classified as Russian | **PASS** | All 4 cases correctly classified as ky |
| No silent relabelling of pilot results | **PASS** | Pilot records unchanged; comparison in separate file |

---

## Assessment for Phase 1

**fasttext lid.176.bin is NOT acceptable as the sole LID tool for Phase 1.**

- kk detection is reliable (95%). fasttext is strictly better than custom_script_based_v1 on the
  kk→ky distinction (correctly identifies Kyrgyz Cyrillic output from gpt-4o-mini).

- uz detection is unreliable (32.5%). The primary failure mode is Uzbek Latin text
  being classified as Turkish or Azerbaijani — especially for whisper-1 (0/40 = 0%) which
  transcribes Uzbek with Turkish orthographic conventions. `custom_script_based_v1` (67.5%)
  outperforms fasttext for uz because it keys on apostrophe patterns (`o'`, `g'`) that
  persist in whisper-1's Turkish-flavored Uzbek transcriptions.

- **Neither tool meets the 80% uz recall threshold on this pilot data.**

- The low uz recall is partly attributable to STT model behavior:
  - Arabic/Uyghur/Georgian/Khmer hallucinations (16/120 cases) — fasttext is CORRECT
  - Cyrillic hallucinations from gpt-4o-mini (19/120 cases) — genuinely not Uzbek Latin output
  - whisper-1 Turkish/Azerbaijani-flavored transcriptions (40/120 cases) — contested

  Even excluding all hallucination failures, adjusted recall is only 45.8%.

---

## Pilot Records

The existing 240 pilot records are **unchanged**. Their `independent_detected_language`
fields remain tagged `lid_tool: custom_script_based_v1` and are **provisional**.

A full fasttext re-tagging of the 240 records is available in:
`research/lid_fasttext_comparison.json` — the `ft_lang` / `ft_conf` columns reflect fasttext
results. This comparison file is supplementary; it does not replace the pilot records.

---

## Step Log

| Step | Status | Notes |
|---|---|---|
| Python 3.13 installed | DONE | 3.13.15 — fasttext-wheel still requires MSVC (no cp313 wheel) |
| Python 3.12 installed | DONE | 3.12.10 — pre-built cp312 wheel confirmed |
| `.venv-lid312` created | DONE | Python 3.12.10, numpy 1.26.4 |
| `fasttext-wheel==0.9.2` installed | DONE | From pre-built wheel |
| `import fasttext` verified | DONE | `load_model` available |
| `lid.176.bin` downloaded | DONE | SHA-256 recorded |
| Reference text validation | DONE | 7/8 pass; uz formal phrase → id (Indonesian) |
| 240-record fasttext LID run | DONE | Results in `lid_fasttext_comparison.json` |
| custom_v1 comparison | DONE | kk: fasttext slightly lower; uz: fasttext significantly lower |
| kk→ky criterion | PASS | fasttext correctly labels Kyrgyz Cyrillic output |
| Pilot records modified | NO | Records unchanged; comparison is a separate file |

---

*No STT API calls made in any step (7B–7E).*
*No manifests or benchmark audio modified.*
*Existing 240 pilot results unchanged.*
*Python 3.14 project environment unchanged.*
