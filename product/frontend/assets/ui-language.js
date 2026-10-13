/* Interface locale only: never changes synthesis language or request data. */
const uzInterfaceText = {
  'Workspace': 'Ish maydoni',
  'How it works': 'Qanday ishlaydi',
  'Try BirOvoz ↗': 'Sinab ko‘rish ↗',
  'Open workspace ↓': 'Boshlash ↓',
  'Your voice workspace': 'Ovoz bilan ishlash',
  'TRANSLATE TO': 'TARJIMA TILI',
  'VOICE': 'OVOZ',
  'Uzbek': 'O‘zbekcha',
  'Kazakh': 'Qozoqcha',
  'My voice': 'Mening ovozim',
  'Standard': 'Standart',
  'Cloud voice': 'Bulutli ovoz',
  'Local · Uzbek only': 'Mahalliy · faqat o‘zbekcha',
  'Checking availability': 'Mavjudligi tekshirilmoqda',
  'Checking voice availability…': 'Ovoz xizmati tekshirilmoqda…',
  'My voice uses local Uzbek models. First request may take longer while models load.': 'Mening ovozim mahalliy o‘zbek modellaridan foydalanadi. Modellar yuklanayotganda birinchi so‘rov ko‘proq vaqt olishi mumkin.',
  'Kazakh local clone is unavailable. Standard voice will be used.': 'Qozoqcha ovoz klonlash mavjud emas. Standart ovoz ishlatiladi.',
  'Text-to-speech input is not available in this version.': 'Bu versiyada matn kiritib ovoz yaratish mavjud emas.',
  'English dubbing': 'Inglizchadan ovozli tarjima',
  'Microphone → voice': 'Mikrofon → ovoz',
  'Ready to record': 'Yozib olishga tayyor',
  'Your microphone will open when you start.': 'Boshlaganingizda mikrofon yoqiladi.',
  'Start with an English recording': 'Inglizcha gapni yozib olishdan boshlang',
  'Your transcript, translation and audio will appear here.': 'Tanilgan matn, tarjima va audio shu yerda chiqadi.',
  'Send automatically after a pause': 'Pauzadan keyin avtomatik yuborish',
  'Recording and Retry send audio to paid OpenAI transcription and translation APIs. Standard voice also uses paid TTS. Local Uzbek voice may have a cold start.': 'Yozuv va qayta urinish pulli OpenAI nutqni tanish va tarjima API xizmatlaridan foydalanadi. Standart ovoz ham pulli TTS ishlatadi. Mahalliy o‘zbek ovozi birinchi safar sekinroq ishga tushishi mumkin.',
  'Start recording': 'Yozishni boshlash',
  'Stop': 'To‘xtatish',
  'Send recording': 'Yozuvni yuborish',
  'Retry paid request': 'Pulli so‘rovni takrorlash',
  'Dismiss': 'Yopish',
  'Play again': 'Qayta tinglash',
  'Download WAV': 'WAV yuklab olish',
  'Provider and timing': 'Provayder va vaqtlar',
  'Stopped': 'To‘xtatildi',
  'Playback stopped · connection closed · running server work may finish': 'Audio to‘xtatildi · ulanish yopildi · boshlangan server hisoblashlari davom etishi mumkin',
  'Speak English — tap to record': 'Inglizcha gapiring — yozish uchun bosing',
  'Tap once to start · auto-send on pause · tap to send now': 'Boshlash uchun bosing · pauzada avtomatik yuboriladi · darhol yuborish uchun yana bosing',
  'Listening — speak now': 'Tinglanmoqda — gapiring',
  'Pause ~1 s or press Send recording · tap mic to cancel': 'Taxminan 1 soniya pauza qiling yoki yozuvni yuboring · bekor qilish uchun mikrofonni bosing',
  'Recording English…': 'Inglizcha nutq yozilmoqda…',
  'Tap to stop recording': 'Yozishni to‘xtatish uchun bosing',
  'Dubbing…': 'Ovozli tarjima tayyorlanmoqda…',
  'English → STT → translate → TTS': 'Inglizcha → nutqni tanish → tarjima → ovoz yaratish',
  'Playing dubbed reply…': 'Tarjima ovozi ijro etilmoqda…',
  'Tap mic to interrupt': 'To‘xtatib gapirish uchun mikrofonni bosing',
  'Error — tap Retry': 'Xatolik — qayta urinib ko‘ring',
  'Sending…': 'Yuborilmoqda…',
  'Requesting microphone…': 'Mikrofon so‘ralmoqda…',
  'Preparing recording…': 'Yozuv tayyorlanmoqda…',
  'Maximum recording time reached': 'Yozuv vaqti chegarasiga yetildi',
  'Still processing — finish current dub first': 'Hali tayyorlanmoqda — joriy tarjima tugashini kuting',
  'Capture was too small to use — tap to try again': 'Yozuv juda qisqa — qayta urinish uchun bosing',
  'Say a full sentence (~1 s) and try again': 'To‘liq gap ayting (taxminan 1 soniya) va qayta urinib ko‘ring',
  'Speak, then press Send recording · maximum 30 s': 'Gapiring, so‘ng yozuvni yuboring · ko‘pi bilan 30 soniya',
  'Voice service unavailable': 'Ovoz xizmati mavjud emas',
  'One recording. Another language.': 'Bir yozuv. Boshqa til.',
  'BirOvoz transcribes your English recording, translates it, then plays the dubbed voice. Uzbek can use local Sayro + Seed-VC; Kazakh uses standard cloud TTS.': 'BirOvoz inglizcha yozuvingizni matnga aylantiradi, tarjima qiladi va ovozli tarjimani ijro etadi. O‘zbekcha uchun mahalliy Sayro + Seed-VC, qozoqcha uchun standart bulutli TTS ishlatiladi.',
  'Transcription and translation use paid APIs. Local Uzbek models load on demand. Stop clears playback and the browser connection; already-started model work may continue.': 'Nutqni tanish va tarjima pulli API xizmatlaridan foydalanadi. Mahalliy o‘zbek modellari zarur bo‘lganda yuklanadi. To‘xtatish audio va brauzer ulanishini tozalaydi; boshlangan model hisoblashlari davom etishi mumkin.',
  'Live session results are not the frozen benchmark. No benchmark data is changed by this tool.': 'Jonli sessiya natijalari oldindan saqlangan benchmark emas. Bu vosita benchmark ma’lumotlarini o‘zgartirmaydi.'
};
let uiLanguage = 'uz';
const interfaceSources = new WeakMap();
const interfaceRoot = document.getElementById('app');
const interfaceObserver = new MutationObserver(renderInterfaceLanguage);

