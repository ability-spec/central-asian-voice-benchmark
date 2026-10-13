"""A cancelled fetch must not hold the next request or clear its ownership."""
import subprocess
from test_dub4_recorder_fix import SRC, _extract_fn, requires_node

@requires_node
def test_cancel_allows_restart_before_previous_fetch_settles():
    script=_extract_fn(SRC,'sendRequest')+_extract_fn(SRC,'cancelStream')+r"""
let processingInFlight=false, streamCtrl=null, dubQueue={}, currentAudio=null;
let state='processing';const STATE={PROCESSING:'processing',IDLE:'idle',ERROR:'error'};
const API_BASE='';let pending=[], errors=[];
function releaseMic() {}
function setState(x) {state=x;}
function showError(x) {errors.push(x);}
function fetch() {return new Promise((resolve,reject)=>pending.push({resolve,reject}));}
(async()=>{
 const first=sendRequest({});
 const old=streamCtrl;
 cancelStream();
 if(!old.signal.aborted || processingInFlight || streamCtrl!==null) throw Error('cancel did not unlock');
 const second=sendRequest({});const next=streamCtrl;
 if(pending.length!==2 || !processingInFlight) throw Error('restart blocked');
 pending[0].reject({name:'AbortError'});await first;
 if(streamCtrl!==next || !processingInFlight || errors.length) throw Error('old request reset replacement');
 cancelStream();pending[1].reject({name:'AbortError'});await second;
 console.log('ok');
})();
"""
    result=subprocess.run(['node','-e',script],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
    assert result.stdout.strip()=='ok'
