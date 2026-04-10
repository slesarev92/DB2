"""Тесты AI usage logging + daily/project budget (Phase 7.2 → 7.5).

Интеграционные против реального postgres — `ai_usage_log` модель есть,
надо проверить что запись идёт правильно. Budget проверка тоже требует
SUM() query — мок не даст уверенности.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import AIUsageLog, Project, User
from app.services.ai_service import AICallResult, AIFeature
from app.services.ai_usage import (
    DEFAULT_DAILY_USER_BUDGET_RUB,
    check_daily_user_budget,
    check_project_budget,
    estimate_cost_for_feature,
    get_project_usage_stats,
    log_ai_usage,
)


# ============================================================
# Helpers
# ============================================================


class _DummyParsed(BaseModel):
    """Минимальный Pydantic для AICallResult.parsed в тестах."""

    ok: bool = True


@pytest.fixture
async def budget_user(db_session: AsyncSession) -> User:
    """User для тестов budget — не зависит от conftest.test_user."""
    from app.core.security import hash_password

    user = User(
        email="budget-test@example.com",
        hashed_password=hash_password("test"),
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def budget_project(db_session: AsyncSession) -> Project:
    """Проект с default ai_budget_rub_monthly = 500₽."""
    proj = Project(
        name="Budget Test Project",
        start_date=date(2026, 1, 1),
        horizon_years=10,
    )
    db_session.add(proj)
    await db_session.flush()
    return proj


# ============================================================
# log_ai_usage
# ============================================================


async def test_log_ai_usage_happy_path(db_session: AsyncSession) -> None:
    """Успешный вызов → запись в ai_usage_log с корректным cost_rub."""
    result: AICallResult[_DummyParsed] = AICallResult(
        parsed=_DummyParsed(),
        model="anthropic/claude-sonnet-4.6",
        prompt_tokens=2500,
        completion_tokens=400,
        total_tokens=2900,
        latency_ms=1234,
    )

    log = await log_ai_usage(
        db_session,
        project_id=None,
        endpoint="explain_kpi",
        result=result,
    )

    assert log.id is not None
    assert log.endpoint == "explain_kpi"
    assert log.model == "anthropic/claude-sonnet-4.6"
    assert log.prompt_tokens == 2500
    assert log.completion_tokens == 400
    assert log.latency_ms == 1234
    # calculate_cost: 2.5 × 0.30 + 0.4 × 1.50 = 1.35
    assert log.cost_rub == Decimal("1.350000")
    assert log.error is None


async def test_log_ai_usage_with_user_id(
    db_session: AsyncSession, budget_user: User
) -> None:
    """Phase 7.5: user_id записывается в лог."""
    log = await log_ai_usage(
        db_session,
        project_id=None,
        user_id=budget_user.id,
        endpoint="explain_kpi",
        model="anthropic/claude-sonnet-4.6",
        result=None,
    )
    assert log.user_id == budget_user.id


async def test_log_ai_usage_cache_hit(db_session: AsyncSession) -> None:
    """Cache hit → result=None, cost_rub=0, endpoint с суффиксом _cache."""
    log = await log_ai_usage(
        db_session,
        project_id=None,
        endpoint="explain_kpi_cache",
        model="anthropic/claude-sonnet-4.6",
        result=None,
    )

    assert log.cost_rub == Decimal("0")
    assert log.prompt_tokens == 0
    assert log.completion_tokens == 0
    assert log.error is None
    assert log.endpoint == "explain_kpi_cache"


async def test_log_ai_usage_error(db_session: AsyncSession) -> None:
    """Failure path → error text, cost_rub=None, tokens=0."""
    log = await log_ai_usage(
        db_session,
        project_id=None,
        endpoint="explain_kpi",
        error="AIServiceUnavailableError: connection timeout",
    )

    assert log.error is not None
    assert "timeout" in log.error
    assert log.cost_rub is None  # NULL для ошибок (не потратили ничего)


# ============================================================
# check_daily_user_budget (Phase 7.5: per-user filtering)
# ============================================================


async def test_check_daily_user_budget_empty_history(
    db_session: AsyncSession, budget_user: User
) -> None:
    """Нет записей → budget 0, no exception."""
    current = await check_daily_user_budget(db_session, user_id=budget_user.id)
    assert current == Decimal("0")


async def test_check_daily_user_budget_under_limit(
    db_session: AsyncSession, budget_user: User
) -> None:
    """Есть записи, но сумма < лимита → возвращает sum."""
    for _ in range(3):
        db_session.add(
            AIUsageLog(
                endpoint="explain_kpi",
                model="anthropic/claude-sonnet-4.6",
                prompt_tokens=2000,
                completion_tokens=300,
                cost_rub=Decimal("1.05"),  # 3 × 1.05 = 3.15₽
                latency_ms=1000,
                user_id=budget_user.id,
            )
        )
    await db_session.flush()

    current = await check_daily_user_budget(db_session, user_id=budget_user.id)
    assert current == Decimal("3.15")


async def test_check_daily_user_budget_exceeded(
    db_session: AsyncSession, budget_user: User
) -> None:
    """Сумма >= лимита → HTTPException 429."""
    db_session.add(
        AIUsageLog(
            endpoint="explain_kpi",
            model="anthropic/claude-sonnet-4.6",
            prompt_tokens=100000,
            completion_tokens=20000,
            cost_rub=Decimal("100"),
            latency_ms=5000,
            user_id=budget_user.id,
        )
    )
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await check_daily_user_budget(db_session, user_id=budget_user.id)

    assert exc_info.value.status_code == 429
    assert "daily_user_budget_exceeded" in exc_info.value.detail["error"]


async def test_check_daily_user_budget_custom_limit(
    db_session: AsyncSession, budget_user: User
) -> None:
    """Тесты могут override'ить лимит для детерминизма."""
    db_session.add(
        AIUsageLog(
            endpoint="explain_kpi",
            model="anthropic/claude-sonnet-4.6",
            prompt_tokens=5000,
            completion_tokens=1000,
            cost_rub=Decimal("3.0"),
            latency_ms=1000,
            user_id=budget_user.id,
        )
    )
    await db_session.flush()

    # Лимит 2₽, текущий расход 3₽ → 429
    with pytest.raises(HTTPException) as exc_info:
        await check_daily_user_budget(
            db_session, user_id=budget_user.id, limit_rub=Decimal("2")
        )
    assert exc_info.value.status_code == 429


