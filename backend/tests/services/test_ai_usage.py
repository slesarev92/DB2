"""Тесты AI usage logging + daily budget (Phase 7.2).

Интеграционные против реального postgres — `ai_usage_log` модель есть,
надо проверить что запись идёт правильно. Budget проверка тоже требует
SUM() query — мок не даст уверенности.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import AIUsageLog
from app.services.ai_service import AICallResult
from app.services.ai_usage import (
    DEFAULT_DAILY_USER_BUDGET_RUB,
    check_daily_user_budget,
    estimate_cost_for_feature,
    log_ai_usage,
)
from app.services.ai_service import AIFeature


# ============================================================
# log_ai_usage
# ============================================================


class _DummyParsed(BaseModel):
    """Минимальный Pydantic для AICallResult.parsed в тестах."""

    ok: bool = True


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
# check_daily_user_budget
# ============================================================


async def test_check_daily_user_budget_empty_history(
    db_session: AsyncSession,
) -> None:
    """Нет записей → budget 0, no exception."""
    current = await check_daily_user_budget(db_session, user_id=42)
    assert current == Decimal("0")


async def test_check_daily_user_budget_under_limit(
    db_session: AsyncSession,
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
            )
        )
    await db_session.flush()

    current = await check_daily_user_budget(db_session, user_id=42)
    assert current == Decimal("3.15")


async def test_check_daily_user_budget_exceeded(
    db_session: AsyncSession,
) -> None:
    """Сумма >= лимита → HTTPException 429."""
    db_session.add(
        AIUsageLog(
            endpoint="explain_kpi",
            model="anthropic/claude-sonnet-4.6",
            prompt_tokens=100000,
            completion_tokens=20000,
            cost_rub=Decimal("100"),  # ровно лимит
            latency_ms=5000,
        )
    )
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await check_daily_user_budget(db_session, user_id=42)

    assert exc_info.value.status_code == 429
    assert "Дневной лимит" in exc_info.value.detail


async def test_check_daily_user_budget_custom_limit(
    db_session: AsyncSession,
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
        )
    )
    await db_session.flush()

    # Лимит 2₽, текущий расход 3₽ → 429
    with pytest.raises(HTTPException) as exc_info:
        await check_daily_user_budget(
            db_session, user_id=42, limit_rub=Decimal("2")
        )
    assert exc_info.value.status_code == 429


async def test_check_daily_user_budget_old_records_excluded(
    db_session: AsyncSession,
) -> None:
    """Записи старше 24 часов не учитываются в daily sum."""
    old_log = AIUsageLog(
        endpoint="explain_kpi",
        model="anthropic/claude-sonnet-4.6",
        prompt_tokens=100000,
        completion_tokens=20000,
        cost_rub=Decimal("500"),  # больше лимита, но 2 дня назад
        latency_ms=5000,
    )
    db_session.add(old_log)
    await db_session.flush()
    # Руками forge created_at в прошлое
    old_log.created_at = datetime.now(timezone.utc) - timedelta(days=2)
    await db_session.flush()

    # Не должно падать — старые записи исключены
    current = await check_daily_user_budget(db_session, user_id=42)
    assert current == Decimal("0")


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
