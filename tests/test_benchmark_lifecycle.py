"""Browser benchmark state must survive delayed network responses."""
import json

from test_dub4_recorder_fix import SRC, _extract_fn, requires_node, run_node


def functions(*names):
    return '\n'.join(_extract_fn(SRC, name) for name in names)


@requires_node
def test_missing_leaderboard_values_are_not_zero():
    result = json.loads(run_node(functions('leaderboardValue') + """
console.log(JSON.stringify([null, undefined, '', false, 0, .25].map(v => leaderboardValue(v, true))));
"""))
    assert result == ['—', '—', '—', '—', '0.0%', '25.0%']


@requires_node
def test_changing_file_cannot_enable_button_during_scoring():
    result = json.loads(run_node(functions('updateBenchmarkRunState') + """
let benchmarkBusy = true;
let benchmarkRunBtn = {}, benchmarkPrompt = {value:'Salom'};
let benchmarkAudio = {files:[{}]};
updateBenchmarkRunState();
const busyDisabled = benchmarkRunBtn.disabled;
benchmarkBusy = false;
updateBenchmarkRunState();
console.log(JSON.stringify([busyDisabled, benchmarkRunBtn.disabled]));
"""))
    assert result == [True, False]


@requires_node
def test_old_prompt_response_cannot_replace_current_language():
    result = json.loads(run_node(functions('loadBenchmarkPrompts', 'updateBenchmarkRunState') + """
let language = 'uz', benchmarkPromptVersion = 0, benchmarkBusy = false;
let benchmarkPromptCache = {}, benchmarkRunBtn = {}, benchmarkAudio = {files:[]};
let benchmarkPrompt = {value:'', textContent:'', appendChild() {}};
let benchmarkStatus = {}, benchmarkPromptText = {}, benchmarkPromptMeta = {};
let API_BASE = '';
let document = {createElement() {return {dataset:{}};}};
let requests = {};
function fetch(url) {return new Promise(resolve => { requests[url.slice(-2)] = resolve; });}
(async () => {
  const old = loadBenchmarkPrompts('uz');
  language = 'kk';
  const current = loadBenchmarkPrompts('kk');
  requests.kk({ok:true, json:async () => ({prompts:[]})});
  await current;
  requests.uz({ok:true, json:async () => ({prompts:[{sentence:'Salom'}]})});
  await old;
  console.log(JSON.stringify({status:benchmarkStatus.textContent, disabled:benchmarkRunBtn.disabled}));
})();
"""))
    assert result == {'status': '0 prompts ready.', 'disabled': True}


@requires_node
def test_old_score_response_cannot_render_or_unlock_new_request():
    result = json.loads(run_node(functions('runBenchmark', 'updateBenchmarkRunState') + """
let benchmarkBusy = false, benchmarkRunVersion = 0, benchmarkController = null;
let benchmarkAudio = {files:[{name:'sample.wav', size:100}]}, benchmarkPrompt = {value:'Salom'};
let benchmarkRunBtn = {}, benchmarkStatus = {}, benchmarkResult = {};
let language = 'uz', API_BASE = '', rendered = 0, respond;
function newConversationId() {return 'test';}
function renderBenchmarkResult() {rendered++;}
class FormData {append() {}}
function fetch() {return new Promise(resolve => {respond = resolve;});}
(async () => {
  const old = runBenchmark();
  // Simulate language change cancelling this job and starting another job.
  benchmarkController.abort();
  benchmarkRunVersion++;
  benchmarkBusy = true;
  benchmarkStatus.textContent = 'New request';
  respond({ok:true, json:async () => ({audio:'old'})});
  await old;
  console.log(JSON.stringify({rendered, busy:benchmarkBusy, status:benchmarkStatus.textContent}));
})();
"""))
    assert result == {'rendered': 0, 'busy': True, 'status': 'New request'}
