"""Chat session store for multi-turn clarification flows.

Two backends:
- ``RedisSessionStore`` for production (Redis with TTL).
- ``InMemorySessionStore`` for tests.

Both conform to the ``SessionStore`` Protocol. Sessions are JSON-serialisable
dicts (the caller is responsible for what goes in).
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Protocol

from ..config import get_settings

logger = logging.getLogger(__name__)

_KEY_PREFIX = "chat:"


def new_session_id() -> str:
    return str(uuid.uuid4())


class SessionStore(Protocol):
    def get(self, session_id: str) -> dict[str, Any] | None: ...
    def set(self, session_id: str, state: dict[str, Any]) -> None: ...
    def delete(self, session_id: str) -> None: ...


class InMemorySessionStore:
    """Single-process dict store with no TTL enforcement (test fixture)."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}

    def get(self, session_id: str) -> dict[str, Any] | None:
        return self._data.get(session_id)

    def set(self, session_id: str, state: dict[str, Any]) -> None:
        self._data[session_id] = state

    def delete(self, session_id: str) -> None:
        self._data.pop(session_id, None)


class RedisSessionStore:
    """Redis-backed store with per-key TTL."""

    def __init__(self, url: str, ttl_s: int) -> None:
        import redis  # local import so tests don't require the lib.

        self._client = redis.Redis.from_url(url, decode_responses=True)
        self._ttl = ttl_s

    def _key(self, session_id: str) -> str:
        return _KEY_PREFIX + session_id

    def get(self, session_id: str) -> dict[str, Any] | None:
        raw = self._client.get(self._key(session_id))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("session %s has invalid JSON; dropping", session_id)
            self.delete(session_id)
            return None

    def set(self, session_id: str, state: dict[str, Any]) -> None:
        self._client.set(
            self._key(session_id),
            json.dumps(state, ensure_ascii=False, default=str),
            ex=self._ttl,
        )

    def delete(self, session_id: str) -> None:
        self._client.delete(self._key(session_id))


_singleton: SessionStore | None = None


def get_session_store() -> SessionStore:
    """Return the process-wide session store, constructing on first use."""
    global _singleton
    if _singleton is None:
        s = get_settings()
        _singleton = RedisSessionStore(s.redis_url, s.chat_session_ttl_s)
    return _singleton


def set_session_store(store: SessionStore) -> None:
    """Override the singleton (used by tests)."""
    global _singleton
    _singleton = store
