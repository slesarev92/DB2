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
from sqlalchemy.orm.attributes import flag_modified

from app.api.deps import get_current_user
from app.core.rate_limit import limiter
from app.db import get_db
from app.models import User
from app.schemas.ai import (
    AIBudgetUpdateRequest,
    AIChatRequest,
    AIContentFieldRequest,
    AIContentFieldResponse,
    AIExecutiveSummaryRequest,
    AIExecutiveSummaryResponse,
    AIExecutiveSummarySaveRequest,
    AIKpiExplanationRequest,
    AIKpiExplanationResponse,
    AIMarketingResearchEditRequest,
    AIMarketingResearchRequest,
    AIMarketingResearchResponse,
    AISensitivityExplanationRequest,
    AISensitivityExplanationResponse,
    AIUsageResponse,
    LLMContentFieldOutput,
    LLMExecutiveSummaryOutput,
    LLMKpiOutput,
    LLMMarketingResearchOutput,
    LLMSensitivityOutput,
)
from app.services import ai_cache, ai_service
from app.services.ai_context_builder import (
    AIContextBuilder,
    AIContextBuilderError,
)
from app.models import Project
from app.services.ai_prompts import (
    CHAT_SYSTEM_PROMPT,
    CONTENT_FIELD_PROMPTS,
    CONTENT_FIELD_SYSTEM,
    EXECUTIVE_SUMMARY_SYSTEM,
    KPI_EXPLAIN_SYSTEM,
    MARKETING_RESEARCH_SYSTEM,
    MARKETING_RESEARCH_TOPIC_PROMPTS,
    SENSITIVITY_EXPLAIN_SYSTEM,
)
from app.services.ai_service import (
    AIFeature,
    AIServiceUnavailableError,
    calculate_cost,
    resolve_model,
)
from app.services.ai_usage import (
    check_daily_user_budget,
    check_project_budget,
    get_project_usage_stats,
    log_ai_usage,
)

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
    # 0. Budget checks
    await check_daily_user_budget(session, user_id=current_user.id)
    await check_project_budget(session, project_id)

    # 1. Build context
    builder = AIContextBuilder(session)
    try:
        context = await builder.for_kpi_explanation(
            project_id=project_id,
            scenario_id=body.scenario_id,
            scope=body.scope,
        )
    except AIContextBuilderError as exc:
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
        await log_ai_usage(
            session,
            project_id=project_id,
            user_id=current_user.id,
            endpoint="explain_kpi_cache",
            model=cached.get("model", "unknown"),
            result=None,
        )
        return AIKpiExplanationResponse(
            **{k: v for k, v in cached.items() if k != "cached"},
            cached=True,
        )

    # 3. Dedupe lock
    lock_acquired = await ai_cache.acquire_dedupe_lock(lock_key)
    if not lock_acquired:
        cached = await ai_cache.wait_for_cache(cache_key)
        if cached is not None:
            await log_ai_usage(
                session,
                project_id=project_id,
                user_id=current_user.id,
                endpoint="explain_kpi_dedupe",
                model=cached.get("model", "unknown"),
                result=None,
            )
            return AIKpiExplanationResponse(
                **{k: v for k, v in cached.items() if k != "cached"},
                cached=True,
            )

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
        await log_ai_usage(
            session,
            project_id=project_id,
            user_id=current_user.id,
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
        user_id=current_user.id,
        endpoint="explain_kpi",
        result=result,
    )

    response_payload: dict = {
        **result.parsed.model_dump(),
        "cost_rub": cost_rub,
        "model": result.model,
    }
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
    await check_project_budget(session, project_id)

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
            user_id=current_user.id,
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
                user_id=current_user.id,
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
            user_id=current_user.id,
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
        user_id=current_user.id,
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
# EXECUTIVE SUMMARY (Phase 7.4)
# ============================================================

EXEC_SUMMARY_CACHE_TTL = 12 * 3600  # 12h — shorter than default 24h


