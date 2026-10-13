// Shared protocol code: no Chrome APIs, DOM, credentials or model calls.
export const DEFAULT_BACKEND = 'http://127.0.0.1:8000';
export const MAX_WAV_BYTES = 32 * 1024 * 1024;

export function localBackend(value) {
  let u;
  try { u = new URL(value); } catch { throw new Error('Укажите адрес вида http://127.0.0.1:8000.'); }
  if (u.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(u.hostname) ||
      u.username || u.password || u.search || u.hash || !['', '/'].includes(u.pathname)) {
    throw new Error('Разрешён только HTTP-адрес localhost или 127.0.0.1 без пути и пароля.');
  }
  return u.origin;
}

export function makeTurnForm(audio, conversationId, language) {
  if (!['uz', 'kk'].includes(language)) throw new Error('Неизвестный язык.');
  const form = new FormData();
  form.append('audio', audio, audio.type.includes('webm') ? 'recording.webm' : 'recording.wav');
  form.append('conversation_id', conversationId);
  form.append('language', language);
  form.append('mode', 'dub');
  form.append('source_language', 'en');
  return form;
}

export async function readNDJSON(body, onEvent, signal) {
  if (!body) throw new Error('Сервер не предоставил поток ответа.');
  const reader = body.getReader();
  const decoder = new TextDecoder('utf-8', { fatal: true });
  let pending = '', completed = false, sawMeta = false, nextIndex = 0;
  const abort = () => { reader.cancel().catch(() => {}); };
  signal?.addEventListener('abort', abort, { once: true });
  function dispatch(line) {
    if (!line.trim()) return;
    signal?.throwIfAborted();
    if (completed) throw new Error('Данные после завершения ответа.');
    let ev;
    try { ev = JSON.parse(line); } catch { throw new Error('Повреждённый JSON в ответе сервера.'); }
    if (ev.type === 'error') throw new Error(typeof ev.detail === 'string' ? ev.detail : 'Ошибка обработки на сервере.');
    if (ev.type === 'meta') {
      if (sawMeta || nextIndex) throw new Error('Некорректный порядок ответа.');
      sawMeta = true;
    } else if (ev.type === 'part') {
      if (!sawMeta || ev.index !== nextIndex || typeof ev.audio !== 'string' || !ev.audio) {
        throw new Error('Пропущена или повреждена часть аудио.');
      }
      nextIndex++;
    } else if (ev.type === 'done') {
      if (!sawMeta || !nextIndex || typeof ev.audio !== 'string' || !ev.audio) {
        throw new Error('Ответ завершён без готового аудио.');
      }
      completed = true;
    } else {
      throw new Error('Неизвестное событие ответа сервера.');
    }
    onEvent(ev);
  }
  try {
    while (true) {
      signal?.throwIfAborted();
      const chunk = await reader.read();
      signal?.throwIfAborted();
      pending += decoder.decode(chunk.value, { stream: !chunk.done });
      // Large enough for a full WAV but bounded against unbounded responses.
      if (pending.length > MAX_WAV_BYTES * 5) throw new Error('Слишком большой ответ сервера.');
      let at;
      while ((at = pending.indexOf('\n')) !== -1) {
        dispatch(pending.slice(0, at));
        pending = pending.slice(at + 1);
      }
      if (chunk.done) break;
    }
    if (pending.trim()) dispatch(pending);
    if (!completed) throw new Error('Поток оборвался. Полный ответ не получен.');
  } finally {
    signal?.removeEventListener('abort', abort);
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

export function wavBlob(base64) {
  if (typeof base64 !== 'string' || base64.length > Math.ceil(MAX_WAV_BYTES / 3) * 4) {
    throw new Error('Аудио слишком большое или отсутствует.');
  }
  let decoded;
  try { decoded = atob(base64); } catch { throw new Error('Повреждённое кодирование аудио.'); }
  const bytes = Uint8Array.from(decoded, c => c.charCodeAt(0));
  const view = new DataView(bytes.buffer);
  const tag = at => String.fromCharCode(...bytes.slice(at, at + 4));
  if (bytes.length < 44 || tag(0) !== 'RIFF' || tag(8) !== 'WAVE' ||
      view.getUint32(4, true) + 8 > bytes.length) throw new Error('Повреждённый WAV от сервера.');
  let fmt = false, data = false;
  for (let p = 12; p + 8 <= bytes.length;) {
    const n = view.getUint32(p + 4, true), end = p + 8 + n;
    if (end > bytes.length) throw new Error('Обрезанный WAV от сервера.');
    if (tag(p) === 'fmt ') {
      if (n < 16 || ![1, 3, 65534].includes(view.getUint16(p + 8, true))) {
        throw new Error('Неподдерживаемый формат WAV.');
      }
      fmt = true;
    }
    if (tag(p) === 'data' && n > 0) data = true;
    p = end + (n & 1);
  }
  if (!fmt || !data) throw new Error('WAV не содержит пригодного аудио.');
  return new Blob([bytes], { type: 'audio/wav' });
}

export function voiceOptions(status) {
  const result = [{ value: 'openai', label: 'Стандартный · OpenAI' }];
  if (status?.local_clone?.configured) result.push({ value: 'local-clone', label: 'Мой голос · локально (uz)' });
  if (status?.elevenlabs?.configured) result.push({ value: 'elevenlabs', label: 'Мой голос · ElevenLabs' });
  return result;
}

export function providerLabel(info = {}) {
  if (info.demo) return 'DEMO · тестовые звуки';
  if (info.mock_mode) return 'MOCK · не реальный синтез';
  const label = info.tts || 'Провайдер не указан';
  return /fallback/i.test(label) || info.fallback || info.tts_fallback ? `FALLBACK · ${label}` : label;
}

// Deterministic local fixture. Not speech, not a model-quality sample.
export function demoWav(frequency = 440, seconds = 0.45) {
  const rate = 16000, n = Math.round(rate * seconds);
  const bytes = new Uint8Array(44 + n * 2), view = new DataView(bytes.buffer);
  const put = (at, str) => [...str].forEach((c, i) => bytes[at + i] = c.charCodeAt(0));
  put(0, 'RIFF'); view.setUint32(4, bytes.length - 8, true); put(8, 'WAVE'); put(12, 'fmt ');
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, rate, true); view.setUint32(28, rate * 2, true);
  view.setUint16(32, 2, true); view.setUint16(34, 16, true); put(36, 'data'); view.setUint32(40, n * 2, true);
  for (let i = 0; i < n; i++) {
    const envelope = Math.min(1, i / 300, (n - i) / 300);
    view.setInt16(44 + i * 2, Math.sin(i * 2 * Math.PI * frequency / rate) * 2000 * envelope, true);
  }
  let binary = '';
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary);
}
