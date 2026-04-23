"""Tests for chat session store (in-memory + Redis mock)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from sales_agent.session import (
    InMemorySessionStore,
    new_session_id,
    set_session_store,
)
from sales_agent.session.store import RedisSessionStore


def test_new_session_id_is_unique() -> None:
    seen = {new_session_id() for _ in range(100)}
    assert len(seen) == 100


def test_in_memory_store_roundtrip() -> None:
    s = InMemorySessionStore()
    sid = new_session_id()
    assert s.get(sid) is None
    s.set(sid, {"pending": {"q": "hi"}, "turn": 1})
    assert s.get(sid) == {"pending": {"q": "hi"}, "turn": 1}
    s.delete(sid)
    assert s.get(sid) is None


def test_redis_store_uses_prefix_and_ttl() -> None:
    fake_client = MagicMock()
    store = RedisSessionStore.__new__(RedisSessionStore)
    store._client = fake_client
    store._ttl = 60

    store.set("abc", {"foo": "bar"})
    args, kwargs = fake_client.set.call_args
    assert args[0] == "chat:abc"
    # value is JSON with Vietnamese chars preserved (ensure_ascii=False)
    assert '"foo"' in args[1] and '"bar"' in args[1]
    assert kwargs.get("ex") == 60


def test_redis_store_get_returns_parsed_dict() -> None:
    fake_client = MagicMock()
    fake_client.get.return_value = '{"foo":"bar","n":1}'
    store = RedisSessionStore.__new__(RedisSessionStore)
    store._client = fake_client
    store._ttl = 60

    result = store.get("abc")
    assert result == {"foo": "bar", "n": 1}
    fake_client.get.assert_called_once_with("chat:abc")


def test_redis_store_get_none_when_missing() -> None:
    fake_client = MagicMock()
    fake_client.get.return_value = None
    store = RedisSessionStore.__new__(RedisSessionStore)
    store._client = fake_client
    store._ttl = 60

    assert store.get("missing") is None


def test_redis_store_corrupt_json_drops_key() -> None:
    fake_client = MagicMock()
    fake_client.get.return_value = "not-json{"
    store = RedisSessionStore.__new__(RedisSessionStore)
    store._client = fake_client
    store._ttl = 60

    assert store.get("abc") is None
    fake_client.delete.assert_called_once_with("chat:abc")


def test_set_session_store_overrides_singleton() -> None:
    fake = InMemorySessionStore()
    set_session_store(fake)
    from sales_agent.session import get_session_store

    assert get_session_store() is fake
    # Clean up.
    set_session_store(InMemorySessionStore())
