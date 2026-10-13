import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import {
  localBackend, readNDJSON, makeTurnForm, demoWav, wavBlob,
  providerLabel, voiceOptions,
} from '../product/chrome-extension/core.mjs';

function body(text, cuts = [1, 2, 13, 29]) {
  const bytes = new TextEncoder().encode(text);
  return new ReadableStream({ start(c) {
    let at = 0;
    for (const n of cuts) { c.enqueue(bytes.slice(at, at + n)); at += n; }
    c.enqueue(bytes.slice(at)); c.close();
  } });
}
const audio = demoWav();
const events = [
  { type: 'meta', transcript: 'Қазақша, O‘zbekcha' },
  { type: 'part', index: 0, text: 'Привет', audio },
  { type: 'done', audio, provider_info: { tts: 'local-clone/sayro-seedvc' } },
];
const lines = list => list.map(JSON.stringify).join('\n');

test('only exact loopback HTTP origins, with optional port, are accepted', () => {
  assert.equal(localBackend('http://localhost:8002/'), 'http://localhost:8002');
  assert.equal(localBackend('http://127.0.0.1:8000'), 'http://127.0.0.1:8000');
  for (const url of ['https://example.com', 'http://localhost.example.com', 'file:///tmp',
    'http://localhost@evil.com', 'http://user:password@localhost', 'http://localhost/api',
    'http://localhost/?key=secret', 'http://localhost/#x']) assert.throws(() => localBackend(url));
});

test('multipart matches existing dub API, without keys or new provider fields', () => {
  const form = makeTurnForm(new Blob(['audio'], { type: 'audio/webm' }), 'session', 'uz');
  assert.deepEqual([...form.keys()], ['audio', 'conversation_id', 'language', 'mode', 'source_language']);
  assert.equal(form.get('mode'), 'dub'); assert.equal(form.get('source_language'), 'en');
  assert.equal(form.get('language'), 'uz'); assert.equal(form.get('conversation_id'), 'session');
  assert.throws(() => makeTurnForm(new Blob(), 'x', 'ru'));
});

test('NDJSON handles split Unicode, mixed chunks and no final newline', async () => {
  const seen = [];
  await readNDJSON(body(lines(events), [25, 1, 1, 1, 1, 3, 8]), ev => seen.push(ev));
  assert.deepEqual(seen, events);
});

test('truncated stream never becomes a completed result', async () => {
  await assert.rejects(readNDJSON(body(lines(events.slice(0, 2))), () => {}), /оборвался/);
});

test('stream error after partial audio is surfaced', async () => {
  await assert.rejects(readNDJSON(body(lines([...events.slice(0, 2), { type: 'error', detail: 'TTS failed' }])), () => {}), /TTS failed/);
});

test('missing, duplicate and out-of-order parts are rejected', async () => {
  for (const list of [
    [events[0], { ...events[1], index: 1 }, events[2]],
    [events[0], events[1], events[1], events[2]],
    [events[1], events[2]], [events[0], events[2]],
    [...events, events[1]], [events[0], { type: 'other' }],
  ]) await assert.rejects(readNDJSON(body(lines(list)), () => {}));
});

test('Stop aborts a reader waiting for the next chunk', async () => {
  const abort = new AbortController(); let cancelled = false;
  const stream = new ReadableStream({ cancel() { cancelled = true; } });
  const request = readNDJSON(stream, () => assert.fail('late event'), abort.signal);
  abort.abort(); await assert.rejects(request, { name: 'AbortError' }); assert.equal(cancelled, true);
});

test('invalid JSON and invalid WAV are refused', async () => {
  await assert.rejects(readNDJSON(body('{broken}\n'), () => {}), /JSON/);
  assert.throws(() => wavBlob('not base64'));
  assert.throws(() => wavBlob(btoa('plain text')));
  const bytes = Uint8Array.from(atob(audio), c => c.charCodeAt(0));
  assert.throws(() => wavBlob(btoa(String.fromCharCode(...bytes.slice(0, 50)))), /WAV/);
  assert.equal(wavBlob(audio).type, 'audio/wav'); assert.ok(wavBlob(audio).size > 44);
});

test('MOCK, DEMO, fallback and actual TTS are labelled explicitly', () => {
  assert.match(providerLabel({ mock_mode: true }), /MOCK/);
  assert.match(providerLabel({ demo: true }), /DEMO/);
  assert.match(providerLabel({ tts: 'openai/tts-1 (fallback)' }), /FALLBACK/);
  assert.equal(providerLabel({ tts: 'openai/tts-1' }), 'openai/tts-1');
  assert.equal(voiceOptions({}).length, 1);
  assert.deepEqual(voiceOptions({ local_clone: { configured: true } }).map(o => o.value), ['openai', 'local-clone']);
});

test('manifest requests no page content, tab capture, broad hosts or remote code', () => {
  const manifest = JSON.parse(readFileSync(new URL('../product/chrome-extension/manifest.json', import.meta.url)));
  assert.equal(manifest.manifest_version, 3);
  assert.deepEqual(manifest.permissions.sort(), ['sidePanel', 'storage']);
  assert.deepEqual(manifest.host_permissions, ['http://127.0.0.1/*', 'http://localhost/*']);
  assert.equal(manifest.content_scripts, undefined);
  assert.match(manifest.content_security_policy.extension_pages, /script-src 'self'/);
});

test('worker registers panel behaviour on install, restart and initial load', async () => {
  const calls = [], handlers = {};
  const chrome = {
    sidePanel: { setPanelBehavior: async option => calls.push(option) },
    runtime: {
      onInstalled: { addListener: f => handlers.install = f },
      onStartup: { addListener: f => handlers.start = f },
    },
  };
  runInNewContext(readFileSync(new URL('../product/chrome-extension/background.js', import.meta.url), 'utf8'), { chrome, console });
  handlers.install(); handlers.start();
  assert.equal(calls.length, 3);
  assert.ok(calls.every(c => c.openPanelOnActionClick === true));
});
