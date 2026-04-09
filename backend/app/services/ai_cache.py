"""Redis cache + dedupe слой для AI-вызовов (Phase 7.2, ADR-16).

## Зачем кэшировать

Identical AI-запрос (тот же project + та же фича + те же данные на входе)
возвращает один и тот же ответ от Polza с вероятностью ~100% при
`temperature=0.2`. Повторный клик «Explain KPI» через 5 минут без
изменений в проекте → нет смысла жечь ещё 3₽.

**Параметры кэша:**

- **TTL** — 24 часа. Достаточно чтобы покрыть рабочий день аналитика,
  но не настолько долго чтобы отдавать устаревший ответ когда
  пользователь реально что-то изменил вчера.
- **Key** — `ai_cache:{project_id}:{feature}:{input_hash}`.
  `input_hash` = SHA-256(sorted JSON dump of context dict). Стабильный
  — одинаковый context dict даёт одинаковый хеш.
- **Invalidation** — через TTL. В Phase 7.5 добавим explicit invalidation
  при `PATCH /api/projects/{id}` и recalculate (чтобы stale KPI не
  комментировались).

## Зачем dedupe

Двойной клик «Explain KPI», или параллельный запрос в двух табах, может
запустить 2 запроса к Polza одновременно — оба cache miss, оба платят.
Dedupe lock через Redis `SETNX` гарантирует что параллельный запрос
ждёт результат первого, а не дублирует работу.

**Алгоритм:**

1. Cache check → hit → возвращаем
2. Miss → acquire `ai_lock:{key}` через `SETNX EX 60`
3. Если получили lock → делаем запрос → пишем cache → release lock
4. Если НЕ получили (другой процесс в полёте) → polling кэша каждые
   100мс до `max_wait_seconds=30`. При появлении — возвращаем.
5. Timeout без cache → fallback на прямой вызов (lock может быть
   stale от зависшего процесса).

## Почему redis.asyncio, а не aioredis

`aioredis` deprecated с редиса 4.2. Современный способ — `redis.asyncio.Redis`
из стандартного `redis` пакета (≥4.2). Пакет уже транзитивно доступен
через `celery[redis]>=5.4.0` в requirements.txt, новая зависимость
не нужна.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from functools import lru_cache
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.services.ai_service import AIFeature

logger = logging.getLogger(__name__)

# ============================================================
# Constants
# ============================================================

CACHE_TTL_SECONDS = 24 * 60 * 60  # 24 часа
"""TTL для cache ответов AI. 24ч достаточно для рабочего дня аналитика."""

DEDUPE_LOCK_TTL_SECONDS = 60
"""TTL dedupe lock'а. Если за 60с первый запрос не закончился, lock
автоматически истекает (safety net против зависших процессов).
60с больше чем polza timeout (60с) — разумный баланс."""

DEDUPE_WAIT_MAX_SECONDS = 30
"""Максимум сколько ждём результат параллельного запроса при dedupe."""

DEDUPE_WAIT_POLL_INTERVAL = 0.1
"""Интервал polling'а cache при dedupe wait (100мс)."""


# ============================================================
# Redis client singleton
# ============================================================


@lru_cache(maxsize=1)
def _get_redis_client() -> Redis:
    """Singleton async Redis client для AI cache.

    Отдельный клиент, не переиспользуем celery_broker — Celery живёт
    на DB 1-2, AI cache — на DB 0 (`redis_url` из settings). Один
    клиент на процесс (connection pool внутри).
    """
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,  # автоматически декодирует bytes → str
        socket_timeout=5,
    )


def reset_redis_cache() -> None:
    """Сбросить singleton клиент. Для тестов."""
    _get_redis_client.cache_clear()


# ============================================================
# Cache key helpers
# ============================================================


