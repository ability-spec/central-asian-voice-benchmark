"""
DUB4 tests — continuous hands-free loop (auto re-arm, silence budget,
one-request guard, session end).

Structure:
  - node: pure DUB4-CORE policy functions (shouldEndOnSilence, nextPhase)
  - node: BOUNDED SIMULATION of the re-arm loop driving the REAL VAD-CORE
    captureStep with scripted frames + the same policy functions — mirrors
    onCaptureEvent/onstop handling to prove: speech -> send, silence ->
    re-arm (bounded), silence budget exceeded -> session ends, and the
    loop always terminates (no busy loop / unbounded API calls).
  - python: structural wiring checks (no node required) + proof the
    DUB1/DUB3 invariants survived.

NOTE: this exercises logic + wiring, not a browser DOM — there is no
real microphone or Chromium here, and nothing calls the OpenAI API.

Run: python -m pytest tests/test_dub4_continuous.py -v
"""

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

CORE_RE = re.compile(
    r"/\* == VAD-CORE-START == \*/(.*?)/\* == VAD-CORE-END == \*/"
    r".*?"
    r"/\* == DUB4-CORE-START == \*/(.*?)/\* == DUB4-CORE-END == \*/",
    re.S,
)


def js_core() -> str:
    html = INDEX_HTML.read_text(encoding="utf-8")
    m = CORE_RE.search(html)
    assert m, "VAD-CORE or DUB4-CORE block not found in index.html"
    return m.group(1) + "\n" + m.group(2)


def run_node(body: str) -> str:
    p = subprocess.run(["node", "-e", js_core() + "\n" + body],
                       capture_output=True, text=True, timeout=30)
    assert p.returncode == 0, f"node failed: {p.stderr[:1500]}"
    return p.stdout.strip()


# ---------------------------------------------------------------------------
# Pure policy
# ---------------------------------------------------------------------------

@requires_node
def test_should_end_on_silence_threshold():
    out = run_node("""
if (shouldEndOnSilence(0, {maxSilentRunMs: 12000})) throw new Error('0 must continue');
if (shouldEndOnSilence(6000, {maxSilentRunMs: 12000})) throw new Error('6s must continue');
if (!shouldEndOnSilence(12000, {maxSilentRunMs: 12000})) throw new Error('12s must end');
if (!shouldEndOnSilence(12016, {maxSilentRunMs: 12000})) throw new Error('over must end');
if (nextPhaseAfterTurn(true) !== 'listen' || nextPhaseAfterTurn(false) !== 'idle')
  throw new Error('nextPhaseAfterTurn');
console.log('OK');
""")
    assert out == "OK"


# ---------------------------------------------------------------------------
# Bounded simulation of the continuous loop on the REAL VAD core
# ---------------------------------------------------------------------------

SIM = """
// Mirror of onCaptureEvent + onstop-discard-restart + speech reset.
function runSession(levelFrames, opts) {
  opts = opts || {};
  let st = newCapture(), sends = 0, restarts = 0, silentRun = 0;
  let ended = false, iter = 0;
  for (const [level, frames] of levelFrames) {
    for (let f = 0; f < frames && !ended; f++) {
      if (++iter > 200000) throw new Error('busy loop detected');
      const r = captureStep(st, level, 16, VAD_CFG);
      st = r.next;
      if (r.event === 'speech-start') { silentRun = 0; }
      else if (r.event === 'utterance-complete' || r.event === 'force-stop') {
        sends++; st = newCapture();            // 'send' path (buildAndSend)
      } else if (r.event === 'timeout') {
        if (opts.continuous &&
            !shouldEndOnSilence(silentRun + VAD_CFG.armTimeoutMs, CONTINUOUS_CFG)) {
          silentRun += VAD_CFG.armTimeoutMs;
          restarts++; st = newCapture();       // restartPending -> beginListening
        } else { ended = true; }               // session ends (idle + release)
      }
    }
    if (ended) break;
  }
  return {sends: sends, restarts: restarts, ended: ended};
}
"""


@requires_node
def test_continuous_survives_silence_and_keeps_taking_turns():
    Q, V = 3, 40
    out = run_node(SIM + f"""
// silence(7s) → utterance → silence(7s) → utterance → silence(7s) → utterance
const turns = [
  [{Q}, 440], [{V}, 8], [{V}, 40], [{Q}, 60],
  [{Q}, 440], [{V}, 8], [{V}, 40], [{Q}, 60],
  [{Q}, 440], [{V}, 8], [{V}, 40], [{Q}, 60],
];
const r = runSession(turns, {{continuous: true}});
if (r.sends !== 3) throw new Error('sends=' + r.sends);
if (r.ended) throw new Error('active session must not end');
if (r.restarts > 3) throw new Error('too many re-arms: ' + r.restarts);
console.log('OK');
""")
    assert out == "OK"


@requires_node
def test_continuous_ends_after_silence_budget_with_bounded_calls():
    out = run_node(SIM + """
// pure silence, forever: must end by itself and never send
const r = runSession([[3, 4000]], {continuous: true});   // ~64 s of silence
if (!r.ended) throw new Error('session must self-end on silence budget');
if (r.sends !== 0) throw new Error('no API call may happen without speech');
if (r.restarts > 2) throw new Error('re-arms must be bounded by budget: ' + r.restarts);
console.log('OK');
""")
    assert out == "OK"


@requires_node
def test_non_continuous_first_timeout_ends_like_dub4_pre():
    out = run_node(SIM + """
const r = runSession([[3, 900]], {continuous: false});   // 14.4 s silence
if (!r.ended || r.restarts !== 0 || r.sends !== 0)
  throw new Error(JSON.stringify(r));
console.log('OK');
""")
    assert out == "OK"


# ---------------------------------------------------------------------------
# Structural wiring (no node required)
# ---------------------------------------------------------------------------

def test_continuous_wiring_present():
    html = INDEX_HTML.read_text(encoding="utf-8")
    for needle in (
        "function beginListening()",
        "function onTurnFinished()",
        "function endHandsFree()",
        "restartPending = true;",
        "if (restartPending && timedOut) {",
        "processingInFlight = true;",
        "processingInFlight = false;",
        "if (processingInFlight) {",
        "onTurnFinished();   // DUB4: resume listening in a hands-free session",
        "onTurnFinished();",
        "state === STATE.LISTENING) endHandsFree();",
    ):
        assert needle in html, f"missing wiring: {needle!r}"


def test_error_and_barge_paths_stop_or_resume_safely():
    html = INDEX_HTML.read_text(encoding="utf-8")
    # error kills the loop
    body = html[html.index("function showError(msg)"):]
    assert "continuous = false;" in body[:400]
    # barge-in commits through the shared beginListening (keeps loop alive)
    barge = html[html.index("ev === 'barge-commit'"):]
    assert "beginListening();" in barge[:700]
    # onended chains to the queue, not to idle, while queue is active
    assert "if (chain && dubQueue.active) { playQueueNext(); return; }" in html


def test_dub1_dub3_invariants_untouched():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "formData.append('mode', 'dub');" in html
    assert "formData.append('source_language', 'en');" in html
    assert "function playbackPlan(data)" in html
    assert "cancelStream();  // DUB3+DUB2: cancel the whole queue AND the pending stream" in html
    assert "startVadLoop('barge')" in html
