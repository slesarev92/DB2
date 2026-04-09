"""Rate limit infrastructure для AI endpoint'ов (Phase 7.2).

## Архитектура

`slowapi` — FastAPI-совместимый wrapper над `limits` библиотекой.
Работает через декоратор `@limiter.limit("10/minute")` на endpoint'е +
middleware, который перехватывает `RateLimitExceeded` и возвращает
HTTP 429.

## Storage

По умолчанию in-memory (на каждый процесс). В проде с несколькими
uvicorn worker'ами нужен Redis storage, чтобы лимит был общим:

    Limiter(storage_uri=settings.redis_url)

Dev-режим — один worker, можно in-memory. Но сразу конфигурируем Redis
чтобы не удивляться при переходе на multi-worker.

## Ключи rate limit

Для AI: `{user_id}:{feature}` — отдельный лимит per фича, чтобы burst
«Explain KPI» не съедал лимит на «Executive summary». `user_id` берём
из `request.state.user_id`, который заполняется в endpoint'е после
`Depends(get_current_user)`.

## slowapi под async

`slowapi` поддерживает FastAPI async endpoint'ы через `SlowAPIMiddleware`.
Storage-слой (Redis) использует синхронный `redis-py` клиент — это OK,
т.к. slowapi вызывает его из middleware до/после endpoint'а, не внутри
horizon'а. Для AI daily budget check (который требует async SQL query к
ai_usage_log) используется отдельный helper в `ai_service`, не slowapi.

## Почему не fastapi-limiter

`fastapi-limiter` красивее (нативный async Redis), но требует lifespan
startup init + тянет `aioredis`/`redis[hiredis]` явно. slowapi — меньше
deps, стабильный API, проверен в проде у многих команд.
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

limiter = Limiter(
    key_func=get_remote_address,  # fallback — IP. Endpoint'ы override'ят.
    storage_uri=settings.redis_url,
    # Headers disabled: чтобы включить, endpoint должен принимать
    # `response: Response` параметр, что загромождает сигнатуру ради
    # cosmetic'а. 429 JSON через дефолтный exception handler достаточен.
    headers_enabled=False,
    # 429 вместо дефолтного. FastAPI сам отдаст это через exception_handler
    # зарегистрированный в main.py.
    default_limits=[],
)
"""Singleton Limiter. Регистрируется в `app.main` через
`app.state.limiter = limiter` + `app.add_exception_handler(...)`."""


def ai_rate_limit_key(user_id: int, feature_value: str) -> str:
    """Строит ключ rate limit для AI endpoint'ов.

    Пример: `ai_rl:42:explain_kpi` — user 42 ограничен 10/min на
    фичу explain_kpi независимо от других фич.
    """
    return f"ai_rl:{user_id}:{feature_value}"
