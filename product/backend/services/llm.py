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