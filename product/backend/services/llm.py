"""
LLM conversation service.

OpenAI gpt-4o-mini — cheap, multilingual, handles Uzbek/Kazakh well.
Generates conversational response in the same language as user input.
"""

import logging
from typing import Optional

from openai import OpenAI, APIError

from product.backend.config import settings
from product.backend.services.session import session_manager

logger = logging.getLogger(__name__)


# ---------- Mock LLM ----------

MOCK_RESPONSES = {
    "uz": "Kechirasiz, hozircha sun'iy intellekt sozlanmagan. Iltimos, OPENAI_API_KEY ni o'rnating va qayta urinib ko'ring.",
    "kk": "Кешіріңіз, әзірге жасанды интеллект конфигурацияланбаған. OPENAI_API_KEY орнатып, қайталап көріңіз.",
}


def _mock_respond(conversation_id: str, transcript: str, language: str) -> str:
    logger.info("MOCK LLM returning canned response for %s", language)
    session_manager.add_turn(conversation_id, "user", transcript)
    reply = MOCK_RESPONSES.get(language, MOCK_RESPONSES["uz"])
    session_manager.add_turn(conversation_id, "assistant", reply)
    return reply


# ---------- Real LLM (OpenAI) ----------

SYSTEM_PROMPTS = {
    "uz": (
        "Siz foydali, qisqa va aniq javob beradigan yordamchisiz. "
        "Foydalanuvchi bilan doim **o'zbek tilida** gaplashing. "
        "Javoblaringiz qisqa va lo'nda bo'lsin — 2-3 jumladan oshmasin."
    ),
    "kk": (
        "Сіз пайдалы, қысқа және нақты жауап беретін көмекшісіз. "
        "Пайдаланушымен әрқашан **қазақ тілінде** сөйлесіңіз. "
        "Жауаптарыңыз қысқа және нұсқа болсын — 2-3 сөйлемнен аспасын."
    ),
}


def _openai_respond(
    conversation_id: str,
    transcript: str,
    language: str,
) -> str:
    """Generate a conversational response using OpenAI chat completions."""
    client = OpenAI(api_key=settings.openai_api_key, timeout=30.0)

    # Build message history
    messages = [{"role": "system", "content": SYSTEM_PROMPTS.get(language, SYSTEM_PROMPTS["uz"])}]

    # Add conversation history
    for turn in session_manager.get_history(conversation_id):
        messages.append({"role": turn["role"], "content": turn["content"]})

    # Add current user input
    messages.append({"role": "user", "content": transcript})

    last_err = None
    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                max_tokens=300,
                temperature=0.7,
                timeout=30.0,
            )
            reply = response.choices[0].message.content.strip()
            # Store both sides only on success
            session_manager.add_turn(conversation_id, "user", transcript)
            session_manager.add_turn(conversation_id, "assistant", reply)
            return reply
        except APIError as e:
            last_err = e
            logger.warning("LLM attempt %d failed: %s", attempt + 1, e)
            if attempt == 1:
                raise last_err
    return ""  # unreachable


# ---------- Public API ----------

def respond(conversation_id: str, transcript: str, language: str) -> str:
    """Generate an AI response to the user's transcribed speech.

    Args:
        conversation_id: Session identifier.
        transcript: Transcribed user speech text.
        language: ISO code ('uz' or 'kk').

    Returns:
        AI response text in the same language.
    """
    if settings.mock_mode:
        return _mock_respond(conversation_id, transcript, language)

    return _openai_respond(conversation_id, transcript, language)


# =========================================================================
# DUB1 — stateless translation (English -> Uzbek/Kazakh) for dub mode.
# Deliberately does NOT read or write session history: dubbing is a
# one-shot translation, not a conversation.
# =========================================================================

MOCK_DUB_PHRASES = {
    "uz": {
        "hello, this is an english test voice": "Salom, bu inglizcha test ovozi.",
        "hello": "Salom.",
        "hi": "Salom.",
        "how are you": "Qalaysiz?",
        "thank you": "Rahmat.",
        "goodbye": "Xayr.",
        "see you tomorrow": "Ertaga ko'rishamiz.",
        "where is the nearest station": "Eng yaqin bekat qayerda?",
        "i would like a coffee please": "Bir stakan qahva kerak edi, iltimos.",
        "my name is alex": "Mening ismim Alex.",
    },
    "kk": {
        "hello, this is an english test voice": "Сәлем, бұл ағылшынша тест дауысы.",
        "hello": "Сәлем.",
        "hi": "Сәлем.",
        "how are you": "Қалыңыз қалай?",
        "thank you": "Рахмет.",
        "goodbye": "Сау болыңыз.",
        "see you tomorrow": "Ертең көрісеміз.",
        "where is the nearest station": "Ең жақын бекет қайда?",
        "i would like a coffee please": "Бір стақан кофе керек еді, өтінемін.",
        "my name is alex": "Менің атым Алекс.",
    },
}

