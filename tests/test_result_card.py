"""
CP3 frontend tests — the turn result card.

Follows the repo's established pattern (see tests/test_frontend_dub4.py):
the card renderer is a PURE function inside a marked block
("RESULT-CARD-CORE-START/END") in product/frontend/index.html, extracted
verbatim and exercised under node with representative payloads from
/api/turn/stream's 'done' event / /api/turn's JSON.

Covers: scored turns (WER/CER rendered), unscored turns (the state the
current dub UI produces, since it sends no reference_text), missing fields,
garbage types, empty input, plus structural guarantees (block purity,
wiring into displayTurn, CSS present, DUB1 request shape intact).

Run: python -m pytest tests/test_result_card.py -v
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = REPO_ROOT / "product" / "frontend" / "index.html"

requires_node = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not available"
)

VAD_BLOCK_RE = re.compile(
    r"/\* == VAD-CORE-START == \*/(.*?)/\* == VAD-CORE-END == \*/", re.S
)
CARD_BLOCK_RE = re.compile(
    r"/\* == RESULT-CARD-CORE-START == \*/(.*?)/\* == RESULT-CARD-CORE-END == \*/", re.S
)


def card_core() -> str:
    """VAD core (fmtMs lives there) + card core, in document order."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    mv, mc = VAD_BLOCK_RE.search(html), CARD_BLOCK_RE.search(html)
    assert mv, "VAD-CORE block not found in index.html"
    assert mc, "RESULT-CARD-CORE block not found in index.html"
    assert mv.start() < mc.start(), "card block must come after the VAD core"
    return mv.group(1) + "\n" + mc.group(1)


def run_node(js_body: str) -> str:
    """Eval the pure cores + js_body under node; js_body must print JSON."""
    src = card_core() + "\n" + js_body
    p = subprocess.run(
        ["node", "-e", src], capture_output=True, text=True, timeout=30
    )
    assert p.returncode == 0, f"node failed: {p.stderr[:2000]}"
    return p.stdout.strip()


# ---------------------------------------------------------------------------
# Structural guarantees (no node needed)
# ---------------------------------------------------------------------------

def test_result_card_block_exists_and_is_pure():
    html = INDEX_HTML.read_text(encoding="utf-8")
    core = CARD_BLOCK_RE.search(html).group(1)
    for bad in ("document", "window", "getElementById",
                "requestAnimationFrame", "fetch(", "XMLHttpRequest"):
        assert bad not in core, f"card core must be DOM/network-free, found {bad!r}"


def test_display_turn_wires_the_card():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "resultCardHtml(data) +" in html, "displayTurn no longer renders the card"
    # the card's latency tiles carry the same data the old inline HUD showed;
    # the hudLine *function* itself must survive for the DUB4 tests.
    assert "function hudLine(data)" in html, "hudLine definition was removed"
    assert "hudLine(data) ?" not in html, "old inline HUD still wired (duplicate)"


def test_result_card_css_present():
    html = INDEX_HTML.read_text(encoding="utf-8")
    for rule in (".result-card{", ".rc-grid{", ".rc-tile{", ".rc-badge{"):
        assert rule in html, f"missing CSS rule {rule}"
    assert "repeat(2,minmax(0,1fr))" in html, "no mobile (2-col) grid rule"


