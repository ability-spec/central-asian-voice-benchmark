"""Exercise the actual capture functions with controlled microphone events."""

import json

from test_dub4_recorder_fix import SRC, _extract_fn, requires_node, run_node


@requires_node
def test_manual_recording_does_not_wait_for_speech_detection():
    fn = _extract_fn(SRC, "startRecording")
    result = json.loads(run_node(fn + """
const STATE = {PROCESSING:'processing', RECORDING:'recording', IDLE:'idle'};
let state = 'idle', mediaRecorder = null, continuous = false, silentRunMs = 0;
let captureAction = 'discard', noSpeechTimeout = true, restartPending = true;
const autoSendInput = {checked:false};
let vadStarts = 0, waveformStarts = 0;
function hideError() {}
function setState(s) {state = s;}
async function openMic() {}
function attachRecorder() {mediaRecorder = {state:'recording'};}
function beginListening() {vadStarts++;}
function startWaveform() {waveformStarts++;}
function showError(m) {throw new Error(m);}
function stopRecording() {}
setInterval = () => 1;
(async () => {
  await startRecording();
  console.log(JSON.stringify({state, continuous, vadStarts,
    recorder:mediaRecorder?.state, captureAction, restartPending, noSpeechTimeout,
    timerVisible:recordingTimer !== null}));
})();
"""))
    assert result == dict(state="recording", continuous=False, vadStarts=0,
                          recorder="recording", captureAction="send",
                          restartPending=False, noSpeechTimeout=False,
                          timerVisible=True)


@requires_node
def test_explicit_send_from_listening_submits_once():
    fns = "\n".join(_extract_fn(SRC, n) for n in ("stopRecording", "stopCapture"))
    result = json.loads(run_node(fns + """
const STATE = {PROCESSING:'processing', LISTENING:'listening'};
let state = STATE.LISTENING, captureAction = 'discard';
let noSpeechTimeout = true, restartPending = true, sends = 0, stops = 0;
let mediaRecorder = null, audioChunks = [], micStream = {}, micMimeType = 'audio/webm';
function setState(s) {state = s;}
function stopVadLoop() {}
function buildAndSend() {sends++;}
function beginListening() {throw new Error('unexpected re-arm');}
class FakeRecorder {
  constructor() {this.state='inactive';}
  start() {this.state='recording';}
  stop() {
    stops++; this.state='inactive';
    queueMicrotask(() => {
      this.ondataavailable({data:{size:1500}});
      this.onstop();
    });
  }
}
const MediaRecorder = FakeRecorder;
attachRecorder();
stopRecording();
stopRecording();
queueMicrotask(() => console.log(JSON.stringify({sends, stops, state, captureAction})));
"""))
    assert result == dict(sends=1, stops=1, state="processing", captureAction="send")


@requires_node
def test_cancel_still_discards_capture():
    fns = "\n".join(_extract_fn(SRC, n) for n in ("endHandsFree", "stopCapture"))
    result = json.loads(run_node(fns + """
let continuous = true, silentRunMs = 100, restartPending = true;
let captureAction = 'send', processingInFlight = false, stops = 0;
let mediaRecorder = {state:'recording', stop(){this.state='inactive'; stops++;}};
function cancelStream() {}
function stopVadLoop() {}
endHandsFree();
console.log(JSON.stringify({continuous, restartPending, captureAction, stops}));
"""))
    assert result == dict(continuous=False, restartPending=False,
                          captureAction="discard", stops=1)


@requires_node
def test_auto_mode_still_arms_speech_detection():
    fn = _extract_fn(SRC, "startRecording")
    result = json.loads(run_node(fn + """
const STATE = {PROCESSING:'processing', LISTENING:'listening', IDLE:'idle'};
let state = 'idle', mediaRecorder = null, continuous = false, silentRunMs = 0;
let captureAction = 'discard', noSpeechTimeout = true, restartPending = true;
const autoSendInput = {checked:true};
let vadStarts = 0;
function hideError() {}
function setState(s) {state = s;}
async function openMic() {}
function beginListening() {vadStarts++; state = STATE.LISTENING;}
function showError(m) {throw new Error(m);}
(async () => {
  await startRecording();
  console.log(JSON.stringify({state, continuous, vadStarts}));
})();
"""))
    assert result == dict(state="listening", continuous=True, vadStarts=1)


@requires_node
def test_rejected_noise_burst_clears_recording_clock():
    fn = _extract_fn(SRC, "onCaptureEvent")
    result = json.loads(run_node(fn + """
const STATE = {LISTENING:'listening'};
let state = 'recording', cleared = false;
recordingTimer = 42;
clearInterval = (id) => {cleared = id === 42;};
function setState(s) {state = s;}
onCaptureEvent('blip-cancel');
console.log(JSON.stringify({state, cleared}));
"""))
    assert result == dict(state="listening", cleared=True)
