"""AI usage logging + budget enforcement (Phase 7.2 → 7.5).

Разделение ответственности:

- `ai_service.py` — чистый Polza SDK клиент без БД-зависимостей.
- `ai_context_builder.py` — БД → context dict.
- `ai_cache.py` — Redis cache/dedupe.
- `ai_usage.py` (этот файл) — БД → ai_usage_log + daily/monthly budget.

Endpoint flow (Phase 7.5):
    1. `check_daily_user_budget(session, user_id)` — 429 если > 100₽/день
    2. `check_project_budget(session, project_id)` — 429 если > monthly limit
    3. Context build → cache check → ai_service.complete_json(...)
    4. `log_ai_usage(session, user_id, project_id, feature, result, ...)`
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import AIUsageLog, Project
from app.services.ai_service import (
    AICallResult,
    AIFeature,
    calculate_cost,
)

# Safety net: per-user daily cap, защищает от bugged UI loops
# (useEffect вызывает endpoint в бесконечном цикле). Ratified
# 2026-04-09 в Phase 7 architectural decisions (#6, L3 system-level).
DEFAULT_DAILY_USER_BUDGET_RUB = Decimal("100")


async def check_daily_user_budget(
    session: AsyncSession,
    user_id: int,
    limit_rub: Decimal = DEFAULT_DAILY_USER_BUDGET_RUB,
) -> Decimal:
    """Проверить что пользователь не превысил daily cap на AI.

    Phase 7.5: фильтрует по `ai_usage_log.user_id` — реальный
    per-user лимит (ранее в 7.2 был глобальный).

    Returns:
        Текущий daily spend в рублях.

    Raises:
        HTTPException 429: daily cap превышен.
    """
    day_ago = datetime.now(timezone.utc) - timedelta(hours=24)

    stmt = select(
        func.coalesce(func.sum(AIUsageLog.cost_rub), 0)
    ).where(
        AIUsageLog.created_at >= day_ago,
        AIUsageLog.user_id == user_id,
    )

    total: Decimal = Decimal(str((await session.scalar(stmt)) or 0))

    if total >= limit_rub:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "daily_user_budget_exceeded",
                "spent_rub": str(total),
                "limit_rub": str(limit_rub),
                "message": (
                    f"Дневной лимит AI {limit_rub}₽ исчерпан "
                    f"(текущий расход: {total}₽). Попробуйте завтра."
                ),
            },
        )

    return total


async def check_project_budget(
    session: AsyncSession,
    project_id: int,
) -> tuple[Decimal, Decimal | None]:
    """Проверить месячный AI-бюджет проекта.

    Считает SUM(cost_rub) из `ai_usage_log` за текущий календарный
    месяц (с 1-го числа 00:00 UTC). Сравнивает с
    `Project.ai_budget_rub_monthly`.

    Returns:
        (spent_rub, budget_rub) — текущий расход и лимит (None = unlimited).

    Raises:
        HTTPException 429: бюджет проекта исчерпан.
        HTTPException 404: проект не найден.
    """
    project = await session.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} не найден",
        )

    budget_rub = project.ai_budget_rub_monthly
    if budget_rub is None:
        # Budget не задан = unlimited, пропускаем проверку
        return Decimal("0"), None

    month_start = _current_month_start()
    stmt = select(
        func.coalesce(func.sum(AIUsageLog.cost_rub), 0)
    ).where(
        AIUsageLog.project_id == project_id,
        AIUsageLog.created_at >= month_start,
    )
    spent: Decimal = Decimal(str((await session.scalar(stmt)) or 0))

    if spent >= budget_rub:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "project_budget_exceeded",
                "spent_rub": str(spent),
                "limit_rub": str(budget_rub),
                "message": (
                    f"Месячный AI-бюджет проекта исчерпан "
                    f"({spent}₽ / {budget_rub}₽). "
                    f"Увеличьте лимит в Параметрах проекта."
                ),
            },
        )

    return spent, budget_rub


async def log_ai_usage(
    session: AsyncSession,
    *,
    project_id: int | None,
    user_id: int | None = None,
    endpoint: str,
    result: AICallResult | None = None,
    model: str | None = None,
    error: str | None = None,
) -> AIUsageLog:
    """Записать один вызов AI в `ai_usage_log`.

    Phase 7.5: добавлен `user_id` — записывает кто выполнил вызов.
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
        user_id=user_id,
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


