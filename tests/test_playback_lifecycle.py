"""Delayed media callbacks must not modify a stopped or replacement session."""
import json
import subprocess

import pytest
from test_dub4_recorder_fix import SRC, _extract_fn, requires_node


@requires_node
@pytest.mark.parametrize('event', ['resolve', 'reject', 'ended', 'error'])
@pytest.mark.parametrize('replace', [False, True])
def test_obsolete_audio_callbacks_are_ignored(event, replace):
    script = _extract_fn(SRC, 'playAudio') + _extract_fn(SRC, 'stopCurrentPlayback') + r"""
let currentAudio = null, currentAudioUrl = null;
let dubQueue = {active:true}, state = 'speaking', micStream = {};
let effects = [], revoked = [], audios = [];
const STATE = {SPEAKING:'speaking', IDLE:'idle'};
function setState(x) {effects.push('state'); state=x;}
function paintPlayButton() {effects.push('button');}
function resetPlayButtons() {effects.push('reset');}
function onTurnFinished() {effects.push('finished');}
function playQueueNext() {effects.push('next');}
function releaseMic() {effects.push('mic');}
function showError() {effects.push('error');}
function startVadLoop() {effects.push('vad');}
function latestPlayButton() {return {};}
let continuous = true, statusMain = {}, statusHint = {};
let serial = 0;
URL.createObjectURL = () => 'blob:' + (++serial);
URL.revokeObjectURL = url => revoked.push(url);
global.Audio = class {
 constructor(url) {this.url=url; audios.push(this);}
 pause() {}
 play() {return new Promise((resolve,reject)=>{this.resolve=resolve;this.reject=reject;});}
};
(async () => {
 playAudio('YQ==', {}, true);
 const old=audios[0], ended=old.onended, error=old.onerror;
 if (REPLACE) playAudio('Yg==', {}, true); else stopCurrentPlayback();
 const active=currentAudio, url=currentAudioUrl;
 effects=[]; revoked=[];
 if (EVENT==='resolve') old.resolve();
 if (EVENT==='reject') old.reject({name:'NotAllowedError'});
 if (EVENT==='ended') ended();
 if (EVENT==='error') error();
 await new Promise(resolve=>setImmediate(resolve));
 if(currentAudio!==active || currentAudioUrl!==url) throw Error('replacement lost');
 if(effects.length || revoked.length) throw Error('obsolete callback changed UI or resources');
 console.log('ok');
})();
"""
    script = script.replace('REPLACE', json.dumps(replace)).replace('EVENT', json.dumps(event))
    result = subprocess.run(['node', '-e', script], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'ok'
