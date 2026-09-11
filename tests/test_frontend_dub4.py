"""
DUB4/DUB5 frontend logic tests — energy VAD + latency HUD.

The VAD core and the HUD formatter are deliberately written as PURE
functions inside a marked block ("VAD-CORE-START/END") in
product/frontend/index.html so they can be extracted verbatim and
exercised under node with deterministic, scripted frame sequences
(no timers, no randomness, no DOM, no network).

Skip policy: node is only needed for the behaviour tests (marked
`requires_node`); the structural tests (block present, DUB1 request
shape intact, VAD wired to the UI) always run.

Run: python -m pytest tests/test_frontend_dub4.py -v
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


def vad_core() -> str:
    html = INDEX_HTML.read_text(encoding="utf-8")
    m = VAD_BLOCK_RE.search(html)
    assert m, "VAD-CORE block not found in index.html"
    return m.group(1)


def run_node(js_body: str) -> str:
    """Eval the pure VAD core + js_body under node; js_body must print JSON."""
    src = vad_core() + "\n" + js_body
    p = subprocess.run(
        ["node", "-e", src], capture_output=True, text=True, timeout=30
    )
    assert p.returncode == 0, f"node failed: {p.stderr[:2000]}"
    return p.stdout.strip()


# ---------------------------------------------------------------------------
# Structural guarantees (no node needed)
# ---------------------------------------------------------------------------

def test_vad_core_block_exists_and_is_pure():
    core = vad_core()
    for dom in ("document", "window", "getElementById", "requestAnimationFrame"):
        assert dom not in core, f"VAD core must be DOM-free, found {dom!r}"


def test_dub1_request_shape_preserved():
    """DUB1 contract intact: mode=dub + source_language=en still appended."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "formData.append('mode', 'dub');" in html
    assert "formData.append('source_language', 'en');" in html


def test_vad_loop_wired_to_ui():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "function startVadLoop(" in html
    assert "function stopVadLoop(" in html
    assert "startVadLoop('capture')" in html
    assert "startVadLoop('barge')" in html
    assert "STATE.LISTENING" in html


def test_latency_hud_wired():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "hudLine(data)" in html


# ---------------------------------------------------------------------------
# VAD core behaviour (node, deterministic frames @ dt=16 ms)
# ---------------------------------------------------------------------------

SCENARIO_HARNESS = """
function feed(st, levels, dt, step) {
  const events = [];
  for (const lv of levels) {
    const r = step(st, lv, dt, VAD_CFG);
    st = r.next;
    if (r.event) events.push(r.event);
  }
  return events;
}
"""


@requires_node
def test_capture_speech_start_and_utterance_complete():
    out = run_node(SCENARIO_HARNESS + """
const Q = 3, V = 40;                    // rms values: quiet vs voiced
let s = newCapture();
let ev1 = feed(s, Array(20).fill(Q), 16, captureStep);            // idle
s = newCapture();
s = feed(s, Array(4).fill(V), 16, captureStep);                    // n/a
// step-by-step control:
let st = newCapture(), events = [];
for (let i = 0; i < 20; i++) events.push(captureStep(st, Q, 16, VAD_CFG));
st = events[events.length-1].next;
assert(JSON.stringify(events.map(e=>e.event).filter(Boolean)) === '[]', 'quiet must not fire');
let fired = [];
for (let i = 0; i < 5; i++) { const r = captureStep(st, V, 16, VAD_CFG); st = r.next; if (r.event) fired.push(r.event); }
assert(JSON.stringify(fired) === '["speech-start"]', 'voiced burst -> speech-start, got ' + JSON.stringify(fired));
for (let i = 0; i < 30; i++) { const r = captureStep(st, V, 16, VAD_CFG); st = r.next; if (r.event) fired.push(r.event); }
// short pause 40 frames = 640 ms < 850: must NOT end utterance
for (let i = 0; i < 40; i++) { const r = captureStep(st, Q, 16, VAD_CFG); st = r.next; if (r.event) fired.push(r.event); }
assert(fired.length === 1, 'short pause fired early: ' + JSON.stringify(fired));
for (let i = 0; i < 55; i++) { const r = captureStep(st, Q, 16, VAD_CFG); st = r.next; if (r.event) fired.push(r.event); }
assert(JSON.stringify(fired) === '["speech-start","utterance-complete"]', 'got ' + JSON.stringify(fired));
console.log('OK');
""")
    assert out == "OK"