@router.post(
    "/generate-executive-summary",
    response_model=AIExecutiveSummaryResponse,
    summary="Сгенерировать AI executive summary",
)
@limiter.limit("10/minute", key_func=_rate_limit_key)
async def generate_executive_summary(
    request: Request,
    project_id: int,
    body: AIExecutiveSummaryRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(_set_rate_limit_user)],
) -> AIExecutiveSummaryResponse:
    """Generate executive summary через opus (HEAVY tier).

    Более дорогой вызов (~10-15₽), поэтому UI показывает confirmation
    dialog перед отправкой. Cache TTL 12h (не 24h — executive часто
    переделывают).
    """
    await check_daily_user_budget(session, user_id=current_user.id)
    await check_project_budget(session, project_id)

    builder = AIContextBuilder(session)
    try:
        context = await builder.for_executive_summary(
            project_id=project_id,
        )
    except AIContextBuilderError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    input_hash = ai_cache.hash_context(context)
    cache_key = ai_cache.make_cache_key(
        project_id, AIFeature.EXECUTIVE_SUMMARY, input_hash
    )
    lock_key = ai_cache.make_lock_key(
        project_id, AIFeature.EXECUTIVE_SUMMARY, input_hash
    )

    cached = await ai_cache.get_cached(cache_key)
    if cached is not None:
        await log_ai_usage(
            session,
            project_id=project_id,
            user_id=current_user.id,
            endpoint="executive_summary_cache",
            model=cached.get("model", "unknown"),
            result=None,
        )
        return AIExecutiveSummaryResponse(
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
                user_id=current_user.id,
                endpoint="executive_summary_dedupe",
                model=cached.get("model", "unknown"),
                result=None,
            )
            return AIExecutiveSummaryResponse(
                **{k: v for k, v in cached.items() if k != "cached"},
                cached=True,
            )

    try:
        user_prompt = (
            "Составь Executive Summary для слайда паспорта проекта:\n\n"
            + json.dumps(context, ensure_ascii=False, indent=2)
        )
        result = await ai_service.complete_json(
            system_prompt=EXECUTIVE_SUMMARY_SYSTEM,
            user_prompt=user_prompt,
            schema=LLMExecutiveSummaryOutput,
            feature=AIFeature.EXECUTIVE_SUMMARY,
            tier_override=body.tier_override,
            endpoint="executive_summary",
        )
    except AIServiceUnavailableError as exc:
        await log_ai_usage(
            session,
            project_id=project_id,
            user_id=current_user.id,
            endpoint="executive_summary",
            error=str(exc),
        )
        await ai_cache.release_dedupe_lock(lock_key)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI executive summary недоступен: {exc}",
        ) from exc

    cost_rub = calculate_cost(
        result.model, result.prompt_tokens, result.completion_tokens
    )
    await log_ai_usage(
        session,
        project_id=project_id,
        user_id=current_user.id,
        endpoint="executive_summary",
        result=result,
    )

    response_payload: dict = {
        **result.parsed.model_dump(),
        "cost_rub": cost_rub,
        "model": result.model,
    }
    await ai_cache.set_cached(
        cache_key, _jsonable(response_payload), ttl=EXEC_SUMMARY_CACHE_TTL
    )
    await ai_cache.release_dedupe_lock(lock_key)

    return AIExecutiveSummaryResponse(**response_payload, cached=False)


@router.patch(
    "/executive-summary",
    summary="Сохранить отредактированный executive summary",
)
@limiter.limit("10/minute", key_func=_rate_limit_key)
async def save_executive_summary(
    request: Request,
    project_id: int,
    body: AIExecutiveSummarySaveRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(_set_rate_limit_user)],
) -> dict:
    """Save edited AI executive summary to Project.

    Аналитик генерирует draft через generate endpoint, редактирует в
    textarea, и сохраняет через этот PATCH. PPT/PDF экспорт читает
    из `Project.ai_executive_summary`.
    """
    from datetime import datetime, timezone

    project = await session.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} не найден",
        )

    project.ai_executive_summary = body.ai_executive_summary
    project.ai_commentary_updated_at = datetime.now(timezone.utc)
    project.ai_commentary_updated_by = current_user.id
    await session.flush()

    return {"status": "saved", "project_id": project_id}


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
    await check_project_budget(session, project_id)

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
                user_id=current_user.id,
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


# ============================================================
# CONTENT FIELD GENERATION (Phase 7.6)
# ============================================================


