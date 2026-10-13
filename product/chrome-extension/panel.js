import {
  DEFAULT_BACKEND, localBackend, makeTurnForm, readNDJSON, wavBlob,
  voiceOptions, providerLabel, demoWav,
} from './core.mjs';

const $ = id => document.getElementById(id);
let backend = DEFAULT_BACKEND;
let health = null, voiceStatus = null;
let conversation = crypto.randomUUID();
let generation = 0, connecting = false, streaming = false, phase = 'idle';
let controller = null, streamTimeout = null, connectSequence = 0;
let mic = null, recorder = null, captureTimer = null, captureStarted = 0;
let inputBlob = null, inputURL = null, inputName = '', pendingCapture = false;
let audioQueue = [], playing = false, queuedURL = null, fullURL = null;
let completed = false, waitingForPlay = false, playedParts = 0, turns = 0;
const player = $('player');

function status(title, detail = '', error = false) {
  $('statusTitle').textContent = title;
  $('statusDetail').textContent = detail;
  $('statusTitle').parentElement.classList.toggle('error', error);
}
function active() { return streaming || playing || pendingCapture || phase === 'recording' || phase === 'validating'; }
function updateControls() {
  const busy = active();
  $('record').disabled = connecting || phase === 'recording' || pendingCapture || !navigator.mediaDevices;
  $('record').textContent = phase === 'recording' ? 'Записываем…' : 'Записать фразу';
  $('sendRecording').hidden = phase !== 'recording';
  $('stop').disabled = !busy && phase !== 'paused';
  $('file').disabled = busy || connecting;
  $('send').disabled = !inputBlob || busy || connecting || !health ||
    health.audio_tools_ready === false || (!health.mock_mode && !$('consent').checked);
  $('language').disabled = busy || connecting;
  $('voice').disabled = busy || connecting || !voiceStatus;
  $('saveSettings').disabled = busy || connecting;
  $('reconnect').disabled = busy || connecting;
  $('demo').disabled = connecting;
  $('replay').disabled = !fullURL && !waitingForPlay;
}
function clearCapture() {
  clearInterval(captureTimer); captureTimer = null;
  if (recorder) {
    recorder.ondataavailable = recorder.onstop = recorder.onerror = null;
    if (recorder.state !== 'inactive') { try { recorder.stop(); } catch {} }
  }
  recorder = null;
  if (mic) mic.getTracks().forEach(t => t.stop());
  mic = null;
}
function clearPlayback() {
  audioQueue = [];
  playing = false; waitingForPlay = false;
  player.onended = player.onerror = player.onpause = player.onplay = null;
  player.pause(); player.removeAttribute('src'); player.load();
  if (queuedURL) URL.revokeObjectURL(queuedURL);
  queuedURL = null;
}
function stopWork(show = true) {
  generation++;
  clearTimeout(streamTimeout); streamTimeout = null;
  controller?.abort(); controller = null;
  streaming = false; pendingCapture = false;
  clearCapture(); clearPlayback(); phase = 'idle';
  if (fullURL) { player.src = fullURL; bindFullPlayer(generation); $('playbackLabel').textContent = 'Готовый ответ · воспроизведение остановлено'; }
  if (show) status('Остановлено', 'Запись и воспроизведение остановлены. Начатые вычисления сервера могут продолжиться.');
  updateControls();
}
function clearResult() {
  if (fullURL) URL.revokeObjectURL(fullURL);
  fullURL = null; completed = false; playedParts = 0;
  $('result').hidden = true; $('transcript').textContent = ''; $('translation').textContent = '';
  $('metrics').replaceChildren(); $('resultBadge').textContent = '';
  $('download').hidden = true; $('download').removeAttribute('href');
  $('replay').textContent = 'Воспроизвести';
}
function clearInput() {
  if (inputURL) URL.revokeObjectURL(inputURL);
  inputURL = null; inputBlob = null; inputName = '';
  $('inputPreview').pause(); $('inputPreview').removeAttribute('src'); $('inputPreview').load();
  $('inputPreview').hidden = true; $('file').value = ''; $('fileName').textContent = 'Файл не выбран';
}
function beginOperation() {
  stopWork(false); clearResult(); $('inputPreview').pause();
  return generation;
}
function resetSession() {
  stopWork(false); clearResult(); clearInput(); turns = 0;
  conversation = crypto.randomUUID(); $('consent').checked = false;
  status('Новая сессия', 'Предыдущие ответы удалены из панели. Сервер может завершать ранее начатую работу.');
  updateControls();
}
function renderVoice() {
  const select = $('voice'); select.replaceChildren();
  if (!voiceStatus) { select.add(new Option('Недоступно', '')); updateControls(); return; }
  for (const option of voiceOptions(voiceStatus)) select.add(new Option(option.label, option.value));
  const current = voiceStatus.resolved_provider || voiceStatus.active_provider || 'openai';
  if (![...select.options].some(o => o.value === current)) select.add(new Option(`${current} · настроен на сервере`, current));
  select.value = current;
  if (current === 'local-clone' && $('language').value === 'kk') {
    $('voiceHint').textContent = 'Для Kazakh используется стандартный OpenAI: локальный clone поддерживает только Uzbek.';
  } else if (current === 'local-clone') {
    $('voiceHint').textContent = 'Sayro → Seed-VC · возможен холодный старт. Выбор голоса общий для этого backend.';
  } else {
    $('voiceHint').textContent = 'Голос настроен в backend. Его переключение влияет и на открытую веб-версию BirOvoz.';
  }
  updateControls();
}
async function fetchLocal(path, options = {}) {
  return fetch(`${backend}${path}`, {
    credentials: 'omit', redirect: 'error', cache: 'no-store', ...options,
  });
}
async function httpError(response) {
  let message = `HTTP ${response.status}`;
  try { const data = await response.json(); if (typeof data.detail === 'string') message = data.detail.slice(0, 600); } catch {}
  return new Error(message);
}
async function connect() {
  if (active()) return;
  const sequence = ++connectSequence;
  connecting = true; health = null; voiceStatus = null; renderVoice();
  $('connectionLabel').textContent = 'Проверяем подключение…'; $('connectionDot').className = 'dot';
  const signal = AbortSignal.timeout(7000);
  try {
    const response = await fetchLocal('/health', { signal });
    if (!response.ok) throw await httpError(response);
    const data = await response.json();
    if (data.status !== 'ok' || typeof data.mock_mode !== 'boolean') throw new Error('По этому адресу не найден API BirOvoz.');
    if (sequence !== connectSequence) return;
    health = data;
    // Explicitly re-consent after every connection/mode change.
    $('consent').checked = false;
    $('costBox').hidden = data.mock_mode;
    $('connectionLabel').textContent = data.mock_mode ? 'MOCK · фиксированные ответы backend' : 'BirOvoz подключён · LIVE';
    $('connectionDot').className = 'dot ready';
    $('limits').textContent = `До ${durationLimit()} секунд · до ${sizeLimit()} МБ. Отправка только по кнопке.`;
    try {
      const response = await fetchLocal('/api/voice/status', { signal });
      if (!response.ok) throw await httpError(response);
      voiceStatus = await response.json();
    } catch {
      $('voiceHint').textContent = 'Статус голоса недоступен. Запрос использует текущую конфигурацию backend.';
    }
    status(data.audio_tools_ready === false ? 'Нужны ffmpeg и ffprobe' : 'Готово к записи',
      data.audio_tools_ready === false ? 'Установите аудиоинструменты в окружении BirOvoz.' :
      data.mock_mode ? 'MOCK не измеряет качество речи или моделей.' : 'Перед отправкой разрешите использование настроенных API.');
  } catch (error) {
    if (sequence !== connectSequence) return;
    health = null; voiceStatus = null;
    $('connectionDot').className = 'dot failed'; $('connectionLabel').textContent = 'Сервер не подключён';
    $('costBox').hidden = false; $('consent').checked = false;
    status('Нет подключения', `Запустите BirOvoz на ${backend}. ${error.message}`, true);
  } finally {
    if (sequence === connectSequence) { connecting = false; renderVoice(); updateControls(); }
  }
}
function durationLimit() { return Math.max(1, Math.min(30, Number(health?.max_audio_duration_seconds) || 30)); }
function sizeLimit() { return Math.max(1, Math.min(10, Number(health?.max_audio_size_mb) || 10)); }
async function validateInput(blob) {
  if (!blob.size) throw new Error('Запись пуста.');
  if (blob.size > sizeLimit() * 1024 * 1024) throw new Error(`Аудио превышает ${sizeLimit()} МБ.`);
  const url = URL.createObjectURL(blob), audio = new Audio();
  try {
    const duration = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('Не удалось определить длительность аудио.')), 6000);
      audio.onloadedmetadata = () => {
        // MediaRecorder WebM may have no indexed duration. Seek to the end
        // to let Chromium determine it, instead of uploading unchecked audio.
        if (Number.isFinite(audio.duration)) { clearTimeout(timer); resolve(audio.duration); }
        else { audio.ondurationchange = () => {
          if (Number.isFinite(audio.duration)) { clearTimeout(timer); resolve(audio.duration); }
        }; audio.currentTime = 1e10; }
      };
      audio.onerror = () => { clearTimeout(timer); reject(new Error('Chrome не может прочитать этот аудиофайл.')); };
      audio.src = url;
    });
    if (!duration || duration > durationLimit() + 0.1) throw new Error(`Аудио должно быть не длиннее ${durationLimit()} секунд.`);
    return duration;
  } finally { audio.removeAttribute('src'); audio.load(); URL.revokeObjectURL(url); }
}
async function acceptInput(blob, name, token) {
  phase = 'validating'; updateControls(); status('Проверяем аудио…');
  try {
    const duration = await validateInput(blob);
    if (token !== generation) return;
    clearInput(); inputBlob = blob; inputName = name; inputURL = URL.createObjectURL(blob);
    $('inputPreview').src = inputURL; $('inputPreview').hidden = false;
    $('fileName').textContent = `${name} · ${duration.toFixed(1)} с`;
    status('Аудио готово', 'Прослушайте запись, затем нажмите «Перевести и озвучить».');
  } catch (error) {
    if (token === generation) { clearInput(); status('Аудио не принято', error.message, true); }
  } finally { if (token === generation) { phase = 'idle'; updateControls(); } }
}
async function startRecording() {
  const token = beginOperation();
  clearInput(); pendingCapture = true; phase = 'permission'; updateControls();
  status('Доступ к микрофону', 'Разрешите доступ в Chrome. Запись никуда не отправляется автоматически.');
  let obtained;
  try {
    obtained = await navigator.mediaDevices.getUserMedia({ audio: {
      echoCancellation: true, noiseSuppression: true, autoGainControl: true,
    } });
    if (token !== generation) { obtained.getTracks().forEach(t => t.stop()); return; }
    mic = obtained;
    const mime = ['audio/webm;codecs=opus', 'audio/webm'].find(x => MediaRecorder.isTypeSupported(x));
    recorder = new MediaRecorder(mic, mime ? { mimeType: mime } : undefined);
    const instance = recorder, chunks = [];
    instance.ondataavailable = event => { if (token === generation && event.data.size) chunks.push(event.data); };
    instance.onerror = () => { if (token === generation) { stopWork(false); status('Ошибка записи', 'Проверьте микрофон и повторите.', true); } };
    instance.onstop = () => {
      if (token !== generation) return;
      const blob = new Blob(chunks, { type: instance.mimeType || 'audio/webm' });
      clearCapture(); phase = 'idle';
      acceptInput(blob, 'Запись микрофона', token);
    };
    instance.start(250); captureStarted = performance.now(); phase = 'recording'; pendingCapture = false;
    $('recordTime').textContent = '00:00';
    captureTimer = setInterval(() => {
      if (token !== generation) return;
      const seconds = (performance.now() - captureStarted) / 1000;
      $('recordTime').textContent = `00:${Math.floor(seconds).toString().padStart(2, '0')}`;
      // End before the backend's hard limit; never auto-send.
      if (seconds >= durationLimit() - 0.5) finishRecording();
    }, 100);
    status('Записываем английскую речь', 'Нажмите «Завершить запись». Stop удалит текущую запись.');
    updateControls();
  } catch (error) {
    obtained?.getTracks().forEach(t => t.stop());
    if (token !== generation) return;
    stopWork(false);
    status('Микрофон недоступен', 'Нажмите «Разрешение микрофона» и разрешите доступ в открывшейся вкладке. Проверьте также настройки Windows.', true);
  }
}
function finishRecording() {
  if (!recorder || recorder.state !== 'recording') return;
  clearInterval(captureTimer); captureTimer = null;
  recorder.stop(); phase = 'validating'; updateControls();
}
function metric(name, value) {
  const dt = document.createElement('dt'), dd = document.createElement('dd');
  dt.textContent = name; dd.textContent = String(value ?? '—'); $('metrics').append(dt, dd);
}
function showMetrics(ev) {
  $('metrics').replaceChildren();
  const info = ev.provider_info || {};
  metric('STT', info.stt); metric('Перевод', info.llm); metric('TTS', info.tts);
  for (const [name, key] of [['STT, мс', 'stt_ms'], ['Перевод, мс', 'llm_ms'], ['TTS, мс', 'tts_ms'], ['Всего, мс', 'total_ms']]) metric(name, ev[key]);
  metric('Режим', info.demo ? 'DEMO: фиксированный текст и звуки' : info.mock_mode ? 'MOCK' : 'LIVE');
}
function bindFullPlayer(token) {
  player.onplay = () => {
    if (token !== generation) return;
    playing = true; phase = 'playing'; updateControls();
  };
  player.onpause = () => {
    if (token !== generation || player.ended) return;
    phase = 'paused'; updateControls();
  };
  player.onended = () => {
    if (token !== generation) return;
    playing = false; phase = 'idle'; updateControls();
  };
}
function fullPlaybackReady() {
  if (!completed || !fullURL) return;
  if (queuedURL) URL.revokeObjectURL(queuedURL); queuedURL = null;
  player.onended = player.onerror = player.onplay = player.onpause = null;
  player.src = fullURL; playing = false; phase = 'idle'; bindFullPlayer(generation);
  $('playbackLabel').textContent = 'Полный WAV · можно прослушать повторно или скачать';
  status('Ответ готов', 'Результат хранится только в текущей панели.'); updateControls();
}
function playNext(token) {
  if (token !== generation || playing) return;
  const next = audioQueue.shift();
  if (!next) { fullPlaybackReady(); return; }
  if (queuedURL) URL.revokeObjectURL(queuedURL);
  queuedURL = URL.createObjectURL(next.blob); player.src = queuedURL;
  playing = true; phase = 'playing'; playedParts++;
  $('playbackLabel').textContent = `Часть ${next.index + 1} · полный WAV появится после завершения`;
  player.onended = () => {
    if (token !== generation) return;
    playing = false; waitingForPlay = false; playNext(token); updateControls();
  };
  player.onerror = () => {
    if (token !== generation) return;
    stopWork(false); status('Ошибка воспроизведения', 'Chrome не смог декодировать WAV. Проверьте backend.', true);
  };
  player.onpause = () => { if (token === generation && !player.ended && playing) { phase = 'paused'; updateControls(); } };
  player.onplay = () => {
    if (token !== generation) return;
    waitingForPlay = false; phase = 'playing'; $('replay').textContent = 'Воспроизвести'; updateControls();
  };
  player.play().then(() => {
    if (token === generation) { status('Воспроизводим перевод', 'Stop остановит аудио и поток ответа.'); updateControls(); }
  }).catch(() => {
    if (token !== generation) return;
    waitingForPlay = true; phase = 'paused'; $('replay').textContent = 'Продолжить';
    status('Аудио получено', 'Chrome приостановил автозапуск. Нажмите «Продолжить» или Play в плеере.'); updateControls();
  });
  updateControls();
}
function receive(ev, token, isDemo = false) {
  if (token !== generation) return;
  $('result').hidden = false;
  if (ev.type === 'meta') {
    $('transcript').textContent = ev.transcript || '';
    $('resultBadge').textContent = isDemo ? 'DEMO' : health?.mock_mode ? 'MOCK' : 'Провайдер уточняется…';
    status('Речь распознана', 'Ожидаем перевод и озвучку. Для local-clone возможен холодный старт.');
  } else if (ev.type === 'part') {
    const blob = wavBlob(ev.audio);
    $('translation').textContent += `${$('translation').textContent ? ' ' : ''}${ev.text || ''}`;
    audioQueue.push({ blob, index: ev.index }); playNext(token);
  } else if (ev.type === 'done') {
    const blob = wavBlob(ev.audio); fullURL = URL.createObjectURL(blob); completed = true;
    $('translation').textContent = ev.response_text || $('translation').textContent;
    $('resultBadge').textContent = providerLabel(ev.provider_info);
    showMetrics(ev);
    $('download').href = fullURL; $('download').download = `birovoz-${$('language').value}-${Date.now()}.wav`;
    $('download').hidden = false;
    if (!playing && !audioQueue.length) fullPlaybackReady(); updateControls();
  }
}
async function sendAudio() {
  if ($('send').disabled || !inputBlob) return;
  const blob = inputBlob, language = $('language').value;
  const token = beginOperation(); controller = new AbortController();
  const owned = controller; streaming = true; phase = 'processing'; updateControls();
  status('Проверяем конфигурацию…');
  let timedOut = false;
  streamTimeout = setTimeout(() => { timedOut = true; owned.abort(); }, 360000);
  try {
    // Re-read health before any paid request. A mock→live transition must
    // never silently turn a free test into a paid call.
    const healthResponse = await fetchLocal('/health', { signal: owned.signal });
    if (!healthResponse.ok) throw await httpError(healthResponse);
    const fresh = await healthResponse.json();
    if (token !== generation) return;
    if (fresh.status !== 'ok' || typeof fresh.mock_mode !== 'boolean') throw new Error('Неизвестная конфигурация backend.');
    if (!fresh.mock_mode && !$('consent').checked) {
      health = fresh; $('costBox').hidden = false;
      throw new Error('Backend работает в LIVE. Перед отправкой разрешите платный запрос.');
    }
    health = fresh; $('costBox').hidden = fresh.mock_mode;
    $('connectionLabel').textContent = fresh.mock_mode ? 'MOCK · фиксированные ответы backend' : 'BirOvoz подключён · LIVE';
    if (fresh.audio_tools_ready === false) throw new Error('Backend не обнаружил ffmpeg/ffprobe.');
    if (turns >= (fresh.max_turns_per_session || 20)) throw new Error('Лимит сессии. Нажмите «Новая сессия».');
    // Input may have been selected before connecting to a more restrictive backend.
    await validateInput(blob);
    owned.signal.throwIfAborted();
    if (token !== generation) return;
    status('Обрабатываем аудио', 'Ожидаем распознавание. Stop доступен; холодный TTS может занять десятки секунд.');
    turns++; // conservative: cancelled requests may still consume server turns
    const response = await fetchLocal('/api/turn/stream', {
      method: 'POST', body: makeTurnForm(blob, conversation, language), signal: owned.signal,
    });
    if (!response.ok) throw await httpError(response);
    await readNDJSON(response.body, ev => receive(ev, token), owned.signal);
  } catch (error) {
    if (token !== generation) return;
    stopWork(false);
    // A malformed/truncated stream is not a completed response, even if a
    // done event was followed by invalid trailing data.
    clearPlayback();
    if (fullURL) URL.revokeObjectURL(fullURL);
    fullURL = null; completed = false;
    $('resultBadge').textContent = 'НЕ ЗАВЕРШЕНО'; $('download').hidden = true;
    $('download').removeAttribute('href'); updateControls();
    status('Запрос не завершён', timedOut ? 'Истекло 6 минут ожидания. Работа модели на сервере может продолжаться.' : error.message, true);
  } finally {
    if (token === generation) {
      clearTimeout(streamTimeout); streamTimeout = null; controller = null; streaming = false;
      if (!playing) phase = 'idle'; updateControls();
    }
  }
}
async function runDemo() {
  const token = beginOperation(); controller = new AbortController(); const owned = controller;
  streaming = true; phase = 'processing'; updateControls();
  status('DEMO · без API', 'Фиксированный текст и тестовый звук, не речь модели.');
  const first = demoWav(440, 0.5), second = demoWav(660, 0.5);
  const events = [
    { type: 'meta', transcript: 'Demo only. No recording is transcribed.' },
    { type: 'part', index: 0, text: 'Тестовый звук.', audio: first },
    { type: 'part', index: 1, text: 'Без распознавания и перевода.', audio: second },
    { type: 'done', response_text: 'Тестовый звук. Без распознавания и перевода.', audio: demoWav(550, 1),
      provider_info: { demo: true, stt: 'не запускался', llm: 'не запускался', tts: 'локальный тестовый сигнал' } },
  ];
  let index = 0;
  const body = new ReadableStream({
    async pull(c) {
      await new Promise(resolve => setTimeout(resolve, 450));
      if (owned.signal.aborted) return;
      if (index < events.length) c.enqueue(new TextEncoder().encode(JSON.stringify(events[index++]) + '\n'));
      else c.close();
    },
  });
  try { await readNDJSON(body, ev => receive(ev, token, true), owned.signal); }
  catch (error) { if (token === generation) { stopWork(false); status('Демо остановлено', error.message, true); } }
  finally { if (token === generation) { streaming = false; controller = null; if (!playing) phase = 'idle'; updateControls(); } }
}

