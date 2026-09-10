"""
Reference-based STT scoring for BirOvoz (WER / CER).

Dependency-free implementation of the Phase 3A text normalisation
methodology (methodology_proposal.md sections C1, C2, C6; identical text
pipeline as Phase 1 and Phase 2), ported from
results/phase3a/run_phase3a_trackb.py (normalise / compute_wer /
compute_cer).

The frozen research scorer delegates to `jiwer` and returns None when
jiwer is not installed. This module computes the same Levenshtein-based
rates with only the standard library, so the product API never needs
that dependency.

Fidelity notes - deliberate, so product scores stay comparable with the
frozen benchmark results:
  * Apostrophe unification covers U+0027, U+02BC and U+0060 only. Curly
    quotes U+2018 / U+2019 are NOT in the class, so they are deleted as
    punctuation and can split a word. Same as Phase 3A: do not "fix"
    this here or scores stop being comparable.
  * Digits and underscore survive normalisation (they are word chars).
  * WER/CER are computed against the RAW hypothesis, normalised
    internally (Phase 3A scores raw_transcription, not the
    pre-normalised copy).
  * Rates are plain edit distance / reference length and may exceed 1.0
    when the hypothesis contains insertions beyond the reference length.
"""

import re
import unicodedata
from typing import Optional


# Byte-faithful port of the Phase 3A regexes. _APOS is exactly the four
# code points from the frozen source: U+0027 twice, U+02BC, U+0060.
_PUNCT = re.compile(r"[^\w\s']", re.UNICODE)
_APOS = re.compile("[''\u02bc`]")
_WS = re.compile(r'\s+')


def normalise(text: str) -> str:
    """Normalise text exactly like the Phase 3A benchmark pipeline."""
    if not isinstance(text, str) or not text.strip():
        return ''
    text = unicodedata.normalize('NFC', text)
    text = text.casefold()
    text = _APOS.sub("'", text)
    text = _PUNCT.sub(' ', text)
    text = _WS.sub(' ', text).strip()
    return text


def _edit_distance(a, b) -> int:
    """Levenshtein distance over two sequences (tokens or characters)."""
    n, m = len(a), len(b)
    if n == 0:
        return m
    if m == 0:
        return n
    prev = list(range(m + 1))
    for i in range(1, n + 1):
        cur = [i] + [0] * m
        ai = a[i - 1]
        for j in range(1, m + 1):
            cur[j] = min(
                prev[j] + 1,              # deletion
                cur[j - 1] + 1,           # insertion
                prev[j - 1] + (ai != b[j - 1]),  # substitution
            )
        prev = cur
    return prev[m]


def wer(reference: str, hypothesis: str) -> Optional[float]:
    """Word error rate, or None when the reference is empty after
    normalisation (mirrors the frozen compute_wer contract)."""
    r, h = normalise(reference), normalise(hypothesis)
    if not r:
        return None
    ref_words = r.split()
    hyp_words = h.split()
    return round(_edit_distance(ref_words, hyp_words) / len(ref_words), 6)


def cer(reference: str, hypothesis: str) -> Optional[float]:
    """Character error rate at Unicode code-point level, or None when
    the reference is empty after normalisation."""
    r, h = normalise(reference), normalise(hypothesis)
    if not r:
        return None
    ref_chars = list(r)
    hyp_chars = list(h)
    return round(_edit_distance(ref_chars, hyp_chars) / len(ref_chars), 6)


def score(reference: str, hypothesis: str) -> dict:
    """Score a hypothesis against a reference.

    Returns {"wer": float | None, "cer": float | None, "scored": bool}.
    scored is False (with None rates) exactly when no usable reference
    was provided - i.e. reference is empty or normalises to nothing.
    """
    r = normalise(reference)
    if not r:
        return {"wer": None, "cer": None, "scored": False}
    return {"wer": wer(reference, hypothesis),
            "cer": cer(reference, hypothesis),
            "scored": True}