@router.post(
    "/generate-content",
    response_model=AIContentFieldResponse,
    summary="AI-генерация текстового поля паспорта",
)
@limiter.limit("10/minute", key_func=_rate_limit_key)
async def generate_content_field(
    request: Request,
    project_id: int,
    body: AIContentFieldRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(_set_rate_limit_user)],
) -> AIContentFieldResponse:
    """Генерация текста для одного content field паспорта.

    Default tier: FAST_CHEAP (haiku) — ~0.3-0.5₽ за вызов.
    Override tier_override=balanced для deeper reasoning (~1.5₽).
    """
    await check_daily_user_budget(session, user_id=current_user.id)
    await check_project_budget(session, project_id)

    # 1. Build context
    builder = AIContextBuilder(session)
    try:
        context = await builder.for_content_field(
            project_id=project_id,
            field_name=body.field,
            user_hint=body.user_hint,
        )
    except AIContextBuilderError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    # 2. Per-field task prompt
    field_task = CONTENT_FIELD_PROMPTS.get(body.field)
    if field_task is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Нет промпта для поля '{body.field}'",
        )

    # 3. Cache
    input_hash = ai_cache.hash_context(context)
    cache_key = ai_cache.make_cache_key(
        project_id, AIFeature.CONTENT_FIELD, input_hash
    )
    lock_key = ai_cache.make_lock_key(
        project_id, AIFeature.CONTENT_FIELD, input_hash
    )

    cached = await ai_cache.get_cached(cache_key)
    if cached is not None:
        await log_ai_usage(
            session,
            project_id=project_id,
            user_id=current_user.id,
            endpoint="content_field_cache",
            model=cached.get("model", "unknown"),
            result=None,
        )
        return AIContentFieldResponse(
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
                user_id=current_user.id,
                endpoint="content_field_dedupe",
                model=cached.get("model", "unknown"),
                result=None,
            )
            return AIContentFieldResponse(
                **{k: v for k, v in cached.items() if k != "cached"},
                cached=True,
            )

    # 4. Polza call
    try:
        user_prompt = (
            f"Сгенерируй текст для поля «{body.field}» паспорта проекта.\n\n"
            f"Задание: {field_task}\n\n"
            f"Контекст проекта:\n"
            + json.dumps(context, ensure_ascii=False, indent=2)
        )
        result = await ai_service.complete_json(
            system_prompt=CONTENT_FIELD_SYSTEM,
            user_prompt=user_prompt,
            schema=LLMContentFieldOutput,
            feature=AIFeature.CONTENT_FIELD,
            tier_override=body.tier_override,
            endpoint="content_field",
        )
    except AIServiceUnavailableError as exc:
        await log_ai_usage(
            session,
            project_id=project_id,
            user_id=current_user.id,
            endpoint="content_field",
            error=str(exc),
        )
        await ai_cache.release_dedupe_lock(lock_key)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI-генерация недоступна: {exc}",
        ) from exc

    # 5. Success
    cost_rub = calculate_cost(
        result.model, result.prompt_tokens, result.completion_tokens
    )
    await log_ai_usage(
        session,
        project_id=project_id,
        user_id=current_user.id,
        endpoint="content_field",
        result=result,
    )

    response_payload: dict = {
        "field": body.field,
        "generated_text": result.parsed.generated_text,
        "cost_rub": cost_rub,
        "model": result.model,
    }
    await ai_cache.set_cached(cache_key, _jsonable(response_payload))
    await ai_cache.release_dedupe_lock(lock_key)

    return AIContentFieldResponse(**response_payload, cached=False)


# ============================================================
# MARKETING RESEARCH (Phase 7.7)
# ============================================================