$('record').addEventListener('click', startRecording);
$('sendRecording').addEventListener('click', finishRecording);
$('stop').addEventListener('click', () => stopWork());
$('newSession').addEventListener('click', resetSession);
$('send').addEventListener('click', sendAudio);
$('consent').addEventListener('change', updateControls);
$('demo').addEventListener('click', runDemo);
$('file').addEventListener('change', () => {
  const file = $('file').files[0]; if (!file) return;
  const token = beginOperation(); clearInput(); acceptInput(file, file.name, token);
});
$('replay').addEventListener('click', () => {
  if (waitingForPlay) { player.play().catch(() => status('Нажмите Play в плеере', '', true)); return; }
  if (!fullURL) return;
  stopWork(false); const token = generation; player.src = fullURL; playing = true; phase = 'playing';
  player.onended = () => { if (token === generation) { playing = false; phase = 'idle'; status('Воспроизведение завершено'); updateControls(); } };
  player.onplay = () => { if (token === generation) { playing = true; phase = 'playing'; updateControls(); } };
  player.onpause = () => { if (token === generation && !player.ended) { phase = 'paused'; updateControls(); } };
  player.play().catch(() => { if (token === generation) { playing = false; phase = 'idle'; status('Нажмите Play в плеере'); updateControls(); } });
  updateControls();
});
$('language').addEventListener('change', async () => {
  renderVoice();
  try { await chrome.storage.local.set({ language: $('language').value }); } catch {}
});
$('voice').addEventListener('change', async () => {
  if (active() || !voiceStatus) return;
  connecting = true; updateControls();
  const prior = voiceStatus;
  try {
    const response = await fetchLocal('/api/voice/provider', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: $('voice').value }), signal: AbortSignal.timeout(7000),
    });
    if (!response.ok) throw await httpError(response);
    voiceStatus = await response.json(); status('Голос изменён', 'Настройка общая для этого локального backend.');
  } catch (error) { voiceStatus = prior; status('Не удалось сменить голос', error.message, true); }
  finally { connecting = false; renderVoice(); updateControls(); }
});
$('micPermission').addEventListener('click', () => {
  chrome.tabs.create({ url: chrome.runtime.getURL('microphone.html') });
});
$('saveSettings').addEventListener('click', async () => {
  if (active()) return;
  try {
    const next = localBackend($('backendUrl').value);
    resetSession(); backend = next; $('backendUrl').value = next;
    await chrome.storage.local.set({ backendUrl: next }); await connect();
  } catch (error) { status('Адрес не сохранён', error.message, true); }
});
$('reconnect').addEventListener('click', connect);
window.addEventListener('pagehide', () => { stopWork(false); clearInput(); clearResult(); });

async function init() {
  try {
    const saved = await chrome.storage.local.get(['backendUrl', 'language']);
    if (saved.backendUrl) backend = localBackend(saved.backendUrl);
    if (['uz', 'kk'].includes(saved.language)) $('language').value = saved.language;
  } catch { backend = DEFAULT_BACKEND; }
  $('backendUrl').value = backend; await connect();
}
init();
