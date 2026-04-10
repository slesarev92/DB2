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
import uuid
from decimal import Decimal
from typing import Annotated, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.rate_limit import limiter
from app.db import get_db
from app.models import User
from app.schemas.ai import (
    AIChatRequest,
    AIKpiExplanationRequest,
    AIKpiExplanationResponse,
    AISensitivityExplanationRequest,
    AISensitivityExplanationResponse,
    LLMKpiOutput,
    LLMSensitivityOutput,
)
from app.services import ai_cache, ai_service
from app.services.ai_context_builder import (
    AIContextBuilder,
    AIContextBuilderError,
)
from app.services.ai_prompts import (
    CHAT_SYSTEM_PROMPT,
    KPI_EXPLAIN_SYSTEM,
    SENSITIVITY_EXPLAIN_SYSTEM,
)
from app.services.ai_service import (
    AIFeature,
    AIServiceUnavailableError,
    calculate_cost,
    resolve_model,
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
    """Конвертирует Decimal → str для JSON-safe cache storage."""
    return {
        k: (str(v) if isinstance(v, Decimal) else v) for k, v in payload.items()
    }


# ============================================================
# EXPLAIN SENSITIVITY (Phase 7.3)
# ============================================================


@router.post(
    "/explain-sensitivity",
    response_model=AISensitivityExplanationResponse,
    summary="AI-интерпретация чувствительности",
)
@limiter.limit("10/minute", key_func=_rate_limit_key)
async def explain_sensitivity(
    request: Request,
    project_id: int,
    body: AISensitivityExplanationRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(_set_rate_limit_user)],
) -> AISensitivityExplanationResponse:
    """Sensitivity analysis interpretation: какой параметр critical и почему."""
    await check_daily_user_budget(session, user_id=current_user.id)

    builder = AIContextBuilder(session)
    try:
        context = await builder.for_sensitivity_interpretation(
            project_id=project_id,
            scenario_id=body.scenario_id,
        )
    except AIContextBuilderError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    input_hash = ai_cache.hash_context(context)
    cache_key = ai_cache.make_cache_key(
        project_id, AIFeature.EXPLAIN_SENSITIVITY, input_hash
    )
    lock_key = ai_cache.make_lock_key(
        project_id, AIFeature.EXPLAIN_SENSITIVITY, input_hash
    )

    cached = await ai_cache.get_cached(cache_key)
    if cached is not None:
        await log_ai_usage(
            session,
            project_id=project_id,
            endpoint="explain_sensitivity_cache",
            model=cached.get("model", "unknown"),
            result=None,
        )
        return AISensitivityExplanationResponse(
            **{k: v for k, v in cached.items() if k != "cached"},
            cached=True,
        )

    lock_acquired = await ai_cache.acquire_dedupe_lock(lock_key)
    if not lock_acquired:
        cached = await ai_cache.wait_for_cache(cache_key)
        if cached is not None:
            await log_ai_usage(
                session,
                project_id=project_id,
                endpoint="explain_sensitivity_dedupe",
                model=cached.get("model", "unknown"),
                result=None,
            )
            return AISensitivityExplanationResponse(
                **{k: v for k, v in cached.items() if k != "cached"},
                cached=True,
            )

    try:
        user_prompt = (
            "Интерпретируй матрицу чувствительности проекта:\n\n"
            + json.dumps(context, ensure_ascii=False, indent=2)
        )
        result = await ai_service.complete_json(
            system_prompt=SENSITIVITY_EXPLAIN_SYSTEM,
            user_prompt=user_prompt,
            schema=LLMSensitivityOutput,
            feature=AIFeature.EXPLAIN_SENSITIVITY,
            tier_override=body.tier_override,
            endpoint="explain_sensitivity",
        )
    except AIServiceUnavailableError as exc:
        await log_ai_usage(
            session,
            project_id=project_id,
            endpoint="explain_sensitivity",
            error=str(exc),
        )
        await ai_cache.release_dedupe_lock(lock_key)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI-интерпретация недоступна: {exc}",
        ) from exc

    cost_rub = calculate_cost(
        result.model, result.prompt_tokens, result.completion_tokens
    )
    await log_ai_usage(
        session,
        project_id=project_id,
        endpoint="explain_sensitivity",
        result=result,
    )

    response_payload: dict = {
        **result.parsed.model_dump(),
        "cost_rub": cost_rub,
        "model": result.model,
    }
    await ai_cache.set_cached(cache_key, _jsonable(response_payload))
    await ai_cache.release_dedupe_lock(lock_key)

    return AISensitivityExplanationResponse(**response_payload, cached=False)


