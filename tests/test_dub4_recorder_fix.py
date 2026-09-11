"""
DUB4 real-browser bugfix tests — timer leak, recorder replacement, and the
header-only-WebM guard (malformed WebM -> backend 422, ffmpeg "0x00 at pos 36").

These extract the REAL functions from product/frontend/index.html by name and
run them in node against stubbed globals (no DOM, no browser, no network).

Proves:
  a) startTimer() called repeatedly keeps exactly ONE live interval;
  b) releaseMic() while recording clears the clock (stopTimer);
  c) attachRecorder() over an active recorder stops + detaches the old one,
     so late dataavailable/onstop cannot pollute the new session's chunks;
  d) buildAndSend() does NOT call fetch/sendRequest for a tiny or a
     zero-padded header-only WebM (the exact real-world malformed blob);
  e) a valid sized WebM keeps flowing to sendRequest unchanged.

Run: python -m pytest tests/test_dub4_recorder_fix.py -v
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = REPO_ROOT / "product" / "frontend" / "index.html"

requires_node = pytest.mark.skipif(shutil.which("node") is None, reason="node unavailable")


def _extract_fn(src: str, name: str) -> str:
    """Grab `(async )?function NAME(...) { ... }` by brace matching."""
    m = re.search(rf"\n(?:async\s+)?function {name}\(", src)
    assert m, f"function {name} not found in index.html"
    i = src.index("{", m.end() - 1)
    depth = 0
    for j in range(i, len(src)):
        c = src[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[m.start() : j + 1]
    raise AssertionError(f"unbalanced braces in {name}")


SRC = INDEX_HTML.read_text(encoding="utf-8")
FNS = {n: _extract_fn(SRC, n) for n in
       ("startTimer", "stopTimer", "releaseMic", "attachRecorder",
        "buildAndSend", "isCaptureValid")}
# isCaptureValid is part of the fix; assert its behavior through buildAndSend.


def run_node(body: str) -> str:
    preamble = "\n".join(FNS.values()) + """
let recordingTimer = null, recordingSeconds = 0;
let statusTimer = { textContent: '', classList: { add(){}, remove(){} } };
let statusMain = { textContent: '' }, statusHint = { textContent: '' };
"""
    p = subprocess.run(
        ["node", "-e", preamble + body], capture_output=True, text=True, timeout=30)
    assert p.returncode == 0, f"node failed: {p.stderr[:1500]}"
    return p.stdout.strip()


# ---------------------------------------------------------------------------
# (a) one interval only
# ---------------------------------------------------------------------------

@requires_node
def test_start_timer_never_stacks_intervals():
    out = run_node("""
let __live = new Set(), __id = 0, __fns = {};
const __si = setInterval, __ci = clearInterval;   // capture real ones first
setInterval = (fn) => { const id = ++__id; __live.add(id); __fns[id] = fn; return id; };
clearInterval = (id) => { __live.delete(id); };
let __stopCalls = 0;
function stopRecording(){ __stopCalls++; }
for (let k = 0; k < 5; k++) startTimer();
const oneLive = __live.size === 1;
// the single live clock must reach the 30 s cap exactly once, at tick 30
const fn = __fns[[...__live][0]];
for (let t = 1; t < 30; t++) fn();
const early = __stopCalls;
fn();                                              // tick 30
console.log(JSON.stringify({ oneLive, early, at30: __stopCalls }));
""")
    r = json.loads(out)
    assert r["oneLive"] is True, "startTimer stacked intervals (zombie clocks)"
    assert r["early"] == 0 and r["at30"] == 1, f"cap fired wrong: {r}"


# ---------------------------------------------------------------------------
# (b) releaseMic clears the clock even when onstop is nulled
# ---------------------------------------------------------------------------

@requires_node
def test_release_mic_stops_the_timer():
    out = run_node("""
let __live = new Set();
setInterval = (fn) => { const id = 1; __live.add(id); return id; };
clearInterval = (id) => { __live.delete(id); };
recordingTimer = 1;
let __vadOff = 0, __wfOff = 0;
function stopVadLoop(){ __vadOff++; }
function stopWaveform(){ __wfOff++; }
function cleanupStream(s){ s.getTracks().forEach(t => t.stop()); }
function cleanupAudio(){}
let mediaRecorder = null, micStream = null, micMimeType = null, analyser = null;
let __stopped = false, __onstopNulled = false;
const old = {
  state: 'recording', onstop: function(){ __onstopNulled = true; },
  ondataavailable: function(){}, stop(){ this.state='inactive'; __stopped = true; },
};
mediaRecorder = old;
micStream = { getTracks: () => [{ stop(){} }] };
releaseMic();
console.log(JSON.stringify({ clockCleared: __live.size === 0,
  stopped: __stopped, onstopNulled: old.onstop === null,
  recorderNull: mediaRecorder === null }));
""")
    r = json.loads(out)
    assert r["clockCleared"] is True, "releaseMic leaked the 30s interval"
    assert r["stopped"] and r["onstopNulled"] and r["recorderNull"]


# ---------------------------------------------------------------------------
# (c) replacing an active recorder detaches the old one
# ---------------------------------------------------------------------------

@requires_node
def test_attach_recorder_replaces_active_recorder_safely():
    out = run_node("""
