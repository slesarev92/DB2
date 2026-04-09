"""Тесты Redis cache + dedupe слоя (Phase 7.2).

Моки — через `fakeredis` был бы идеален, но он не в requirements и
нужен только для этих тестов. Вместо этого подменяем singleton клиент
на AsyncMock — у нас чистая API surface (get/set/delete/set nx=True),
легко заmock'ать.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from redis.exceptions import RedisError

from app.services import ai_cache
from app.services.ai_cache import (
    acquire_dedupe_lock,
    get_cached,
    hash_context,
    make_cache_key,
    make_lock_key,
    release_dedupe_lock,
    reset_redis_cache,
    set_cached,
    wait_for_cache,
)
from app.services.ai_service import AIFeature


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def _reset_cache_singleton():
    reset_redis_cache()
    yield
    reset_redis_cache()


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Подменяет `_get_redis_client` на mock с AsyncMock методами."""
    client = MagicMock()
    client.get = AsyncMock(return_value=None)
    client.set = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=1)

    monkeypatch.setattr(ai_cache, "_get_redis_client", lambda: client)
    return client


# ============================================================
# Hash stability
# ============================================================


def test_hash_context_is_stable() -> None:
    """Одинаковые dict'ы в разном порядке дают одинаковый хеш."""
    ctx1 = {"project": {"id": 1, "name": "A"}, "scope": "y1y5"}
    ctx2 = {"scope": "y1y5", "project": {"name": "A", "id": 1}}

    assert hash_context(ctx1) == hash_context(ctx2)


def test_hash_context_detects_differences() -> None:
    """Разные dict'ы дают разные хеши."""
    ctx1 = {"id": 1}
    ctx2 = {"id": 2}

    assert hash_context(ctx1) != hash_context(ctx2)


def test_hash_context_returns_hex_string() -> None:
    """SHA-256 hex → 64 символа."""
    h = hash_context({"a": 1})
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


# ============================================================
# Cache keys
# ============================================================


def test_make_cache_key_format() -> None:
    key = make_cache_key(42, AIFeature.EXPLAIN_KPI, "abc123")
    assert key == "ai_cache:42:explain_kpi:abc123"


def test_make_lock_key_format() -> None:
    key = make_lock_key(42, AIFeature.EXPLAIN_KPI, "abc123")
    assert key == "ai_lock:42:explain_kpi:abc123"


# ============================================================
# get/set cached
# ============================================================


async def test_get_cached_miss_returns_none(fake_redis: MagicMock) -> None:
    """Ключа нет → None, не падение."""
    fake_redis.get.return_value = None
    result = await get_cached("ai_cache:1:explain_kpi:xyz")
    assert result is None


async def test_get_cached_hit_returns_dict(fake_redis: MagicMock) -> None:
    """Redis возвращает JSON-строку → парсим в dict."""
    cached_value = {"summary": "cached", "cost_rub": 2.4}
    fake_redis.get.return_value = json.dumps(cached_value)

    result = await get_cached("ai_cache:1:explain_kpi:xyz")
    assert result == cached_value


async def test_get_cached_redis_error_returns_none(fake_redis: MagicMock) -> None:
    """Redis недоступен → None (graceful degradation, не исключение)."""
    fake_redis.get.side_effect = RedisError("connection refused")

    result = await get_cached("ai_cache:1:explain_kpi:xyz")
    assert result is None


async def test_get_cached_corrupt_json_returns_none(fake_redis: MagicMock) -> None:
    """Corrupt cached value → None + log warning."""
    fake_redis.get.return_value = "not valid json {"

    result = await get_cached("ai_cache:1:explain_kpi:xyz")
    assert result is None


async def test_set_cached_writes_json_with_ttl(fake_redis: MagicMock) -> None:
    """SET с JSON + EX=86400."""
    await set_cached("ai_cache:1:explain_kpi:xyz", {"foo": "bar"})

    fake_redis.set.assert_awaited_once()
    args, kwargs = fake_redis.set.await_args
    assert args[0] == "ai_cache:1:explain_kpi:xyz"
    assert json.loads(args[1]) == {"foo": "bar"}
    assert kwargs["ex"] == 86400


async def test_set_cached_redis_error_does_not_raise(
    fake_redis: MagicMock,
) -> None:
    """Ошибка записи — молча логируем, не падаем."""
    fake_redis.set.side_effect = RedisError("oom")
    # Не должно поднять исключение
    await set_cached("k", {"a": 1})


# ============================================================
# Dedupe lock
# ============================================================


async def test_acquire_dedupe_lock_success(fake_redis: MagicMock) -> None:
    """SETNX вернул True → получили lock."""
    fake_redis.set.return_value = True
    acquired = await acquire_dedupe_lock("ai_lock:1:explain_kpi:xyz")

    assert acquired is True
    # Проверяем что SET вызван с nx=True + ex=60
    args, kwargs = fake_redis.set.await_args
    assert kwargs["nx"] is True
    assert kwargs["ex"] == 60


async def test_acquire_dedupe_lock_contention(fake_redis: MagicMock) -> None:
    """SETNX вернул False → другой уже держит → False."""
    fake_redis.set.return_value = None  # nx=True при contention даёт None

    acquired = await acquire_dedupe_lock("ai_lock:1:explain_kpi:xyz")
    assert acquired is False


async def test_acquire_dedupe_lock_redis_error_is_master(
    fake_redis: MagicMock,
) -> None:
    """Redis ошибка → fallback: этот вызов — master (чтобы не стоп).

    Это conservative choice: при недоступности Redis мы теряем dedupe
    (хуже чем нормально) но не блокируем вызов (лучше чем полный стоп).
    """
    fake_redis.set.side_effect = RedisError("down")
    acquired = await acquire_dedupe_lock("ai_lock:1:explain_kpi:xyz")
    assert acquired is True


async def test_release_dedupe_lock(fake_redis: MagicMock) -> None:
    await release_dedupe_lock("ai_lock:1:explain_kpi:xyz")
    fake_redis.delete.assert_awaited_once_with("ai_lock:1:explain_kpi:xyz")


# ============================================================
# wait_for_cache
# ============================================================


async def test_wait_for_cache_appears(fake_redis: MagicMock) -> None:
    """Cache появляется через короткое время → возвращаем значение."""
    call_count = {"n": 0}
    cached_value = {"summary": "from other worker"}

    async def faked_get(key: str):
        call_count["n"] += 1
        if call_count["n"] >= 3:
            return json.dumps(cached_value)
        return None

    fake_redis.get.side_effect = faked_get

    result = await wait_for_cache(
        "ai_cache:1:explain_kpi:xyz",
        max_wait_seconds=2.0,
    )
    assert result == cached_value
    assert call_count["n"] >= 3


async def test_wait_for_cache_timeout(fake_redis: MagicMock) -> None:
    """Cache не появился за max_wait → None (caller fallback'нется)."""
    fake_redis.get.return_value = None

    result = await wait_for_cache(
        "ai_cache:1:explain_kpi:xyz",
        max_wait_seconds=0.3,  # короткий для теста
    )
    assert result is None
