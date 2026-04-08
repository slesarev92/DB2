"""Scenario service: list/get/update + чтение результатов расчёта.

Сценарии создаются автоматически в project_service.create_project (3 шт.
на проект). Здесь только чтение и обновление дельт. Запись результатов
расчёта — задача 2.4 (Celery pipeline orchestration).
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PeriodScope, Scenario, ScenarioResult, ScenarioType
from app.schemas.scenario import ScenarioUpdate

# Алфавит даёт неправильный порядок ('aggressive' < 'base' < 'conservative'
# и 'y1y10' < 'y1y3' < 'y1y5'). Сортируем в Python по бизнес-смыслу.
SCENARIO_ORDER: dict[ScenarioType, int] = {
    ScenarioType.BASE: 0,
    ScenarioType.CONSERVATIVE: 1,
    ScenarioType.AGGRESSIVE: 2,
}

SCOPE_ORDER: dict[PeriodScope, int] = {
    PeriodScope.Y1Y3: 0,
    PeriodScope.Y1Y5: 1,
    PeriodScope.Y1Y10: 2,
}


async def list_scenarios_for_project(
    session: AsyncSession,
    project_id: int,
) -> list[Scenario]:
    """3 сценария проекта в порядке Base → Conservative → Aggressive."""
    stmt = select(Scenario).where(Scenario.project_id == project_id)
    scenarios = list((await session.scalars(stmt)).all())
    scenarios.sort(key=lambda s: SCENARIO_ORDER[s.type])
    return scenarios


async def get_scenario(
    session: AsyncSession,
    scenario_id: int,
) -> Scenario | None:
    return await session.get(Scenario, scenario_id)


async def update_scenario(
    session: AsyncSession,
    scenario: Scenario,
    data: ScenarioUpdate,
) -> Scenario:
    """PATCH: только дельты и notes. type/project_id неизменны (нет в схеме)."""
    update_fields = data.model_dump(exclude_unset=True)
    for key, value in update_fields.items():
        setattr(scenario, key, value)
    await session.flush()
    await session.refresh(scenario)
    return scenario


async def list_results_for_scenario(
    session: AsyncSession,
    scenario_id: int,
) -> list[ScenarioResult]:
    """Все ScenarioResult сценария, отсортированы Y1Y3 → Y1Y5 → Y1Y10."""
    stmt = select(ScenarioResult).where(ScenarioResult.scenario_id == scenario_id)
    results = list((await session.scalars(stmt)).all())
    results.sort(key=lambda r: SCOPE_ORDER[r.period_scope])
    return results
