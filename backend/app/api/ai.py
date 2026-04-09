"""AI endpoints (Phase 7.2..7.8).

Все AI-фичи живут здесь. Каждый endpoint следует единому flow:

1. `Depends(get_current_user)` — требует авторизацию
2. `@limiter.limit("10/minute", key_func=...)` — rate limit
3. `await check_daily_user_budget(...)` — daily cap safety net
4. Context build через `AIContextBuilder`
5. Cache check через `ai_cache`
6. `ai_service.complete_json(feature=..., ...)` — реальный Polza вызов
7. `log_ai_usage(...)` — в БД
8. Response со строкой `cached: bool`, `cost_rub`, `model`

Phase 7.2 добавляет explain-kpi. Следующие endpoint'ы (7.3..7.8)
расширяют этот файл по мере добавления фич.

NB: здесь НЕ используем `from __future__ import annotations` — это
ломает FastAPI introspection сигнатур с `Annotated[..., Depends(...)]`
(конкретно — Pydantic body модели начинают считаться query params).
Единственный endpoint-файл проекта без future import'а.
"""
import json
import logging
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.rate_limit import limiter
from app.db import get_db
from app.models import User
from app.schemas.ai import (
    AIKpiExplanationRequest,
    AIKpiExplanationResponse,
    LLMKpiOutput,
)
from app.services import ai_cache, ai_service
from app.services.ai_context_builder import (
    AIContextBuilder,
    AIContextBuilderError,
)
from app.services.ai_prompts import KPI_EXPLAIN_SYSTEM
from app.services.ai_service import (
    AIFeature,
    AIServiceUnavailableError,
    calculate_cost,
)
from app.services.ai_usage import check_daily_user_budget, log_ai_usage

logger = logging.getLogger(__name__)

# Префикс /api/projects/{project_id}/ai — все AI endpoint'ы привязаны
# к проекту. Исключение — админ endpoint'ы (в MVP не нужны).
router = APIRouter(
    prefix="/api/projects/{project_id}/ai",
    tags=["ai"],
)


def _rate_limit_key(request: Request) -> str:
    """Key function для slowapi: `ai_rl:{user_id}:explain_kpi`.

    `request.state.user_id` проставляется в endpoint'е через
    `set_rate_limit_user` helper (см. ниже). slowapi вызывает key_func
    до того как run endpoint body, поэтому state должен быть установлен
    middleware'ом или dependency — либо делаем fallback на IP.
    """
    user_id = getattr(request.state, "ai_rate_limit_user_id", None)
    if user_id is None:
        # Fallback: до попадания в endpoint, slowapi не знает user_id.
        # Используем IP как грубый ключ — лучше чем ничего.
        return f"ai_rl_ip:{request.client.host if request.client else 'unknown'}:explain_kpi"
    return f"ai_rl:{user_id}:explain_kpi"