@router.post(
    "/marketing-research",
    response_model=AIMarketingResearchResponse,
    summary="AI marketing research",
)
@limiter.limit("5/minute", key_func=_rate_limit_key)
async def generate_marketing_research(
    request: Request,
    project_id: int,
    body: AIMarketingResearchRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(_set_rate_limit_user)],
) -> AIMarketingResearchResponse:
    """Generate marketing research для одного topic.

    RESEARCH tier (opus, ~10-20₽). NO Redis cache — research должен
    быть свежим. Результат сохраняется в Project.marketing_research JSONB.

    TODO: web_search integration после Polza API verification.
    """
    from datetime import datetime as dt, timezone as tz

    await check_daily_user_budget(session, user_id=current_user.id)
    await check_project_budget(session, project_id)

    if body.topic == "custom" and not body.custom_query:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="custom_query обязателен для topic=custom",
        )

    builder = AIContextBuilder(session)
    try:
        context = await builder.for_marketing_research(
            project_id=project_id,
            topic=body.topic,
            custom_query=body.custom_query,
        )
    except AIContextBuilderError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    topic_task = MARKETING_RESEARCH_TOPIC_PROMPTS.get(body.topic, "")

    try:
        user_prompt = (
            f"Тема исследования: {body.topic}\n"
            f"Задание: {topic_task}\n"
            + (f"Конкретный запрос: {body.custom_query}\n" if body.custom_query else "")
            + f"\nКонтекст проекта:\n"
            + json.dumps(context, ensure_ascii=False, indent=2)
        )
        result = await ai_service.complete_json(
            system_prompt=MARKETING_RESEARCH_SYSTEM,
            user_prompt=user_prompt,
            schema=LLMMarketingResearchOutput,
            feature=AIFeature.MARKETING_RESEARCH,
            endpoint="marketing_research",
            temperature=0.4,  # slightly higher for research creativity
        )
    except AIServiceUnavailableError as exc:
        await log_ai_usage(
            session,
            project_id=project_id,
            user_id=current_user.id,
            endpoint="marketing_research",
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI marketing research недоступен: {exc}",
        ) from exc

    cost_rub = calculate_cost(
        result.model, result.prompt_tokens, result.completion_tokens
    )
    await log_ai_usage(
        session,
        project_id=project_id,
        user_id=current_user.id,
        endpoint="marketing_research",
        result=result,
    )

    generated_at = dt.now(tz.utc).isoformat()

    # Save to Project.marketing_research JSONB
    project = await session.get(Project, project_id)
    if project is not None:
        research = dict(project.marketing_research or {})
        research[body.topic] = {
            "text": result.parsed.research_text,
            "sources": [s.model_dump() for s in result.parsed.sources],
            "key_findings": result.parsed.key_findings,
            "confidence_notes": result.parsed.confidence_notes,
            "generated_at": generated_at,
            "cost_rub": str(cost_rub),
            "model": result.model,
        }
        project.marketing_research = research
        flag_modified(project, "marketing_research")
        await session.flush()

    return AIMarketingResearchResponse(
        topic=body.topic,
        research_text=result.parsed.research_text,
        sources=result.parsed.sources,
        key_findings=result.parsed.key_findings,
        confidence_notes=result.parsed.confidence_notes,
        generated_at=generated_at,
        cost_rub=cost_rub,
        model=result.model,
        web_sources_used=False,
    )


@router.patch(
    "/marketing-research",
    summary="Редактировать marketing research text",
)
@limiter.limit("10/minute", key_func=_rate_limit_key)
async def edit_marketing_research(
    request: Request,
    project_id: int,
    body: AIMarketingResearchEditRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(_set_rate_limit_user)],
) -> dict:
    """Обновить research_text для конкретного topic."""
    project = await session.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} не найден",
        )

    research = dict(project.marketing_research or {})
    if body.topic not in research:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Research по теме '{body.topic}' не найден",
        )

    research[body.topic]["text"] = body.edited_text
    project.marketing_research = research
    flag_modified(project, "marketing_research")
    await session.flush()

    return {"status": "saved", "topic": body.topic}


@router.delete(
    "/marketing-research/{topic}",
    summary="Удалить marketing research topic",
)
@limiter.limit("10/minute", key_func=_rate_limit_key)
async def delete_marketing_research(
    request: Request,
    project_id: int,
    topic: str,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(_set_rate_limit_user)],
) -> dict:
    """Удалить конкретный topic из marketing_research JSONB."""
    project = await session.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} не найден",
        )

    research = dict(project.marketing_research or {})
    if topic not in research:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Research по теме '{topic}' не найден",
        )

    del research[topic]
    project.marketing_research = research or None
    flag_modified(project, "marketing_research")
    await session.flush()

    return {"status": "deleted", "topic": topic}


# ============================================================
# USAGE + BUDGET (Phase 7.5)
# ============================================================


@router.get(
    "/usage",
    response_model=AIUsageResponse,
    summary="AI usage statistics для проекта",
)
async def get_ai_usage(
    project_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AIUsageResponse:
    """Агрегированная статистика AI-расходов проекта.

    Без rate limit — read-only endpoint, не дёргает Polza.
    """
    stats = await get_project_usage_stats(session, project_id)
    return AIUsageResponse(**stats)


@router.patch(
    "/budget",
    response_model=AIUsageResponse,
    summary="Обновить AI-бюджет проекта",
)
@limiter.limit("10/minute", key_func=_rate_limit_key)
async def update_ai_budget(
    request: Request,
    project_id: int,
    body: AIBudgetUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(_set_rate_limit_user)],
) -> AIUsageResponse:
    """Обновить месячный AI-бюджет проекта. null = unlimited."""
    project = await session.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} не найден",
        )

    project.ai_budget_rub_monthly = body.ai_budget_rub_monthly
    await session.flush()

    stats = await get_project_usage_stats(session, project_id)
    return AIUsageResponse(**stats)