function renderInterfaceLanguage() {
  interfaceObserver.disconnect();
  try {
    const walker = document.createTreeWalker(interfaceRoot, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      // Spoken/transcribed content and raw diagnostic errors stay verbatim.
      if (node.parentElement.closest('.msg-text,.provider-line,#errorMsg,script,style,[data-ui-language]')) continue;
      const previous = interfaceSources.get(node);
      const source = previous && node.data === previous.rendered ? previous.source : node.data;
      const trimmed = source.trim();
      const translated = uiLanguage === 'uz' ? uzInterfaceText[trimmed] : null;
      const rendered = translated ? source.replace(trimmed, translated) : source;
      interfaceSources.set(node, {source, rendered});
      if (node.data !== rendered) node.data = rendered;
    }
    document.documentElement.lang = uiLanguage;
    document.querySelectorAll('[data-ui-language]').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.uiLanguage === uiLanguage));
    });
    const mic = document.getElementById('micBtn');
    mic.setAttribute('aria-label', document.getElementById('micLabel').textContent);
  } finally {
    interfaceObserver.observe(interfaceRoot, {subtree:true, childList:true, characterData:true});
  }
}

function setUiLanguage(locale) {
  if (locale !== 'uz' && locale !== 'en') return;
  uiLanguage = locale;
  renderInterfaceLanguage();
}
renderInterfaceLanguage();
