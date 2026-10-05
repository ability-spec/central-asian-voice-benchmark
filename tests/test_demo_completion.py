"""Release regressions for stream completion, recovery and empty speech."""
import json

import pytest
from fastapi import HTTPException
from test_pipeline_reliability import pipeline, call
from product.backend.routers import turn
from test_dub4_recorder_fix import SRC, _extract_fn, requires_node, run_node


@pytest.mark.asyncio
@pytest.mark.parametrize('stream', [False, True])
async def test_empty_speech_never_reaches_llm_or_tts(pipeline, monkeypatch, stream):
    monkeypatch.setattr(turn, 'transcribe', lambda *args: '  ')
    def forbidden(*args, **kwargs):
        pytest.fail('Empty speech reached a paid downstream stage')
    monkeypatch.setattr(turn, 'respond', forbidden)
    monkeypatch.setattr(turn, 'synthesize_b64', forbidden)
    if stream:
        response = await call(True)
        events = [json.loads(item) async for item in response.body_iterator]
        assert events == [{'type': 'error', 'detail': 'No speech detected. Please record a clear sentence and try again.'}]
    else:
        with pytest.raises(HTTPException) as error:
            await call(False)
        assert error.value.status_code == 422
    assert list(pipeline.iterdir()) == []


@requires_node
@pytest.mark.parametrize('scenario', ['complete', 'truncated', 'out_of_order', 'empty', 'no_eof'])
def test_stream_requires_ordered_parts_and_completion(scenario):
    done = {'type': 'done', 'turn_number': 1, 'response_text': 'Salom', 'audio': 'YQ==', 'language': 'uz'}
    events = [{'type': 'part', 'index': 0, 'audio': 'YQ==', 'text': 'Salom'}, done]
    if scenario == 'truncated': events = events[:1]
    if scenario == 'out_of_order': events[0]['index'] = 2
    if scenario == 'empty': events = []
    # Deliberately omit the final newline and split bytes inside a JSON record.
    payload = '\n'.join(json.dumps(event) for event in events)
    if scenario == 'no_eof':
        payload += '\n'
    script = _extract_fn(SRC, 'sendRequest') + """
let processingInFlight = false, streamCtrl = null, dubQueue = {}, currentAudio = null;
let turnNumber = 0, state = 'processing', errors = [], displayed = 0, finished = 0;
const STATE = {ERROR:'error', PROCESSING:'processing', IDLE:'idle', SPEAKING:'speaking'};
function setState(value) {state = value;}
function playQueueNext() {dubQueue.active = false;}
function pumpQueue() {dubQueue.active = false;}
function displayTurn() {displayed++;}
function showError(message) {errors.push(message);}
function releaseMic() {}
function onTurnFinished() {finished++;}
const API_BASE = '';
const raw = new TextEncoder().encode(PAYLOAD);
let index = 0;
const chunks = raw.length ? [raw.slice(0, 5), raw.slice(5)] : [];
const reader = {read:async () => index < chunks.length ? {value:chunks[index++], done:false} : {done:true}, cancel:async () => {}};
async function fetch() {return {ok:true, body:{getReader:() => reader}};}
(async () => {
 await sendRequest({});
 console.log(JSON.stringify({displayed, errors, finished, busy:processingInFlight, controller:streamCtrl}));
})();
"""
    if scenario == 'no_eof':
        # A valid terminal event must release the UI without another reader.read().
        script = script.replace('{done:true}, cancel:', 'Promise.reject(new Error("Unexpected read after done")), cancel:')
    result = json.loads(run_node(script.replace('PAYLOAD', json.dumps(payload))))
    assert result['busy'] is False and result['controller'] is None
    if scenario in ('complete', 'no_eof'):
        assert result['displayed'] == 1 and result['errors'] == [] and result['finished'] == 1
    else:
        assert result['displayed'] == 0 and len(result['errors']) == 1


@requires_node
def test_hands_free_waits_for_stream_completion_before_rearming():
    script = _extract_fn(SRC, 'onTurnFinished') + """
let continuous = true, processingInFlight = true, micStream = {}, silentRunMs = 1;
let state = 'speaking', released = 0, armed = 0;
const STATE = {SPEAKING:'speaking', IDLE:'idle'};
function beginListening() {armed++;}
function releaseMic() {released++;}
function setState(value) {state = value;}
onTurnFinished();
const pending = {armed, released};
processingInFlight = false;
onTurnFinished();
console.log(JSON.stringify({pending, armed, released}));
"""
    result = json.loads(run_node(script))
    assert result == {'pending': {'armed': 0, 'released': 0}, 'armed': 1, 'released': 0}


@requires_node
def test_new_session_clears_previous_audio_and_retry_state():
    script = _extract_fn(SRC, 'resetSession') + """
let conversationId = 'old', turnNumber = 20, lastFormData = {}, turnAudio = ['old'];
let stopped = 0;
function stopSession() {stopped++;}
function newConversationId() {return 'new';}
let chatEl = {textContent:'old', appendChild(node) {this.placeholder = node.textContent;}};
let document = {createElement() {return {};}};
resetSession();
console.log(JSON.stringify({stopped, conversationId, turnNumber, lastFormData, turnAudio, placeholder:chatEl.placeholder}));
"""
    result = json.loads(run_node(script))
    assert result['stopped'] == 1 and result['conversationId'] == 'new'
    assert result['turnNumber'] == 0 and result['lastFormData'] is None and result['turnAudio'] == []
    assert result['placeholder'].startswith('New session.')