let mediaRecorder = null, audioChunks = [];
let micStream = {}, micMimeType = 'audio/webm';
let captureAction = 'send', noSpeechTimeout = false;
let __sent = 0, __begin = 0, __err = 0;
function setState(){}
function stopVadLoop(){}
function stopTimer(){}
function beginListening(){ __begin++; }
function showError(){ __err++; }
function releaseMic(){ mediaRecorder = null; }
function buildAndSend(){ __sent++; }
class FakeMR {
  constructor(){ this.state='inactive'; this.ondataavailable=null;
    this.onstop=null; this.onerror=null; this.mimeType='audio/webm';
    this.__stops=0; }
  start(){ this.state='recording'; }
  stop(){ this.__stops++; this.state='inactive'; }
}
MediaRecorder = FakeMR;
const old = new FakeMR(); old.state = 'recording';
old.ondataavailable = (e) => audioChunks.push(e.data);   // pollution vector
old.onstop = () => { __sent += 100; };                     // zombie send vector
mediaRecorder = old;
audioChunks.push('JUNK-FROM-OLD-SESSION');
attachRecorder();
const fresh = mediaRecorder;
// late events from the old recorder must not touch the new session
if (old.ondataavailable) old.ondataavailable({ data: { size: 999 } });
if (old.onstop) old.onstop();
// new recorder works normally
fresh.ondataavailable({ data: { size: 7 } });
fresh.onstop();
console.log(JSON.stringify({
  oldStopped: old.__stops === 1,
  oldDetached: old.ondataavailable === null && old.onstop === null && old.onerror === null,
  chunksReset: audioChunks.length === 1 && audioChunks[0].size === 7,
  newStarted: fresh.state === 'recording' || fresh.state === 'inactive',
  sends: __sent,
}));
""")
    r = json.loads(out)
    assert r["oldStopped"] is True, "old recorder never stopped on replace"
    assert r["oldDetached"] is True, "old handlers still attached (late-event pollution)"
    assert r["chunksReset"] is True, "audioChunks kept stale/foreign data"
    assert r["sends"] == 1, "zombie onstop injected a phantom send"


# ---------------------------------------------------------------------------
# (d)+(e) client-side sanity gate in buildAndSend
# ---------------------------------------------------------------------------

def _build_and_send_body(parts_js: str, blob_type: str = "audio/webm") -> dict:
    return json.loads(run_node(f"""
let mediaRecorder = {{ mimeType: '{blob_type}' }};
let audioChunks = {parts_js};
let processingInFlight = false, language = 'uz', conversationId = 'c';
let lastFormData = null;
let __sent = 0;
const STATE = {{IDLE:0, LISTENING:1, RECORDING:2, PROCESSING:3, SPEAKING:4, ERROR:5}};
function setState(){{}}
function showError(m){{}}
function releaseMic(){{ mediaRecorder = null; }}
function sendRequest(fd){{ __sent++; }}
(async () => {{
  const valid = await isCaptureValid(new Blob(
    audioChunks.map(p => new Uint8Array(p.bytes)), {{ type: '{blob_type}' }}));
  audioChunks = audioChunks.map(p => new Uint8Array(p.bytes));
  await buildAndSend();
  console.log(JSON.stringify({{ sent: __sent, valid, main: statusMain.textContent }}));
}})();
"""))


VALID_WEBM = [0x1A, 0x45, 0xDF, 0xA3, 0x84, 1, 2, 3, 4,
              0x18, 0x53, 0x80, 0x67, 0xFF]
HEADER_ONLY_PADDED = [0x1A, 0x45, 0xDF, 0xA3, 0x84, 1, 2, 3, 4,
                      0x18, 0x53, 0x80, 0x67, 0x00]


@requires_node
def test_valid_webm_still_sends():
    pad = {"bytes": VALID_WEBM + [0x4F] * 1200}
    r = _build_and_send_body(f"[{json.dumps(pad)}]")
    assert r["valid"] is True
    assert r["sent"] == 1, "valid capture must not be blocked"


@requires_node
def test_tiny_blob_is_rejected_without_request():
    tiny = {"bytes": VALID_WEBM[:9]}   # 9 bytes — header fragment
    r = _build_and_send_body(f"[{json.dumps(tiny)}]")
    assert r["valid"] is False
    assert r["sent"] == 0, "tiny header-only blob must never hit the network"
    assert "tap to try again" in r["main"].lower() or "too small" in r["main"].lower()


@requires_node
def test_zero_padded_header_only_webm_rejected_despite_size():
    """The exact real-world blob: valid EBML header + Segment ID + 0x00 VINT,
    size-padded past the trivial threshold. ffmpeg choked at pos 36."""
    padded = {"bytes": HEADER_ONLY_PADDED + [0x00] * 1200}
    r = _build_and_send_body(f"[{json.dumps(padded)}]")
    assert r["valid"] is False, "zero-padded header-only WebM passed the gate"
    assert r["sent"] == 0
