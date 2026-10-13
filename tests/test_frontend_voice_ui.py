"""Minimal voice UI regressions; no browser/model/cloud dependency."""
from pathlib import Path
import shutil
import subprocess
import pytest

SOURCE=(Path(__file__).resolve().parents[1]/'product/frontend/index.html').read_text(encoding='utf-8')
def function(name):
    start=SOURCE.index('function '+name+'(')
    return SOURCE[start:SOURCE.index('\n}',start)+2]

@pytest.mark.skipif(shutil.which('node') is None,reason='node required')
def test_native_player_callbacks_are_restored_after_stop():
    js="""
const resultAudioUrls=[],turnAudio=['AAAA'];let currentAudio=null,currentAudioUrl=null;
let streamCtrl=null,processingInFlight=false,dubQueue={active:false,parts:[]};
let continuous=false,silentRunMs=0,restartPending=false,captureAction='',mediaRecorder=null;
const STATE={IDLE:'idle',SPEAKING:'speaking'};let state='idle';
const statusMain={},statusHint={};let finished=0;
const player={pause(){this.paused=true;}},download={};
const document={querySelectorAll:()=>[player]};
URL.createObjectURL=b=>{if(b.type!=='audio/wav')throw Error('wrong format');return 'blob:result';};
URL.revokeObjectURL=()=>{};
function setState(s){state=s;}function stopVadLoop(){}function resetPlayButtons(){}
function stopWaveform(){}function releaseMic(){}function stopCapture(){}
function showError(e){throw Error(e);}function onTurnFinished(){finished++;state='idle';}
"""+'\n'.join(function(n) for n in ['wavBlob','mountResultPlayer','cancelStream','endHandsFree'])+"""
mountResultPlayer({querySelector:s=>s==='.result-player'?player:download},0);
player.onplay();endHandsFree();
if(currentAudio || state!=='idle')throw Error('Stop failed');
player.onplay();player.onended();
if(currentAudio || state!=='idle' || finished!==1)throw Error('replayed native audio did not finish');
if(download.href!=='blob:result' || download.download!=='birovoz-1.wav')throw Error('Download not linked to WAV');
"""
    r=subprocess.run(['node','-e',js],capture_output=True,text=True,timeout=20)
    assert r.returncode==0,r.stderr

def test_ui_has_no_hero_or_fake_text_input():
    assert 'id="hero"' not in SOURCE
    assert '<textarea' not in SOURCE
    assert 'Text-to-speech input is not available' in SOURCE
    assert 'paid OpenAI' in SOURCE
    assert 'Provider and timing' in SOURCE
    assert 'Download WAV' in SOURCE
    assert 'frozen benchmark' in SOURCE