def hash_context(context: dict[str, Any]) -> str:
    """SHA-256 от sorted JSON dump context'а.

    Стабильность: два одинаковых dict'а (с одинаковыми ключами в любом
    порядке) дают одинаковый хеш. Float значения Decimal'ов уже
    конвертированы в `AIContextBuilder` — JSON-safe.

    Returns:
        Hex string длиной 64 символа.
    """
    serialized = json.dumps(
        context, sort_keys=True, ensure_ascii=False, default=str
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def make_cache_key(
    project_id: int, feature: AIFeature, input_hash: str
) -> str:
    """`ai_cache:{project_id}:{feature}:{input_hash}`"""
    return f"ai_cache:{project_id}:{feature.value}:{input_hash}"


def make_lock_key(
    project_id: int, feature: AIFeature, input_hash: str
) -> str:
    """`ai_lock:{project_id}:{feature}:{input_hash}`"""
    return f"ai_lock:{project_id}:{feature.value}:{input_hash}"


# ============================================================
# Cache read/write
# ============================================================


async def get_cached(cache_key: str) -> dict[str, Any] | None:
    """Прочитать cached AI-ответ. None если miss или Redis error.

    Никогда не падает на Redis ошибках — AI-фичи должны работать даже
    при недоступности Redis (просто без кэша). Это graceful degradation
    по аналогии с `AIServiceUnavailableError` в ai_service.
    """
    client = _get_redis_client()
    try:
        raw = await client.get(cache_key)
    except RedisError as exc:
        logger.warning("Redis GET failed for %s: %s", cache_key, exc)
        return None

    if raw is None:
        return None

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("Cached value for %s is corrupt JSON: %s", cache_key, exc)
        return None


async def set_cached(
    cache_key: str, value: dict[str, Any], ttl: int = CACHE_TTL_SECONDS
) -> None:
    """Сохранить AI-ответ в cache с TTL."""
    client = _get_redis_client()
    try:
        await client.set(
            cache_key,
            json.dumps(value, ensure_ascii=False, default=str),
            ex=ttl,
        )
    except RedisError as exc:
        logger.warning("Redis SET failed for %s: %s", cache_key, exc)


# ============================================================
# Dedupe lock
# ============================================================


async def acquire_dedupe_lock(lock_key: str) -> bool:
    """Попытаться захватить dedupe lock.

    Returns:
        True если lock получен (этот вызов — master), False если
        другой процесс уже держит lock (этот вызов — follower, должен
        wait_for_cache).
    """
    client = _get_redis_client()
    try:
        # SETNX + EX атомарно через `nx=True, ex=...`
        acquired = await client.set(
            lock_key, "1", nx=True, ex=DEDUPE_LOCK_TTL_SECONDS
        )
    except RedisError as exc:
        logger.warning("Redis SETNX failed for %s: %s", lock_key, exc)
        # Fallback: при ошибке Redis считаем что мы master — пусть
        # вызовет Polza напрямую (хуже чем dedupe, но лучше чем стоп).
        return True

    return bool(acquired)


async def release_dedupe_lock(lock_key: str) -> None:
    """Освободить dedupe lock. Ошибки игнорируем (TTL подчистит)."""
    client = _get_redis_client()
    try:
        await client.delete(lock_key)
    except RedisError as exc:
        logger.warning("Redis DELETE failed for %s: %s", lock_key, exc)


async def wait_for_cache(
    cache_key: str,
    max_wait_seconds: float = DEDUPE_WAIT_MAX_SECONDS,
) -> dict[str, Any] | None:
    """Polling кэша пока не появится значение (от параллельного мастера)
    или не истечёт timeout.

    Returns:
        Cached dict если появился, None если timeout — caller должен
        fallback'нуться на прямой вызов (lock, видимо, stale).
    """
    elapsed = 0.0
    while elapsed < max_wait_seconds:
        cached = await get_cached(cache_key)
        if cached is not None:
            return cached
        await asyncio.sleep(DEDUPE_WAIT_POLL_INTERVAL)
        elapsed += DEDUPE_WAIT_POLL_INTERVAL

    return None