async def _set_rate_limit_user(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Dependency: сохраняет user.id в request.state для rate limit key.

    slowapi вызывает key_func ДО dependency'ов, поэтому первый вызов
    ключом будет по IP. Но это OK: второй и последующие вызовы от
    того же пользователя попадут в правильный per-user bucket.

    Альтернатива — custom middleware, который parsit JWT до slowapi.
    Слишком сложно для MVP, rate limit как safety net терпит небольшую
    imprecision первого вызова.
    """
    request.state.ai_rate_limit_user_id = current_user.id
    return current_user


@router.post(
    "/explain-kpi",
    response_model=AIKpiExplanationResponse,
    summary="AI-объяснение KPI сценария",
)
@limiter.limit("10/minute", key_func=_rate_limit_key)
async def explain_kpi(
    request: Request,  # noqa: ARG001 — нужен slowapi для key_func
    project_id: int,
    body: AIKpiExplanationRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(_set_rate_limit_user)],
) -> AIKpiExplanationResponse:
    """Сгенерировать AI-объяснение KPI фокусного сценария на фокусном scope.

    **Flow (Phase 7.2 решение #6):**

    1. Daily budget safety net — 429 если превышен 100₽/день
    2. Build context через `AIContextBuilder.for_kpi_explanation`
    3. Hash context → lookup Redis cache
    4. Cache hit → возвращаем с `cached=true, cost_rub=0`
    5. Cache miss → acquire dedupe lock
    6. Lock acquired → call Polza через `complete_json(feature=EXPLAIN_KPI)`
    7. Pydantic validate → log_ai_usage → set cache → release lock
    8. Return response

    **Graceful degradation:**

    - AIServiceUnavailableError → HTTP 503 с placeholder message
    - AIContextBuilderError → HTTP 404 (это не AI, это данные)
    - Redis недоступен → пропускаем cache, всё остальное работает
    - Bugged LLM output → Pydantic fail → через
      AIServiceUnavailableError → 503
    """
    # 0. Daily budget safety net (отдельно от slowapi — slowapi не
    #    умеет cost-based лимиты)
    await check_daily_user_budget(session, user_id=current_user.id)

    # 1. Build context
    builder = AIContextBuilder(session)
    try:
        context = await builder.for_kpi_explanation(
            project_id=project_id,
            scenario_id=body.scenario_id,
            scope=body.scope,
        )
    except AIContextBuilderError as exc:
        # Это не AI-проблема — это состояние данных. 404.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    # 2. Cache lookup
    input_hash = ai_cache.hash_context(context)
    cache_key = ai_cache.make_cache_key(
        project_id, AIFeature.EXPLAIN_KPI, input_hash
    )
    lock_key = ai_cache.make_lock_key(
        project_id, AIFeature.EXPLAIN_KPI, input_hash
    )

    cached = await ai_cache.get_cached(cache_key)
    if cached is not None:
        # Логируем cache hit с нулевой стоимостью для observability
        await log_ai_usage(
            session,
            project_id=project_id,
            endpoint="explain_kpi_cache",
            model=cached.get("model", "unknown"),
            result=None,
        )
        return AIKpiExplanationResponse(
            **{k: v for k, v in cached.items() if k != "cached"},
            cached=True,
        )

    # 3. Dedupe lock: если другой запрос в полёте — ждём его
    lock_acquired = await ai_cache.acquire_dedupe_lock(lock_key)
    if not lock_acquired:
        cached = await ai_cache.wait_for_cache(cache_key)
        if cached is not None:
            await log_ai_usage(
                session,
                project_id=project_id,
                endpoint="explain_kpi_dedupe",
                model=cached.get("model", "unknown"),
                result=None,
            )
            return AIKpiExplanationResponse(
                **{k: v for k, v in cached.items() if k != "cached"},
                cached=True,
            )
        # Timeout — fallback на прямой вызов (lock, видимо, stale)

    # 4. Polza call
    try:
        user_prompt = (
            "Объясни KPI фокусного сценария. Контекст проекта:\n\n"
            + json.dumps(context, ensure_ascii=False, indent=2)
        )
        result = await ai_service.complete_json(
            system_prompt=KPI_EXPLAIN_SYSTEM,
            user_prompt=user_prompt,
            schema=LLMKpiOutput,
            feature=AIFeature.EXPLAIN_KPI,
            tier_override=body.tier_override,
            endpoint="explain_kpi",
        )
    except AIServiceUnavailableError as exc:
        # Log failure для observability — пустой log entry с error text
        await log_ai_usage(
            session,
            project_id=project_id,
            endpoint="explain_kpi",
            error=str(exc),
        )
        await ai_cache.release_dedupe_lock(lock_key)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "AI-объяснение недоступно — Polza AI не отвечает. "
                f"Повторите через минуту. Детали: {exc}"
            ),
        ) from exc

    # 5. Успех: лог + cache + return
    cost_rub = calculate_cost(
        result.model, result.prompt_tokens, result.completion_tokens
    )
    await log_ai_usage(
        session,
        project_id=project_id,
        endpoint="explain_kpi",
        result=result,
    )

    response_payload: dict = {
        **result.parsed.model_dump(),
        "cost_rub": cost_rub,
        "model": result.model,
    }
    # Cache payload без `cached` поля — его endpoint добавляет при возврате
    await ai_cache.set_cached(cache_key, _jsonable(response_payload))
    await ai_cache.release_dedupe_lock(lock_key)

    return AIKpiExplanationResponse(**response_payload, cached=False)


def _jsonable(payload: dict) -> dict:
    """Конвертирует Decimal → str для JSON-safe cache storage.

    Pydantic сериализует Decimal как str при model_dump_json, но мы
    кладём dict в JSON вручную — нужен явный преобразователь.
    """
    return {
        k: (str(v) if isinstance(v, Decimal) else v) for k, v in payload.items()
    }