async def test_check_daily_user_budget_old_records_excluded(
    db_session: AsyncSession, budget_user: User
) -> None:
    """Записи старше 24 часов не учитываются в daily sum."""
    old_log = AIUsageLog(
        endpoint="explain_kpi",
        model="anthropic/claude-sonnet-4.6",
        prompt_tokens=100000,
        completion_tokens=20000,
        cost_rub=Decimal("500"),
        latency_ms=5000,
        user_id=budget_user.id,
    )
    db_session.add(old_log)
    await db_session.flush()
    old_log.created_at = datetime.now(timezone.utc) - timedelta(days=2)
    await db_session.flush()

    current = await check_daily_user_budget(db_session, user_id=budget_user.id)
    assert current == Decimal("0")


async def test_check_daily_user_budget_filters_by_user(
    db_session: AsyncSession, budget_user: User
) -> None:
    """Phase 7.5: другой user's записи не учитываются."""
    from app.core.security import hash_password

    other_user = User(
        email="other-user-budget@example.com",
        hashed_password=hash_password("test"),
    )
    db_session.add(other_user)
    await db_session.flush()

    # Другой user потратил 100₽ — наш user не должен быть заблокирован
    db_session.add(
        AIUsageLog(
            endpoint="explain_kpi",
            model="anthropic/claude-sonnet-4.6",
            cost_rub=Decimal("100"),
            latency_ms=1000,
            user_id=other_user.id,
        )
    )
    await db_session.flush()

    current = await check_daily_user_budget(db_session, user_id=budget_user.id)
    assert current == Decimal("0")  # наш user потратил 0


# ============================================================
# check_project_budget (Phase 7.5)
# ============================================================


async def test_check_project_budget_under_limit(
    db_session: AsyncSession, budget_project: Project
) -> None:
    """Расход < бюджета → возвращает (spent, budget)."""
    db_session.add(
        AIUsageLog(
            project_id=budget_project.id,
            endpoint="explain_kpi",
            model="anthropic/claude-sonnet-4.6",
            cost_rub=Decimal("10"),
            latency_ms=1000,
        )
    )
    await db_session.flush()

    spent, budget = await check_project_budget(db_session, budget_project.id)
    assert spent == Decimal("10")
    assert budget == Decimal("500.00")


async def test_check_project_budget_at_limit(
    db_session: AsyncSession, budget_project: Project
) -> None:
    """Расход == бюджету → 429."""
    db_session.add(
        AIUsageLog(
            project_id=budget_project.id,
            endpoint="explain_kpi",
            model="anthropic/claude-sonnet-4.6",
            cost_rub=Decimal("500"),
            latency_ms=1000,
        )
    )
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await check_project_budget(db_session, budget_project.id)
    assert exc_info.value.status_code == 429
    assert "project_budget_exceeded" in exc_info.value.detail["error"]


async def test_check_project_budget_over_limit(
    db_session: AsyncSession, budget_project: Project
) -> None:
    """Расход > бюджета → 429."""
    db_session.add(
        AIUsageLog(
            project_id=budget_project.id,
            endpoint="explain_kpi",
            model="anthropic/claude-sonnet-4.6",
            cost_rub=Decimal("600"),
            latency_ms=1000,
        )
    )
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await check_project_budget(db_session, budget_project.id)
    assert exc_info.value.status_code == 429


