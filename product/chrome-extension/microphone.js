document.getElementById('allowMic').addEventListener('click', async () => {
  const button = document.getElementById('allowMic');
  button.disabled = true;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach(track => track.stop());
    document.getElementById('micStatus').textContent = 'Разрешение получено. Можно закрыть эту вкладку.';
  } catch {
    document.getElementById('micStatus').textContent = 'Доступ не получен. Проверь разрешения сайта в Chrome и доступ к микрофону в Windows.';
  } finally { button.disabled = false; }
});
