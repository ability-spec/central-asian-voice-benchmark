"""
In-memory conversation session manager.

Stores conversation history per conversation_id.
Max 20 turns per session.
Data is lost on server restart — no database.
"""

import time
from collections import defaultdict
from typing import Optional

from product.backend.config import settings


class SessionManager:
    """Lightweight in-memory store for multi-turn dialogue history."""

    def __init__(self):
        self._sessions: dict[str, list[dict]] = defaultdict(list)
        self._created: dict[str, float] = {}

    def _ensure_session(self, conversation_id: str) -> None:
        if conversation_id not in self._created:
            self._created[conversation_id] = time.time()

    def add_turn(
        self,
        conversation_id: str,
        role: str,
        message: str,
    ) -> None:
        self._ensure_session(conversation_id)
        self._sessions[conversation_id].append({
            "role": role,
            "content": message,
            "timestamp": time.time(),
        })

    def get_history(self, conversation_id: str) -> list[dict]:
        """Return the full conversation history as role/content pairs."""
        self._ensure_session(conversation_id)
        return list(self._sessions[conversation_id])

    def get_turn_count(self, conversation_id: str) -> int:
        """Number of user turns so far (half the total messages)."""
        self._ensure_session(conversation_id)
        return sum(
            1 for m in self._sessions[conversation_id] if m["role"] == "user"
        )

    def is_max_turns_reached(self, conversation_id: str) -> bool:
        return self.get_turn_count(conversation_id) >= settings.max_turns_per_session

    def session_age(self, conversation_id: str) -> float:
        """Seconds since session creation."""
        if conversation_id not in self._created:
            return 0.0
        return time.time() - self._created[conversation_id]


# Singleton
session_manager = SessionManager()