async def test_check_project_budget_null_budget_means_unlimited(
    db_session: AsyncSession, budget_project: Project
) -> None:
    """ai_budget_rub_monthly = NULL → unlimited, no 429."""
    budget_project.ai_budget_rub_monthly = None
    await db_session.flush()

    db_session.add(
        AIUsageLog(
            project_id=budget_project.id,
            endpoint="explain_kpi",
            model="anthropic/claude-sonnet-4.6",
            cost_rub=Decimal("999999"),
            latency_ms=1000,
        )
    )
    await db_session.flush()

    spent, budget = await check_project_budget(db_session, budget_project.id)
    assert spent == Decimal("0")  # skipped query, default 0
    assert budget is None


async def test_check_project_budget_deleted_project_returns_404(
    db_session: AsyncSession, budget_project: Project
) -> None:
    """Deleted project → 404."""
    budget_project.deleted_at = datetime.now(timezone.utc)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await check_project_budget(db_session, budget_project.id)
    assert exc_info.value.status_code == 404


async def test_check_project_budget_old_month_excluded(
    db_session: AsyncSession, budget_project: Project
) -> None:
    """Записи за прошлый месяц не учитываются."""
    old_log = AIUsageLog(
        project_id=budget_project.id,
        endpoint="explain_kpi",
        model="anthropic/claude-sonnet-4.6",
        cost_rub=Decimal("1000"),
        latency_ms=1000,
    )
    db_session.add(old_log)
    await db_session.flush()
    old_log.created_at = datetime.now(timezone.utc) - timedelta(days=35)
    await db_session.flush()

    spent, budget = await check_project_budget(db_session, budget_project.id)
    assert spent == Decimal("0")


# ============================================================
# get_project_usage_stats (Phase 7.5)
# ============================================================


async def test_get_project_usage_stats_empty(
    db_session: AsyncSession, budget_project: Project
) -> None:
    """Нет вызовов → zero stats."""
    stats = await get_project_usage_stats(db_session, budget_project.id)
    assert stats["spent_rub"] == Decimal("0")
    assert stats["budget_rub"] == Decimal("500.00")
    assert stats["budget_remaining_rub"] == Decimal("500.00")
    assert stats["budget_percent_used"] == 0.0
    assert stats["daily_history"] == []
    assert stats["recent_calls"] == []
    assert stats["cache_hit_rate_24h"] == 0.0


async def test_get_project_usage_stats_with_data(
    db_session: AsyncSession, budget_project: Project
) -> None:
    """Несколько вызовов → correct aggregation."""
    for i in range(3):
        db_session.add(
            AIUsageLog(
                project_id=budget_project.id,
                endpoint="explain_kpi" if i < 2 else "explain_kpi_cache",
                model="anthropic/claude-sonnet-4.6",
                cost_rub=Decimal("10") if i < 2 else Decimal("0"),
                latency_ms=1000,
            )
        )
    await db_session.flush()

    stats = await get_project_usage_stats(db_session, budget_project.id)
    assert stats["spent_rub"] == Decimal("20")
    assert stats["budget_remaining_rub"] == Decimal("480.00")
    assert abs(stats["budget_percent_used"] - 0.04) < 0.001
    assert len(stats["recent_calls"]) == 3
    # 1 cache hit out of 3 calls
    cache_calls = [c for c in stats["recent_calls"] if c["cached"]]
    assert len(cache_calls) == 1


async def test_get_project_usage_stats_deleted_project(
    db_session: AsyncSession, budget_project: Project
) -> None:
    """Deleted project → 404."""
    budget_project.deleted_at = datetime.now(timezone.utc)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await get_project_usage_stats(db_session, budget_project.id)
    assert exc_info.value.status_code == 404


# ============================================================
# estimate_cost_for_feature
# ============================================================


def test_estimate_cost_for_feature_explain_kpi() -> None:
    """EXPLAIN_KPI ~3₽ — используется в UI pre-flight label."""
    assert estimate_cost_for_feature(AIFeature.EXPLAIN_KPI) == Decimal("3")


def test_estimate_cost_for_feature_content_field() -> None:
    """CONTENT_FIELD — самая дешёвая через haiku tier."""
    assert estimate_cost_for_feature(AIFeature.CONTENT_FIELD) == Decimal("0.5")


def test_estimate_cost_for_feature_executive_summary() -> None:
    """EXECUTIVE_SUMMARY через HEAVY tier (opus) → дорого."""
    assert estimate_cost_for_feature(AIFeature.EXECUTIVE_SUMMARY) == Decimal("10")
