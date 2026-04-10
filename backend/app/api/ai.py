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
from sqlalchemy import select
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified
from datetime import datetime, timezone

from app.api.deps import get_current_user
from app.core.rate_limit import limiter
from app.db import get_db
from app.models import (
    AIGeneratedImage,
    ChatConversation,
    ChatMessage,
    MediaAsset,
    ProjectSKU,
    User,
)
from app.schemas.ai import (
    AIBudgetUpdateRequest,
    AIChatRequest,
    AIContentFieldRequest,
    AIContentFieldResponse,
    AIExecutiveSummaryRequest,
    AIExecutiveSummaryResponse,
    AIExecutiveSummarySaveRequest,
    AIGeneratedImageRead,
    ChatConversationDetail,
    ChatConversationRead,
    ChatMessageRead,
    AIKpiExplanationRequest,
    AIKpiExplanationResponse,
    AIMarketingResearchEditRequest,
    AIMarketingResearchRequest,
    AIMarketingResearchResponse,
    AIPackageMockupRequest,
    AIPackageMockupResponse,
    AISensitivityExplanationRequest,
    AISensitivityExplanationResponse,
    AIUsageResponse,
    LLMContentFieldOutput,
    LLMExecutiveSummaryOutput,
    LLMKpiOutput,
    LLMMarketingResearchOutput,
    LLMSensitivityOutput,
    LLMVisionArtDirectionOutput,
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
    PACKAGE_ITERATION_BLOCK,
    PACKAGE_ITERATION_ENTRY,
    PACKAGE_VISION_SYSTEM,
    PACKAGE_VISION_WITH_PROMPT,
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
        # Persist to DB if not yet saved (backfill from Redis)
        await _persist_kpi_commentary(
            session, project_id, body.scenario_id, body.scope, cached
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

    await _persist_kpi_commentary(
        session, project_id, body.scenario_id, body.scope, response_payload
    )

    return AIKpiExplanationResponse(**response_payload, cached=False)


async def _persist_kpi_commentary(
    session: AsyncSession,
    project_id: int,
    scenario_id: int,
    scope: str,
    payload: dict,
) -> None:
    """Save KPI commentary to Project.ai_kpi_commentary JSONB."""
    from sqlalchemy.orm.attributes import flag_modified

    project = await session.get(Project, project_id)
    if project is None:
        return
    cache = project.ai_kpi_commentary or {}
    cache[f"{scenario_id}_{scope}"] = _jsonable(payload)
    project.ai_kpi_commentary = cache
    flag_modified(project, "ai_kpi_commentary")
    await session.flush()
    await session.commit()


async def _persist_sensitivity_commentary(
    session: AsyncSession,
    project_id: int,
    scenario_id: int,
    payload: dict,
) -> None:
    """Save sensitivity commentary to Project.ai_sensitivity_commentary JSONB."""
    from sqlalchemy.orm.attributes import flag_modified

    project = await session.get(Project, project_id)
    if project is None:
        return
    cache = project.ai_sensitivity_commentary or {}
    cache[str(scenario_id)] = _jsonable(payload)
    project.ai_sensitivity_commentary = cache
    flag_modified(project, "ai_sensitivity_commentary")
    await session.flush()
    await session.commit()


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
        await _persist_sensitivity_commentary(
            session, project_id, body.scenario_id, cached
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

    await _persist_sensitivity_commentary(
        session, project_id, body.scenario_id, response_payload
    )

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
    await session.commit()

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

    # Conversation: load existing or create new
    conversation: ChatConversation | None = None
    if body.conversation_id:
        try:
            conv_id_int = int(body.conversation_id)
            conversation = await session.get(ChatConversation, conv_id_int)
            if conversation and conversation.deleted_at is not None:
                conversation = None
        except (ValueError, TypeError):
            pass

    if conversation is None:
        title = body.question[:80].strip() or "Новый разговор"
        conversation = ChatConversation(
            project_id=project_id,
            user_id=current_user.id,
            title=title,
        )
        session.add(conversation)
        await session.flush()

    conv_id = conversation.id

    # Save user message to DB
    user_msg = ChatMessage(
        conversation_id=conv_id,
        role="user",
        content=body.question,
    )
    session.add(user_msg)
    await session.flush()

    # Load conversation history from DB (last 20 messages for LLM context)
    history_stmt = (
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conv_id)
        .order_by(ChatMessage.created_at)
    )
    all_db_messages = (await session.scalars(history_stmt)).all()
    # Use last 20 messages (excluding the one we just added — it'll be appended)
    history_messages = [
        {"role": m.role, "content": m.content}
        for m in all_db_messages[:-1]  # exclude last (just-added user msg)
    ][-20:]

    # Also update Redis for backward compat
    redis_key = f"ai_chat:{project_id}:{conv_id}"
    redis = ai_cache._get_redis_client()

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
        # First event: conversation_id (now DB int id as string)
        yield f"data: {json.dumps({'type': 'conversation_id', 'id': str(conv_id)})}\n\n"

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

        # Save assistant message to DB
        cost = calculate_cost(model, prompt_tokens, completion_tokens)
        try:
            assistant_msg = ChatMessage(
                conversation_id=conv_id,
                role="assistant",
                content=full_response,
                model=model,
                cost_rub=cost,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
            session.add(assistant_msg)
            conversation.updated_at = datetime.now(timezone.utc)
            await session.flush()
        except Exception:
            pass  # Best effort

        # Save conversation to Redis (for LLM context window perf)
        new_history = history_messages + [
            {"role": "user", "content": body.question},
            {"role": "assistant", "content": full_response},
        ]
        new_history = new_history[-20:]
        try:
            await redis.set(
                redis_key,
                json.dumps(new_history, ensure_ascii=False),
                ex=CHAT_HISTORY_TTL,
            )
        except Exception:
            pass

        # Usage log
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
            pass

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
# CHAT CONVERSATIONS — list / load / delete
# ============================================================


@router.get(
    "/conversations",
    response_model=list[ChatConversationRead],
    summary="List chat conversations for project",
)
async def list_conversations(
    project_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[ChatConversationRead]:
    """Все незакрытые разговоры текущего юзера в проекте, новые первыми."""
    stmt = (
        select(ChatConversation)
        .where(
            ChatConversation.project_id == project_id,
            ChatConversation.user_id == current_user.id,
            ChatConversation.deleted_at.is_(None),
        )
        .order_by(ChatConversation.updated_at.desc())
        .limit(50)
    )
    rows = (await session.scalars(stmt)).all()
    return [
        ChatConversationRead(
            id=c.id,
            title=c.title,
            created_at=c.created_at.isoformat(),
            updated_at=c.updated_at.isoformat(),
        )
        for c in rows
    ]


@router.get(
    "/conversations/{conversation_id}",
    response_model=ChatConversationDetail,
    summary="Load conversation with all messages",
)
async def get_conversation(
    project_id: int,
    conversation_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ChatConversationDetail:
    """Загрузить разговор со всеми сообщениями."""
    stmt = (
        select(ChatConversation)
        .where(
            ChatConversation.id == conversation_id,
            ChatConversation.project_id == project_id,
            ChatConversation.user_id == current_user.id,
            ChatConversation.deleted_at.is_(None),
        )
        .options(selectinload(ChatConversation.messages))
    )
    conv = (await session.scalars(stmt)).first()
    if conv is None:
        raise HTTPException(status_code=404, detail="Разговор не найден")
    return ChatConversationDetail(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at.isoformat(),
        updated_at=conv.updated_at.isoformat(),
        messages=[
            ChatMessageRead(
                id=m.id,
                role=m.role,
                content=m.content,
                model=m.model,
                cost_rub=m.cost_rub,
                created_at=m.created_at.isoformat(),
            )
            for m in conv.messages
        ],
    )


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete conversation",
)
async def delete_conversation(
    project_id: int,
    conversation_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Soft delete: проставляет deleted_at."""
    stmt = select(ChatConversation).where(
        ChatConversation.id == conversation_id,
        ChatConversation.project_id == project_id,
        ChatConversation.user_id == current_user.id,
        ChatConversation.deleted_at.is_(None),
    )
    conv = (await session.scalars(stmt)).first()
    if conv is None:
        raise HTTPException(status_code=404, detail="Разговор не найден")
    conv.deleted_at = datetime.now(timezone.utc)
    await session.commit()


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
        await session.commit()

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
    await session.commit()

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
    await session.commit()

    return {"status": "deleted", "topic": topic}


# ============================================================
# PACKAGE MOCKUP (Phase 7.8)
# ============================================================


@router.post(
    "/generate-mockup",
    response_model=AIPackageMockupResponse,
    summary="AI-генерация mockup'а упаковки (two-step: vision → flux)",
)
@limiter.limit("5/minute", key_func=_rate_limit_key)
async def generate_package_mockup(
    request: Request,
    project_id: int,
    body: AIPackageMockupRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(_set_rate_limit_user)],
) -> AIPackageMockupResponse:
    """Two-step pipeline: Claude vision анализирует reference → flux генерит mockup.

    Step 1 (~3₽ sonnet / ~15₽ opus): Claude vision reads reference image → art direction
    Step 2 (~8₽): flux-2-pro generates image from art direction
    Total: ~13₽ per generation.
    """
    import base64
    import io

    from app.services.media_service import (
        read_media_file,
        save_uploaded_file,
    )

    await check_daily_user_budget(session, user_id=current_user.id)
    await check_project_budget(session, project_id)

    # Validate project_sku exists and belongs to project
    from sqlalchemy.orm import selectinload as _sil

    psku_stmt = (
        select(ProjectSKU)
        .where(ProjectSKU.id == body.project_sku_id)
        .options(_sil(ProjectSKU.sku))
    )
    psku = (await session.scalars(psku_stmt)).first()
    if psku is None or psku.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ProjectSKU {body.project_sku_id} не найден в project {project_id}",
        )

    sku = psku.sku

    # Load project for context enrichment
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} не найден",
        )

    # Load last 3 iterations for this SKU (oldest first for chronological context)
    history_stmt = (
        select(AIGeneratedImage)
        .where(AIGeneratedImage.project_sku_id == body.project_sku_id)
        .order_by(AIGeneratedImage.created_at.desc())
        .limit(3)
    )
    prev_rows = list((await session.scalars(history_stmt)).all())
    prev_rows.reverse()  # oldest first

    iteration_history = ""
    if prev_rows:
        entries = "\n".join(
            PACKAGE_ITERATION_ENTRY.format(
                n=i + 1,
                prompt=row.prompt_text[:300],
                art_direction=row.art_direction[:500],
            )
            for i, row in enumerate(prev_rows)
        )
        iteration_history = PACKAGE_ITERATION_BLOCK.format(entries=entries)

    art_direction = ""
    vision_cost = Decimal("0")

    # Step 1: Vision — analyze reference image
    if body.reference_asset_id is not None:
        ref_asset = await session.get(MediaAsset, body.reference_asset_id)
        if ref_asset is None or ref_asset.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reference asset {body.reference_asset_id} не найден",
            )

        try:
            image_bytes = read_media_file(ref_asset)
            image_b64 = base64.b64encode(image_bytes).decode("ascii")
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Не удалось прочитать reference image: {exc}",
            ) from exc

        user_prompt = PACKAGE_VISION_WITH_PROMPT.format(
            user_prompt=body.prompt,
            target_audience=project.target_audience or "не указана",
            concept_text=project.concept_text or "не указана",
            geography=project.geography or "не указана",
            innovation_type=project.innovation_type or "не указан",
            idea_short=project.idea_short or "не указана",
            production_type=project.production_type or "не указан",
            project_goal=project.project_goal or "не указана",
            brand=sku.brand,
            sku_name=sku.name,
            format=sku.format or "не указан",
            volume=f"{sku.volume_l}L" if sku.volume_l else "не указан",
            segment=sku.segment or "не указан",
            iteration_history=iteration_history,
        )

        try:
            vision_result = await ai_service.complete_vision(
                system_prompt=PACKAGE_VISION_SYSTEM,
                user_prompt=user_prompt,
                image_base64=image_b64,
                image_media_type=ref_asset.content_type,
                schema=LLMVisionArtDirectionOutput,
                feature=AIFeature.PACKAGE_MOCKUP,
                tier_override=body.tier_override or ai_service.AIModelTier.BALANCED,
                endpoint="mockup_vision",
            )
            art_direction = vision_result.parsed.art_direction
            vision_cost = calculate_cost(
                vision_result.model,
                vision_result.prompt_tokens,
                vision_result.completion_tokens,
            )
            await log_ai_usage(
                session,
                project_id=project_id,
                user_id=current_user.id,
                endpoint="mockup_vision",
                result=vision_result,
            )
        except AIServiceUnavailableError as exc:
            await log_ai_usage(
                session,
                project_id=project_id,
                user_id=current_user.id,
                endpoint="mockup_vision",
                error=str(exc),
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"AI vision недоступен: {exc}",
            ) from exc
    else:
        # No reference — use prompt directly as art direction
        ctx_parts = [
            f"Product packaging mockup for FMCG brand '{sku.brand}', "
            f"product '{sku.name}', segment '{sku.segment or 'mainstream'}', "
            f"format '{sku.format or 'bottle'}', volume {sku.volume_l or '0.5'}L.",
        ]
        if project.target_audience:
            ctx_parts.append(f"Target audience: {project.target_audience}.")
        if project.concept_text:
            ctx_parts.append(f"Product concept: {project.concept_text}.")
        if project.geography:
            ctx_parts.append(f"Market/geography: {project.geography}.")
        if project.innovation_type:
            ctx_parts.append(f"Innovation type: {project.innovation_type}.")
        if project.idea_short:
            ctx_parts.append(f"Idea: {project.idea_short}.")
        ctx_parts.append(f"User request: {body.prompt}")
        if prev_rows:
            last = prev_rows[-1]
            ctx_parts.append(
                f"PREVIOUS ART DIRECTION (keep style, apply user changes): "
                f"{last.art_direction[:500]}"
            )
        art_direction = " ".join(ctx_parts)

    # Step 2: Generate image via flux
    flux_prompt = (
        f"{art_direction}\n\n"
        f"Professional product packaging photo, studio lighting, "
        f"white background, high resolution, commercial photography style."
    )

    try:
        img_result = await ai_service.generate_image(prompt=flux_prompt)
    except AIServiceUnavailableError as exc:
        await log_ai_usage(
            session,
            project_id=project_id,
            user_id=current_user.id,
            endpoint="mockup_generate",
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI image generation недоступен: {exc}",
        ) from exc

    # Save generated image to MediaAsset
    image_data = base64.b64decode(img_result["b64_json"])
    asset = await save_uploaded_file(
        session,
        project_id=project_id,
        kind="ai_generated",
        filename=f"mockup_{sku.brand}_{sku.name}.png".replace(" ", "_"),
        content_type="image/png",
        fileobj=io.BytesIO(image_data),
        uploaded_by=current_user.id,
    )

    # Estimate flux cost (no per-token pricing — use flat estimate)
    flux_cost = Decimal("8")  # ~8₽ per flux generation
    total_cost = vision_cost + flux_cost

    await log_ai_usage(
        session,
        project_id=project_id,
        user_id=current_user.id,
        endpoint="mockup_generate",
        model=img_result["model"],
    )

    # Save to AIGeneratedImage gallery
    gen_img = AIGeneratedImage(
        project_sku_id=body.project_sku_id,
        media_asset_id=asset.id,
        reference_asset_id=body.reference_asset_id,
        prompt_text=body.prompt,
        art_direction=art_direction,
        cost_rub=total_cost,
        model=img_result["model"],
        created_by=current_user.id,
    )
    session.add(gen_img)
    await session.flush()
    await session.commit()

    return AIPackageMockupResponse(
        id=gen_img.id,
        media_asset_id=asset.id,
        media_url=f"/api/media/{asset.id}",
        art_direction=art_direction,
        prompt=body.prompt,
        cost_rub=total_cost,
        model=img_result["model"],
    )


@router.get(
    "/mockups",
    response_model=list[AIGeneratedImageRead],
    summary="Галерея AI-генерированных mockup'ов",
)
async def list_mockups(
    project_id: int,
    project_sku_id: int | None = None,
    session: Annotated[AsyncSession, Depends(get_db)] = None,
    current_user: Annotated[User, Depends(get_current_user)] = None,
) -> list[AIGeneratedImageRead]:
    """Все AI-генерированные mockup'ы проекта (или конкретного SKU)."""
    stmt = (
        select(AIGeneratedImage)
        .join(ProjectSKU, AIGeneratedImage.project_sku_id == ProjectSKU.id)
        .where(ProjectSKU.project_id == project_id)
    )
    if project_sku_id is not None:
        stmt = stmt.where(AIGeneratedImage.project_sku_id == project_sku_id)
    stmt = stmt.order_by(AIGeneratedImage.created_at.desc()).limit(50)

    rows = (await session.scalars(stmt)).all()
    return [
        AIGeneratedImageRead(
            id=r.id,
            project_sku_id=r.project_sku_id,
            media_asset_id=r.media_asset_id,
            media_url=f"/api/media/{r.media_asset_id}",
            reference_asset_id=r.reference_asset_id,
            prompt_text=r.prompt_text,
            art_direction=r.art_direction,
            cost_rub=r.cost_rub,
            model=r.model,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]


@router.post(
    "/mockups/{mockup_id}/set-primary",
    summary="Установить mockup как основное изображение SKU",
)
@limiter.limit("10/minute", key_func=_rate_limit_key)
async def set_mockup_as_primary(
    request: Request,
    project_id: int,
    mockup_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(_set_rate_limit_user)],
) -> dict:
    """Set AIGeneratedImage as ProjectSKU.package_image_id."""
    gen_img = await session.get(AIGeneratedImage, mockup_id)
    if gen_img is None:
        raise HTTPException(status_code=404, detail="Mockup не найден")

    psku = await session.get(ProjectSKU, gen_img.project_sku_id)
    if psku is None or psku.project_id != project_id:
        raise HTTPException(status_code=404, detail="SKU не найден в проекте")

    psku.package_image_id = gen_img.media_asset_id
    await session.flush()
    await session.commit()

    return {"status": "set", "package_image_id": gen_img.media_asset_id}


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
    await session.commit()

    stats = await get_project_usage_stats(session, project_id)
    return AIUsageResponse(**stats)