# Deterministic word-level fallback for phrases the map does not know.
# Mock quality only; grammatical perfection is explicitly not promised.
MOCK_DUB_WORDS = {
    "uz": {
        "hello": "salom", "hi": "salom", "thanks": "rahmat", "please": "iltimos",
        "yes": "ha", "no": "yo'q", "good": "yaxshi", "bad": "yomon",
        "very": "juda", "today": "bugun", "tomorrow": "ertaga",
        "friend": "do'st", "water": "suv", "coffee": "qahva", "tea": "choy",
        "bread": "non", "name": "ism", "my": "mening", "you": "siz", "where": "qayerda",
    },
    "kk": {
        "hello": "сәлем", "hi": "сәлем", "thanks": "рахмет", "please": "өтінемін",
        "yes": "иә", "no": "жоқ", "good": "жақсы", "bad": "жаман",
        "very": "өте", "today": "бүгін", "tomorrow": "ертең",
        "friend": "дос", "water": "су", "coffee": "кофе", "tea": "шай",
        "bread": "нан", "name": "есім", "my": "менің", "you": "сіз", "where": "қайда",
    },
}


def _normalize_english(text: str) -> str:
    """Lowercase, collapse whitespace, strip trailing punctuation (deterministic)."""
    norm = " ".join(text.strip().lower().split())
    return norm.rstrip(".,!?;:")


def _mock_translate(text: str, target_language: str) -> str:
    """Deterministic mock English -> uz/kk translation (exact phrase map,
    then word-level fallback, then pass-through of unknown words)."""
    norm = _normalize_english(text)
    phrases = MOCK_DUB_PHRASES.get(target_language, {})
    if norm in phrases:
        logger.info("MOCK translate: exact phrase hit (%s)", target_language)
        return phrases[norm]

    words = MOCK_DUB_WORDS.get(target_language, {})
    out_tokens = []
    for tok in norm.split():
        prefix = tok[: len(tok) - len(tok.lstrip(".,!?;:("))]
        core = tok.strip(".,!?;:()")
        suffix = tok[len(tok.rstrip(".,!?;:)")) :]
        rep = words.get(core)
        out_tokens.append(prefix + (rep if rep is not None else core) + suffix)
    joined = " ".join(out_tokens)
    if joined:
        joined = joined[0].upper() + joined[1:]
        if not joined.endswith((".", "!", "?")):
            joined += "."
    logger.info("MOCK translate: word-fallback to %s", target_language)
    return joined or text.strip()


TRANSLATE_SYSTEM_PROMPTS = {
    "uz": (
        "You are a professional interpreter. Translate the user's English "
        "message into natural, conversational Uzbek (Latin script). "
        "Preserve meaning, tone and intent. Output ONLY the translated "
        "text — no quotes, no notes, no explanations. Keep the reply short "
        "(max 3 sentences)."
    ),
    "kk": (
        "You are a professional interpreter. Translate the user's English "
        "message into natural, conversational Kazakh (Cyrillic script). "
        "Preserve meaning, tone and intent. Output ONLY the translated "
        "text — no quotes, no notes, no explanations. Keep the reply short "
        "(max 3 sentences)."
    ),
}


def _openai_translate(text: str, target_language: str) -> str:
    """Stateless single-shot translation via OpenAI chat completions.

    Mirrors the retry pattern used by respond(): two attempts, raise on the
    second APIError. No conversation history is read or written.
    """
    client = OpenAI(api_key=settings.openai_api_key, timeout=30.0)
    messages = [
        {"role": "system", "content": TRANSLATE_SYSTEM_PROMPTS[target_language]},
        {"role": "user", "content": text},
    ]
    last_err = None
    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                max_tokens=300,
                temperature=0.0,  # deterministic translation
                timeout=30.0,
            )
            return response.choices[0].message.content.strip()
        except APIError as e:
            last_err = e
            logger.warning("Translate attempt %d failed: %s", attempt + 1, e)
            if attempt == 1:
                raise last_err
    return ""  # unreachable


def translate(text: str, source_language: str, target_language: str) -> str:
    """Translate text from source_language into target_language (stateless).

    Args:
        text: Source text (e.g. the English transcript).
        source_language: ISO code of the source ('en' in DUB1).
        target_language: ISO code for output ('uz' or 'kk').

    Returns:
        Translated text in the target language.
    """
    if settings.mock_mode:
        return _mock_translate(text, target_language)

    return _openai_translate(text, target_language)