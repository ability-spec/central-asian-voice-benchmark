"""UI language changes labels without changing voice requests or spoken content."""
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which('node') is None, reason='node required')
def test_locale_switch_preserves_content_and_updates_dynamic_status():
    asset = Path(__file__).resolve().parents[1] / 'product/frontend/assets/ui-language.js'
    script = r"""
const fs = require('fs');
const texts = ['Workspace', 'Ready to record', 'English transcription'];
const nodes = texts.map((data, i) => ({data, parentElement:{closest:()=>i===2}}));
const buttons = ['uz','en'].map(locale=>({dataset:{uiLanguage:locale},setAttribute(k,v){this[k]=v;}}));
const mic = {setAttribute(k,v){this[k]=v;}};
const document = {
 documentElement:{lang:'en'},
 getElementById:id=>id==='micBtn'?mic:id==='micLabel'?{textContent:'Start recording'}:{},
 querySelectorAll:()=>buttons,
 createTreeWalker:()=>{let index=0;return {nextNode:()=>nodes[index++]||null};}
};
const NodeFilter={SHOW_TEXT:4};
class MutationObserver {disconnect(){} observe(){}}
let language='kk';
function fetch(){throw Error('locale made a network request');}
eval(fs.readFileSync(process.argv[1],'utf8') + `
if(document.documentElement.lang!=='uz' || nodes[0].data==='Workspace') throw Error('Uzbek default missing');
if(nodes[2].data!=='English transcription') throw Error('spoken content changed');
setUiLanguage('en');
if(nodes[0].data!=='Workspace' || nodes[1].data!=='Ready to record') throw Error('English restore failed');
nodes[1].data='Listening — speak now';
setUiLanguage('uz');
if(nodes[1].data==='Listening — speak now') throw Error('dynamic status not translated');
setUiLanguage('en');
if(nodes[1].data!=='Listening — speak now') throw Error('dynamic source lost');
if(language!=='kk' || buttons[1]['aria-pressed']!=='true') throw Error('locale changed voice language or selection');
setUiLanguage('invalid');
if(document.documentElement.lang!=='en') throw Error('invalid locale accepted');
`);
"""
    result = subprocess.run(['node', '-e', script, str(asset)], capture_output=True,
                            text=True, encoding='utf-8', timeout=20)
    assert result.returncode == 0, result.stderr
