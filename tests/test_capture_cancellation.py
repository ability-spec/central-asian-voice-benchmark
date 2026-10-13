"""Stopping during a microphone permission prompt must discard its late result."""
import json
import subprocess
import pytest
from test_dub4_recorder_fix import SRC, _extract_fn, requires_node

@requires_node
@pytest.mark.parametrize('deny', [False, True])
def test_permission_completion_after_stop_is_ignored(deny):
    script = _extract_fn(SRC, 'openMic') + _extract_fn(SRC, 'startRecording') + r"""
let captureVersion=0, micStream=null, mediaRecorder=null, effects=[], stopped=0;
let grant, reject;
const navigator={mediaDevices:{getUserMedia:()=>new Promise((a,b)=>{grant=a;reject=b;})}};
const MediaRecorder={isTypeSupported:()=>true};
const STATE={PROCESSING:'processing',IDLE:'idle'};
let statusMain={}, statusHint={};
function hideError() {}
function setState() {effects.push('state');}
function cleanupStream(stream) {stream.getTracks().forEach(t=>t.stop());}
function releaseMic() {effects.push('release');}
function showError() {effects.push('error');}
(async()=>{
 const pending=startRecording();
 captureVersion++; // Stop/New session invalidates this permission request.
 effects=[];
 if(DENY) reject({name:'NotAllowedError'});
 else grant({getTracks:()=>[{stop:()=>stopped++}]});
 await pending;
 if(effects.length || micStream!==null) throw Error('cancelled prompt changed session');
 if(!DENY && stopped!==1) throw Error('late microphone track leaked');
 console.log('ok');
})();
"""
    result=subprocess.run(['node','-e',script.replace('DENY',json.dumps(deny))],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
    assert result.stdout.strip()=='ok'
