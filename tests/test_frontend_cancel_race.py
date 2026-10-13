"""Exercise real playback functions with delayed browser audio callbacks."""
import shutil
import subprocess
from pathlib import Path

import pytest

HTML = Path(__file__).resolve().parents[1] / 'product/frontend/index.html'


def function_source(name):
    text = HTML.read_text(encoding='utf-8')
    start = text.index('function ' + name + '(')
    end = text.index('\n}', start) + 2
    return text[start:end]


@pytest.mark.skipif(shutil.which('node') is None, reason='node required')
def test_barge_in_drops_old_audio_callbacks_and_next_playback_survives():
    script = """
let currentAudio=null, currentAudioUrl=null, streamCtrl=new AbortController();
let dubQueue={active:true}, state='speaking', micStream=null;
const STATE={SPEAKING:'speaking',IDLE:'idle'};
let errors=[], started=0, revoked=[], sounds=[];
const statusMain={},statusHint={};
function resetPlayButtons(){} function paintPlayButton(){}
function startRecording(){started++;} function releaseMic(){}
function onTurnFinished(){} function playQueueNext(){}
function setState(s){state=s;} function startVadLoop(){}
function latestPlayButton(){return null;} function showError(e){errors.push(e);}
let nextUrl=0;
URL.createObjectURL=()=>String(++nextUrl);
URL.revokeObjectURL=u=>revoked.push(u);
class Audio {
 constructor(url){this.url=url; sounds.push(this);}
 pause(){this.paused=true;}
 play(){return new Promise((resolve,reject)=>{this.resolve=resolve;this.reject=reject;});}
}
""" + '\n'.join(function_source(n) for n in ['cancelStream', 'bargeIn', 'playAudio']) + """
(async()=>{
 playAudio('AAAA',null,true);
 const old=currentAudio, oldCtrl=streamCtrl;
 const oldEnded=old.onended,oldError=old.onerror;
 bargeIn();
 if(!oldCtrl.signal.aborted || streamCtrl || dubQueue.active || !old.paused || currentAudio)
   throw Error('barge-in did not stop stream and playback');
 if(started!==1) throw Error('next capture was not started');
 playAudio('AAAA',null,true);
 const next=currentAudio, nextURL=currentAudioUrl;
 old.reject(Object.assign(new Error('interrupted'),{name:'AbortError'}));
 await new Promise(resolve=>setImmediate(resolve));
 oldEnded(); oldError();
 if(currentAudio!==next || currentAudioUrl!==nextURL || errors.length)
   throw Error('old audio callback corrupted the next playback');
 console.log('OK');
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
    result = subprocess.run(['node', '-e', script], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which('node') is None, reason='node required')
def test_cancelled_stream_does_not_reset_next_request():
    script = r"""
let streamCtrl=null,processingInFlight=false,dubQueue={active:false};
const API_BASE='',STATE={ERROR:'error',SPEAKING:'speaking'};
let state='processing',turnNumber=0,currentAudio=null;const statusHint={};
function onTurnFinished(){}
function setState(s){state=s;}function showError(e){throw Error(e);}
function pumpQueue(){}function playQueueNext(){}function displayTurn(){}
const pending=[];
function fetch(){return new Promise((resolve,reject)=>pending.push({resolve,reject}));}
""" + 'async ' + function_source('sendRequest') + '\n' + function_source('cancelStream') + r"""
(async()=>{
 const old=sendRequest(new FormData());cancelStream();
 const next=sendRequest(new FormData());const nextCtrl=streamCtrl;
 pending[0].reject(Object.assign(new Error('abort'),{name:'AbortError'}));
 await old;
 if(!processingInFlight || streamCtrl!==nextCtrl || !dubQueue.active)
   throw Error('old stream reset the next request');
 let delivered=false;
 const payload=new TextEncoder().encode(JSON.stringify({type:'part',index:0,audio:'YQ==',text:'Salom'})+'\n'+JSON.stringify({type:'done',turn_number:1,audio:'YQ==',response_text:'Salom',language:'uz'})+'\n');
 pending[1].resolve({ok:true,body:{getReader:()=>({read:async()=>{if(delivered)return {done:true};delivered=true;return {done:false,value:payload};},cancel:async()=>{}})}});
 await next;
 if(processingInFlight || streamCtrl)throw Error('next stream did not finish');
 console.log('OK');
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
    result = subprocess.run(['node', '-e', script], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which('node') is None, reason='node required')
def test_explicit_stop_clears_playback_queue_connection_and_returns_idle():
    script = """
let streamCtrl=new AbortController(),processingInFlight=true;
const oldCtrl=streamCtrl;let dubQueue={active:true,parts:['OLD']};
let continuous=true,silentRunMs=100,restartPending=true,captureAction='send';
let mediaRecorder=null,currentAudioUrl='old-url',revoked=[];
let currentAudio={onended:()=>{},onerror:()=>{},pause(){this.paused=true;}};
const old=currentAudio,STATE={IDLE:'idle'};let state='speaking',released=0;
const statusMain={},statusHint={};
function stopVadLoop(){}function resetPlayButtons(){}function stopWaveform(){}
function releaseMic(){released++;}function setState(s){state=s;}
function stopCapture(){throw Error('no recorder should be stopped');}
URL.revokeObjectURL=u=>revoked.push(u);
""" + function_source('cancelStream') + '\n' + function_source('endHandsFree') + """
endHandsFree();
if(!oldCtrl.signal.aborted || streamCtrl || processingInFlight || dubQueue.active || dubQueue.parts.length)
 throw Error('Stop did not clear connection and queue');
if(!old.paused || old.onended || old.onerror || currentAudio || currentAudioUrl || revoked[0]!=='old-url')
 throw Error('Stop did not clear playback');
if(state!=='idle' || continuous || !released || captureAction!=='discard')throw Error('Stop did not end session');
console.log('OK');
"""
    result = subprocess.run(['node', '-e', script], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