@requires_node
def test_capture_blip_is_cancelled_not_submitted():
    out = run_node("""
let st = newCapture(), fired = [];
for (let i = 0; i < 5; i++) { const r = captureStep(st, 40, 16, VAD_CFG); st = r.next; if (r.event) fired.push(r.event); }
for (let i = 0; i < 8; i++) { const r = captureStep(st, 40, 16, VAD_CFG); st = r.next; if (r.event) fired.push(r.event); }  // speech 208ms < 450
for (let i = 0; i < 30; i++) { const r = captureStep(st, 3, 16, VAD_CFG); st = r.next; if (r.event) fired.push(r.event); }  // quiet 480ms
assert(JSON.stringify(fired) === '["speech-start","blip-cancel"]', JSON.stringify(fired));
assert(st.inSpeech === false, 'must return to armed');
let more = [];
for (let i = 0; i < 80; i++) { const r = captureStep(st, 3, 16, VAD_CFG); st = r.next; if (r.event) more.push(r.event); }
assert(more.indexOf('utterance-complete') === -1, 'blip must never submit');
console.log('OK');
""")
    assert out == "OK"


@requires_node
def test_capture_arm_timeout():
    out = run_node("""
let st = newCapture(), fired = [];
for (let i = 0; i < 400; i++) {                       // 400*16 = 6400ms > 6000
  const r = captureStep(st, 3, 16, VAD_CFG); st = r.next;
  if (r.event) { fired.push(r.event); break; }
}
assert(fired[0] === 'timeout', JSON.stringify(fired));
console.log('OK');
""")
    assert out == "OK"


@requires_node
def test_capture_hard_cap_force_stop():
    out = run_node("""
let st = newCapture(), fired = [];
for (let i = 0; i < 2400; i++) {                      // 38.4 s voiced > 35 s cap
  const r = captureStep(st, 40, 16, VAD_CFG); st = r.next;
  if (r.event) fired.push(r.event);
}
assert(fired[0] === 'speech-start', JSON.stringify(fired));
assert(fired.indexOf('force-stop') !== -1, 'missing force-stop: ' + JSON.stringify(fired));
console.log('OK');
""")
    assert out == "OK"


@requires_node
def test_barge_start_commit_and_release_paths():
    out = run_node("""
// commit path: sustained loud speech during playback
let st = newBarge(), fired = [];
for (let i = 0; i < 5; i++) { const r = bargeStep(st, 45, 16, VAD_CFG); st = r.next; if (r.event) fired.push(r.event); }
assert(fired[0] === 'barge-start', JSON.stringify(fired));
for (let i = 0; i < 40; i++) { const r = bargeStep(st, 45, 16, VAD_CFG); st = r.next; if (r.event) fired.push(r.event); }
assert(fired[1] === 'barge-commit', JSON.stringify(fired));
// release path: brief noise blip does not steal the turn
let s2 = newBarge(), f2 = [];
for (let i = 0; i < 5; i++) { const r = bargeStep(s2, 45, 16, VAD_CFG); s2 = r.next; if (r.event) f2.push(r.event); }
for (let i = 0; i < 30; i++) { const r = bargeStep(s2, 2, 16, VAD_CFG); s2 = r.next; if (r.event) f2.push(r.event); }
assert(JSON.stringify(f2) === '["barge-start","barge-release"]', JSON.stringify(f2));
// quiet-room: speaker-level hum (below bargeRms) never fires at all
let s3 = newBarge(), f3 = [];
for (let i = 0; i < 200; i++) { const r = bargeStep(s3, 15, 16, VAD_CFG); s3 = r.next; if (r.event) f3.push(r.event); }
assert(f3.length === 0, 'barge must ignore sub-threshold level, got ' + JSON.stringify(f3));
console.log('OK');
""")
    assert out == "OK"


@requires_node
def test_vad_rms_math_is_exact():
    out = run_node("""
function arr(vals){ const a = new Uint8Array(vals.length); vals.forEach((v,i)=>a[i]=v); return a; }
if (vadRms(arr([128,128,128,128])) !== 0) throw new Error('silence must be 0');
const r = vadRms(arr([118,138,118,138]));            // |Δ| = 10 everywhere
if (Math.abs(r - 10) > 1e-9) throw new Error('rms=' + r);
console.log('OK');
""")
    assert out == "OK"


# ---------------------------------------------------------------------------
# Latency HUD formatter
# ---------------------------------------------------------------------------

@requires_node
def test_hud_formatter_output_and_guards():
    out = run_node("""
const line = hudLine({stt_ms:1240, llm_ms:640, tts_ms:2100, total_ms:3980});
if (line !== 'STT 1.2s · AI 640ms · TTS 2.1s · Σ 4.0s') throw new Error('got: ' + line);
if (fmtMs(999) !== '999ms' || fmtMs(1000) !== '1.0s') throw new Error('fmtMs');
if (hudLine({stt_ms:0,llm_ms:0,tts_ms:0,total_ms:0}) !== '') throw new Error('zero must hide');
if (hudLine({}) !== '' || hudLine(null) !== '') throw new Error('missing fields must hide');
console.log('OK');
""")
    assert out == "OK"
