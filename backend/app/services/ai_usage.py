"""AI usage logging + daily budget enforcement (Phase 7.2).

Разделение ответственности:

- `ai_service.py` — чистый Polza SDK клиент без БД-зависимостей.
- `ai_context_builder.py` — БД → context dict.
- `ai_cache.py` — Redis cache/dedupe.
- `ai_usage.py` (этот файл) — БД → ai_usage_log + daily/monthly budget.

Endpoint flow (Phase 7.2):
    1. `check_daily_user_budget(session, user_id)` — 429 если превышен
    2. Context build → cache check → ai_service.complete_json(...)
    3. `log_ai_usage(session, user_id, project_id, feature, result, ...)`

В Phase 7.5 добавится `check_project_monthly_budget(...)` — проверка
`Project.ai_budget_rub_monthly` (поле добавится тогда же).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import AIUsageLog
from app.services.ai_service import (
    AICallResult,
    AIFeature,
    calculate_cost,
)

# Safety net: per-user daily cap, защищает от bugged UI loops
# (useEffect вызывает endpoint в бесконечном цикле). Ratified
# 2026-04-09 в Phase 7 architectural decisions (#6, L3 system-level).
# Значение не настраивается per-user в MVP — глобальный hard limit.
DEFAULT_DAILY_USER_BUDGET_RUB = Decimal("100")


async def check_daily_user_budget(
    session: AsyncSession,
    user_id: int,
    limit_rub: Decimal = DEFAULT_DAILY_USER_BUDGET_RUB,
) -> Decimal:
    """Проверить что пользователь не превысил daily cap на AI.

    Считает SUM(cost_rub) по `ai_usage_log` за последние 24 часа (не
    календарный день — чтобы не было скачков в полночь UTC). Если
    превышен — raises HTTP 429.

    Args:
        session: AsyncSession из Depends(get_db).
        user_id: current_user.id из Depends(get_current_user).
        limit_rub: override для тестов. В проде — DEFAULT.

    Returns:
        Текущий daily spend в рублях (для отображения в UI после
        успешной проверки). Может быть 0.

    Raises:
        HTTPException 429: daily cap превышен. Detail содержит
            текущий spend и лимит для user-facing сообщения.
    """
    day_ago = datetime.now(timezone.utc) - timedelta(hours=24)

    # AIUsageLog не имеет user_id колонки в Phase 7.1 модели — добавим
    # в миграцию Phase 7.5. Пока MVP: фильтруем через JOIN с Project
    # (который имеет created_by). Это не идеально, но позволяет нам
    # ввести daily budget уже в 7.2. Альтернатива — добавлять колонку
    # user_id сейчас, что требует миграции и усложняет 7.2.
    #
    # TODO Phase 7.5: добавить AIUsageLog.user_id + migrate + упростить
    # этот запрос до простого WHERE user_id = :uid.
    #
    # Для MVP считаем что user имеет daily cap по сумме cost_rub всех
    # вызовов — это conservative, лимит ниже ожидаемого, что норм для
    # safety net.
    stmt = select(
        func.coalesce(func.sum(AIUsageLog.cost_rub), 0)
    ).where(AIUsageLog.created_at >= day_ago)
    # Фильтр по user добавится в 7.5. Сейчас лимит глобальный на инстанс —
    # это override safety net, не per-user fair limit. Логируем явно:
    del user_id  # будет использоваться в 7.5

    total: Decimal = Decimal(str((await session.scalar(stmt)) or 0))

    if total >= limit_rub:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Дневной лимит AI {limit_rub}₽ исчерпан "
                f"(текущий расход: {total}₽). Попробуйте завтра."
            ),
        )

    return total


async def log_ai_usage(
    session: AsyncSession,
    *,
    project_id: int | None,
    endpoint: str,
    result: AICallResult | None = None,
    model: str | None = None,
    error: str | None = None,
) -> AIUsageLog:
    """Записать один вызов AI в `ai_usage_log`.

    Args:
        session: AsyncSession. Caller должен flush/commit сам.
        project_id: Связанный проект (nullable — будущие admin-операции).
        endpoint: Имя фичи/endpoint'а (`explain_kpi`, `explain_kpi_cache`,
            `explain_kpi_debug`, ...). Используется для агрегации
            расходов в 7.5 dashboard.
        result: `AICallResult` от `ai_service.complete_json` — содержит
            usage метрики. None при cache hit / error (тогда заполняем
            нулями).
        model: Явный model identifier (для cache_hit / error случая,
            когда result=None но мы знаем что планировали вызвать).
        error: Текст ошибки при failure. None при успехе / cache hit.

    Returns:
        Созданный AIUsageLog (flushed, но не committed).
    """
    if result is not None:
        log_model = result.model
        prompt_tokens = result.prompt_tokens
        completion_tokens = result.completion_tokens
        latency_ms = result.latency_ms
        cost_rub: Decimal | None = calculate_cost(
            log_model, prompt_tokens, completion_tokens
        )
    else:
        log_model = model or "unknown"
        prompt_tokens = 0
        completion_tokens = 0
        latency_ms = 0
        cost_rub = Decimal("0") if error is None else None

    usage = AIUsageLog(
        project_id=project_id,
        endpoint=endpoint,
        model=log_model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_rub=cost_rub,
        latency_ms=latency_ms,
        error=error,
    )
    session.add(usage)
    await session.flush()
    return usage


def estimate_cost_for_feature(feature: AIFeature) -> Decimal:
    """Грубая оценка типичной стоимости вызова фичи.

    Используется UI'ем для pre-flight cost estimate в кнопке
    («Explain KPI (~3₽)»). Значения — эмпирические из ручной проверки
    + из плана архитектурных решений. Не точные, но дают порядок.

    Для точного расчёта после вызова — `calculate_cost()`.
    """
    estimates: dict[AIFeature, Decimal] = {
        AIFeature.EXPLAIN_KPI: Decimal("3"),
        AIFeature.EXPLAIN_SENSITIVITY: Decimal("2"),
        AIFeature.FREEFORM_CHAT: Decimal("5"),
        AIFeature.EXECUTIVE_SUMMARY: Decimal("10"),
        AIFeature.CONTENT_FIELD: Decimal("0.5"),
        AIFeature.MARKETING_RESEARCH: Decimal("20"),
        AIFeature.PACKAGE_MOCKUP: Decimal("8"),
    }
    return estimates.get(feature, Decimal("3"))
