"""Bounded, thread-safe in-memory conversation history for the local demo."""

import threading
import time
from collections import OrderedDict

from product.backend.config import settings


class SessionManager:
    """Keep up to 1000 sessions; expire history after one hour of inactivity.

    Unknown-session reads never allocate storage. History is lost on restart;
    this is still a single-process demo store, not a multi-worker database.
    """

    def __init__(self, max_sessions=1000, idle_timeout_seconds=3600):
        if max_sessions < 1 or idle_timeout_seconds <= 0:
            raise ValueError('Session capacity and idle timeout must be positive')
        self.max_sessions = max_sessions
        self.idle_timeout_seconds = idle_timeout_seconds
        self._sessions = OrderedDict()
        self._created = {}
        self._last_used = {}
        self._lock = threading.RLock()

    def _remove(self, conversation_id):
        self._sessions.pop(conversation_id, None)
        self._created.pop(conversation_id, None)
        self._last_used.pop(conversation_id, None)

    def _prune(self, now):
        # LRU order follows last access, so only the expired prefix needs scanning.
        while self._sessions:
            oldest = next(iter(self._sessions))
            if now - self._last_used.get(oldest, now) < self.idle_timeout_seconds:
                break
            self._remove(oldest)

    def _touch(self, conversation_id, now):
        self._last_used[conversation_id] = now
        self._sessions.move_to_end(conversation_id)

    def add_turn(self, conversation_id: str, role: str, message: str) -> None:
        with self._lock:
            now = time.monotonic()
            self._prune(now)
            if conversation_id not in self._sessions:
                while len(self._sessions) >= self.max_sessions:
                    self._remove(next(iter(self._sessions)))
                self._sessions[conversation_id] = []
                self._created[conversation_id] = now
            self._touch(conversation_id, now)
            self._sessions[conversation_id].append({
                'role': role, 'content': message, 'timestamp': time.time(),
            })

    def get_history(self, conversation_id: str) -> list[dict]:
        with self._lock:
            now = time.monotonic()
            self._prune(now)
            if conversation_id not in self._sessions:
                return []
            self._touch(conversation_id, now)
            # Callers cannot mutate the stored dictionaries through a shallow list copy.
            return [dict(message) for message in self._sessions[conversation_id]]

    def get_turn_count(self, conversation_id: str) -> int:
        return sum(message['role'] == 'user' for message in self.get_history(conversation_id))

    def is_max_turns_reached(self, conversation_id: str) -> bool:
        return self.get_turn_count(conversation_id) >= settings.max_turns_per_session

    def session_age(self, conversation_id: str) -> float:
        with self._lock:
            now = time.monotonic()
            self._prune(now)
            created = self._created.get(conversation_id)
            return max(0.0, now - created) if created is not None else 0.0


session_manager = SessionManager()