def _current_month_start() -> datetime:
    """UTC datetime первого числа текущего месяца."""
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, 1, tzinfo=timezone.utc)


async def get_project_usage_stats(
    session: AsyncSession,
    project_id: int,
) -> dict:
    """Собрать агрегированную статистику AI-расходов проекта.

    Используется endpoint'ом GET /api/projects/{id}/ai/usage.
    """
    project = await session.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} не найден",
        )

    month_start = _current_month_start()
    budget_rub = project.ai_budget_rub_monthly

    # 1. Total spent this month
    stmt_month = select(
        func.coalesce(func.sum(AIUsageLog.cost_rub), 0)
    ).where(
        AIUsageLog.project_id == project_id,
        AIUsageLog.created_at >= month_start,
    )
    spent_rub: Decimal = Decimal(str((await session.scalar(stmt_month)) or 0))

    # 2. Daily history (current month, group by date)
    stmt_daily = (
        select(
            func.date_trunc("day", AIUsageLog.created_at).label("day"),
            func.coalesce(func.sum(AIUsageLog.cost_rub), 0).label("spent"),
            func.count().label("calls"),
        )
        .where(
            AIUsageLog.project_id == project_id,
            AIUsageLog.created_at >= month_start,
        )
        .group_by("day")
        .order_by("day")
    )
    daily_rows = (await session.execute(stmt_daily)).all()
    daily_history = [
        {
            "date": row.day.strftime("%Y-%m-%d") if row.day else "",
            "spent_rub": Decimal(str(row.spent)),
            "calls": row.calls,
        }
        for row in daily_rows
    ]

    # 3. Recent calls (last 20)
    stmt_recent = (
        select(AIUsageLog)
        .where(AIUsageLog.project_id == project_id)
        .order_by(AIUsageLog.created_at.desc())
        .limit(20)
    )
    recent_rows = (await session.scalars(stmt_recent)).all()
    recent_calls = [
        {
            "id": row.id,
            "timestamp": row.created_at.isoformat(),
            "endpoint": row.endpoint,
            "model": row.model,
            "prompt_tokens": row.prompt_tokens,
            "completion_tokens": row.completion_tokens,
            "cost_rub": row.cost_rub,
            "latency_ms": row.latency_ms,
            "error": row.error,
            "cached": row.endpoint.endswith("_cache") or row.endpoint.endswith("_dedupe"),
        }
        for row in recent_rows
    ]

    # 4. Cache hit rate (24h)
    day_ago = datetime.now(timezone.utc) - timedelta(hours=24)
    stmt_total_24h = (
        select(func.count())
        .select_from(AIUsageLog)
        .where(
            AIUsageLog.project_id == project_id,
            AIUsageLog.created_at >= day_ago,
        )
    )
    stmt_cache_24h = (
        select(func.count())
        .select_from(AIUsageLog)
        .where(
            AIUsageLog.project_id == project_id,
            AIUsageLog.created_at >= day_ago,
            AIUsageLog.endpoint.like("%_cache"),
        )
    )
    total_24h = (await session.scalar(stmt_total_24h)) or 0
    cache_24h = (await session.scalar(stmt_cache_24h)) or 0
    cache_hit_rate = cache_24h / total_24h if total_24h > 0 else 0.0

    # Budget calculations
    if budget_rub is not None:
        remaining = max(budget_rub - spent_rub, Decimal("0"))
        percent = float(spent_rub / budget_rub) if budget_rub > 0 else 0.0
    else:
        remaining = None
        percent = 0.0

    return {
        "project_id": project_id,
        "month_start": date(month_start.year, month_start.month, 1).isoformat(),
        "spent_rub": spent_rub,
        "budget_rub": budget_rub,
        "budget_remaining_rub": remaining,
        "budget_percent_used": min(percent, 1.0),
        "daily_history": daily_history,
        "recent_calls": recent_calls,
        "cache_hit_rate_24h": round(cache_hit_rate, 4),
    }