def test_dub1_request_shape_still_intact():
    """DUB1/DUB4 contract untouched by CP3."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "formData.append('mode', 'dub');" in html
    assert "formData.append('source_language', 'en');" in html


# ---------------------------------------------------------------------------
# Behaviour (node; representative real payloads)
# ---------------------------------------------------------------------------

@requires_node
def test_scored_turn_renders_wer_cer_and_latency():
    out = run_node("""
    var html = resultCardHtml({
      wer: 0.182, cer: 0.0751, scored: true,
      stt_ms: 1200, llm_ms: 3010, tts_ms: 800, total_ms: 5010
    });
    var c = {
      wer: html.includes('WER'), cer: html.includes('CER'),
      wer_pct: html.includes('>18.2'), cer_pct: html.includes('>7.5'),
      scored_badge: html.includes('Scored'),
      stt: html.includes('1.2s'), ai: html.includes('3.0s'),
      tts: html.includes('800ms'), total: html.includes('5.0s'),
      sigma: html.includes('\\u03a3'),
      no_unscored: !html.includes('Unscored'),
      no_nan: !html.includes('NaN') && !html.includes('undefined'),
      wrapped: html.startsWith('<div class="result-card">')
    };
    console.log(JSON.stringify(c));
    """)
    c = json.loads(out)
    failed = [k for k, v in c.items() if not v]
    assert not failed, f"scored-turn render missing: {failed}"


@requires_node
def test_unscored_turn_renders_honest_state():
    """The state the current dub UI produces (no reference_text sent):
    scored=false, wer/cer null — tiles must show em dashes + the badge."""
    out = run_node("""
    var html = resultCardHtml({
      wer: null, cer: null, scored: false,
      stt_ms: 950, llm_ms: 2100, tts_ms: 640, total_ms: 3690
    });
    var c = {
      unscored_badge: html.includes('Unscored') && html.includes('no reference'),
      wer_tile: html.includes('WER'), cer_tile: html.includes('CER'),
      dash: html.includes('\\u2014'),
      stt: html.includes('950ms'), total: html.includes('3.7s'),
      no_pct: !html.includes('%'),
      no_nan: !html.includes('NaN') && !html.includes('undefined')
    };
    console.log(JSON.stringify(c));
    """)
    c = json.loads(out)
    failed = [k for k, v in c.items() if not v]
    assert not failed, f"unscored-turn render missing: {failed}"


@requires_node
def test_partial_payload_missing_fields_render_gracefully():
    """A 'done' event could in principle lack keys entirely."""
    out = run_node("""
    var html = resultCardHtml({stt_ms: 500, total_ms: 900});
    var c = {
      renders: html.indexOf('<div class="result-card">') === 0,
      stt: html.includes('500ms'), total: html.includes('900ms'),
      unscored: html.includes('Unscored'),
      dash_for_missing: html.includes('\\u2014'),
      no_undefined: !html.includes('undefined'),
      no_nan: !html.includes('NaN')
    };
    console.log(JSON.stringify(c));
    """)
    c = json.loads(out)
    failed = [k for k, v in c.items() if not v]
    assert not failed, f"partial-payload render missing: {failed}"


@requires_node
def test_garbage_types_never_leak_nan_or_undefined():
    out = run_node("""
    var html = resultCardHtml({
      wer: 'abc', cer: {}, scored: true,
      stt_ms: 700, llm_ms: 'fast', tts_ms: -3, total_ms: 'x'
    });
    var none = resultCardHtml({
      wer: 'x', scored: 'yes', stt_ms: null, tts_ms: -3, total_ms: -5
    });
    console.log(JSON.stringify({
      no_nan: !html.includes('NaN'),
      no_undefined: !html.includes('undefined'),
      dash_for_bad_rates: html.includes('\\u2014'),
      scored_badge: html.includes('Scored'),
      valid_ms_survives: html.includes('700ms'),
      no_pct_from_garbage: !html.includes('%'),
      garbage_only_returns_empty: none === ''
    }));
    """)
    c = json.loads(out)
    failed = [k for k, v in c.items() if not v]
    assert not failed, f"garbage-typed payload leaked: {failed}"


@requires_node
def test_empty_and_null_input_return_empty_string():
    out = run_node("""
    console.log(JSON.stringify({
      null_input: resultCardHtml(null) === '',
      empty_obj: resultCardHtml({}) === '',
      all_zero: resultCardHtml({stt_ms: 0, llm_ms: 0, tts_ms: 0, total_ms: 0,
                               wer: null, cer: null, scored: false}) === ''
    }));
    """)
    c = json.loads(out)
    assert all(c.values()), f"expected '' for empty inputs, got {c}"


@requires_node
def test_card_html_has_no_unsafe_payload_interpolation():
    """Only numbers and static labels may enter the markup: a hostile
    string in any metric field must never appear in the output."""
    out = run_node("""
    var html = resultCardHtml({
      wer: '<script>alert(1)</script>', cer: '\\"onerror=1',
      scored: true, stt_ms: 100, llm_ms: 100, tts_ms: 100, total_ms: 300
    });
    console.log(JSON.stringify({
      no_script: !html.includes('<script'),
      no_onerror: !html.includes('onerror'),
      still_renders: html.includes('result-card'),
      no_nan: !html.includes('NaN')
    }));
    """)
    c = json.loads(out)
    assert all(c.values()), f"unsafe payload leaked into card HTML: {c}"