# ============================================================
# FREEFORM CHAT (Phase 7.3) — SSE streaming
# ============================================================

CHAT_HISTORY_TTL = 3600  # 1 hour


@router.post(
    "/chat",
    summary="Freeform AI chat — SSE streaming",
    response_class=StreamingResponse,
)
@limiter.limit("10/minute", key_func=_rate_limit_key)
async def freeform_chat(
    request: Request,
    project_id: int,
    body: AIChatRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(_set_rate_limit_user)],
) -> StreamingResponse:
    """SSE streaming chat — единственный endpoint с plain text response.

    Conversation history хранится в Redis (TTL 1h). При первом вызове
    с conversation_id=null генерируется UUID, возвращается в SSE event
    `conversation_id`. Последующие вызовы с тем же ID продолжают
    разговор.
    """
    await check_daily_user_budget(session, user_id=current_user.id)

    # Context builder
    builder = AIContextBuilder(session)
    try:
        context = await builder.for_freeform_chat(
            project_id=project_id,
            user_question=body.question,
        )
    except AIContextBuilderError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    # Conversation history from Redis
    conv_id = body.conversation_id or str(uuid.uuid4())
    redis_key = f"ai_chat:{project_id}:{conv_id}"
    redis = ai_cache._get_redis_client()

    history_messages: list[dict[str, str]] = []
    try:
        raw_history = await redis.get(redis_key)
        if raw_history:
            history_messages = json.loads(raw_history)
    except Exception:
        pass  # Redis unavailable → start fresh

    # Build messages array
    context_text = json.dumps(context, ensure_ascii=False, indent=2)
    messages: list[dict[str, str]] = [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Контекст проекта:\n\n{context_text}",
        },
    ]
    messages.extend(history_messages)
    messages.append({"role": "user", "content": body.question})

    # Resolve model
    model = resolve_model(
        AIFeature.FREEFORM_CHAT, body.tier_override
    )

    async def sse_generator() -> AsyncIterator[str]:
        """SSE stream: yields `data: ...` events."""
        # First event: conversation_id
        yield f"data: {json.dumps({'type': 'conversation_id', 'id': conv_id})}\n\n"

        full_response = ""
        prompt_tokens = 0
        completion_tokens = 0
        try:
            client = ai_service._get_client()
            stream = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.2,
                max_tokens=2000,
                stream=True,
            )
            async for chunk in stream:
                if chunk.usage:
                    prompt_tokens = chunk.usage.prompt_tokens or 0
                    completion_tokens = chunk.usage.completion_tokens or 0
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    full_response += delta.content
                    yield f"data: {json.dumps({'type': 'token', 'content': delta.content})}\n\n"

        except AIServiceUnavailableError as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
            return
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': f'Ошибка: {exc}'})}\n\n"
            return

        # Save conversation to Redis
        new_history = history_messages + [
            {"role": "user", "content": body.question},
            {"role": "assistant", "content": full_response},
        ]
        # Keep last 20 messages (10 turns) to avoid unbounded growth
        new_history = new_history[-20:]
        try:
            await redis.set(
                redis_key,
                json.dumps(new_history, ensure_ascii=False),
                ex=CHAT_HISTORY_TTL,
            )
        except Exception:
            pass  # Redis unavailable → history lost, not fatal

        # Cost + usage log (best effort — session may be closed by now
        # in some edge cases with SSE, but normally still alive)
        cost = calculate_cost(model, prompt_tokens, completion_tokens)
        try:
            await log_ai_usage(
                session,
                project_id=project_id,
                endpoint="freeform_chat",
                result=ai_service.AICallResult(
                    parsed=None,  # type: ignore[arg-type]
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens,
                    latency_ms=0,
                ),
            )
        except Exception:
            pass  # Best effort logging

        # Final event with metadata
        yield f"data: {json.dumps({'type': 'done', 'cost_rub': str(cost), 'model': model})}\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
