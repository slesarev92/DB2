"""F-01/F-02 staleness invalidation.

Когда пользователь меняет pipeline input (project settings, SKU rates,
PSC params, period values, BOM, scenarios, financial plan), сохранённые
ScenarioResult больше не соответствуют актуальным данным. UI должен
показать badge "⚠️ Расчёт устарел".

Этот модуль — ЕДИНАЯ точка инвалидации. Endpoint'ы PATCH/POST/DELETE
вызывают `mark_project_stale(session, project_id)` после успешной
mutation (до commit — изменения попадают в одну транзакцию).

Инвалидация — bulk UPDATE: одна SQL-команда на все scenario_results
всех сценариев проекта. `session.execute(update(...))` не трогает ORM
identity map, но для нашего use-case (end-user не смотрит stale
результаты в той же сессии) это OK.

Сброс флага: не здесь. При recalculate в `calculation_service.
calculate_and_save_scenario` старые ScenarioResult удаляются через
`DELETE WHERE scenario_id=X`, новые создаются со `server_default=false`
— is_stale автоматически False.
"""
from __future__ import annotations

import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ProjectFinancialPlan,
    ProjectSKU,
    ProjectSKUChannel,
    Scenario,
    ScenarioResult,
)

logger = logging.getLogger(__name__)


async def mark_project_stale(
    session: AsyncSession,
    project_id: int,
) -> int:
    """Помечает is_stale=True для всех ScenarioResult проекта.

    Args:
        session: активная async session (не коммитится — caller commit'ит).
        project_id: id проекта, чьи результаты инвалидируются.

    Returns:
        Количество обновлённых строк (0 если ScenarioResult ещё не созданы
        — не ошибка, recalculate ещё не выполнялся).

    Noop-safe: если scenario_results пустые (проект только что создан),
    UPDATE просто вернёт 0. Не поднимает исключение.
    """
    scenario_ids_subq = select(Scenario.id).where(Scenario.project_id == project_id)

    result = await session.execute(
        update(ScenarioResult)
        .where(ScenarioResult.scenario_id.in_(scenario_ids_subq))
        .values(is_stale=True)
    )
    rows = result.rowcount or 0
    logger.debug(
        "mark_project_stale: project_id=%s, updated_rows=%s", project_id, rows
    )
    return rows


async def mark_stale_by_psc(
    session: AsyncSession,
    psk_channel_id: int,
) -> int:
    """Инвалидирует проект через psc → psk → project_id.

    Удобно для period_values endpoints, которые знают только psk_channel_id.
    Возвращает 0 если psc не найден или не привязан к существующему
    проекту (noop-safe — не поднимает ошибку).
    """
    stmt = (
        select(ProjectSKU.project_id)
        .join(ProjectSKUChannel, ProjectSKUChannel.project_sku_id == ProjectSKU.id)
        .where(ProjectSKUChannel.id == psk_channel_id)
    )
    project_id = await session.scalar(stmt)
    if project_id is None:
        return 0
    return await mark_project_stale(session, project_id)


async def mark_stale_by_scenario(
    session: AsyncSession,
    scenario_id: int,
) -> int:
    """Инвалидирует проект через scenario.project_id.

    Удобно для scenarios endpoints (PATCH deltas, channel_deltas).
    """
    project_id = await session.scalar(
        select(Scenario.project_id).where(Scenario.id == scenario_id)
    )
    if project_id is None:
        return 0
    return await mark_project_stale(session, project_id)


async def mark_stale_by_financial_plan(
    session: AsyncSession,
    financial_plan_id: int,
) -> int:
    """Инвалидирует проект через financial_plan.project_id.

    Удобно для financial_plan endpoints.
    """
    project_id = await session.scalar(
        select(ProjectFinancialPlan.project_id).where(
            ProjectFinancialPlan.id == financial_plan_id
        )
    )
    if project_id is None:
        return 0
    return await mark_project_stale(session, project_id)
