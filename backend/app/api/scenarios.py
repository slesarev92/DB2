"""Scenarios endpoints.

  GET    /api/projects/{project_id}/scenarios     ← 3 сценария проекта
  GET    /api/scenarios/{scenario_id}             ← один сценарий
  PATCH  /api/scenarios/{scenario_id}             ← изменить дельты/notes
  GET    /api/scenarios/{scenario_id}/results     ← результаты расчёта (3 scope)
  GET    /api/scenarios/{scenario_id}/channel-deltas  ← per-channel overrides (B-06)
  PUT    /api/scenarios/{scenario_id}/channel-deltas  ← replace per-channel overrides
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db import get_db
from app.models import User
from app.schemas.scenario import (
    ChannelDeltaItem,
    ChannelDeltaRequest,
    ScenarioRead,
    ScenarioResultRead,
    ScenarioUpdate,
)
from app.services import project_service, scenario_service

router = APIRouter(tags=["scenarios"])

_project_not_found = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Project not found",
)
_scenario_not_found = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Scenario not found",
)


@router.get(
    "/api/projects/{project_id}/scenarios",
    response_model=list[ScenarioRead],
)
async def list_project_scenarios_endpoint(
    project_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[ScenarioRead]:
    """Возвращает 3 сценария проекта в порядке Base → Conservative → Aggressive."""
    project = await project_service.get_project(session, project_id)
    if project is None:
        raise _project_not_found

    scenarios = await scenario_service.list_scenarios_for_project(
        session, project_id
    )
    return [ScenarioRead.model_validate(s) for s in scenarios]


@router.get(
    "/api/scenarios/{scenario_id}",
    response_model=ScenarioRead,
)
async def get_scenario_endpoint(
    scenario_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ScenarioRead:
    scenario = await scenario_service.get_scenario(session, scenario_id)
    if scenario is None:
        raise _scenario_not_found
    return ScenarioRead.model_validate(scenario)


@router.patch(
    "/api/scenarios/{scenario_id}",
    response_model=ScenarioRead,
)
async def update_scenario_endpoint(
    scenario_id: int,
    data: ScenarioUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ScenarioRead:
    """Обновляет дельты сценария. type и project_id не изменяются."""
    scenario = await scenario_service.get_scenario(session, scenario_id)
    if scenario is None:
        raise _scenario_not_found
    updated = await scenario_service.update_scenario(session, scenario, data)
    await session.commit()
    return ScenarioRead.model_validate(updated)


@router.get(
    "/api/scenarios/{scenario_id}/results",
    response_model=list[ScenarioResultRead],
)
async def get_scenario_results_endpoint(
    scenario_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[ScenarioResultRead]:
    """Результаты последнего расчёта по 3 горизонтам (Y1-3 / Y1-5 / Y1-10).

    Возвращает 404 с actionable-сообщением если расчёт ещё не запускался.
    Расчётный pipeline появится в задаче 2.4.
    """
    scenario = await scenario_service.get_scenario(session, scenario_id)
    if scenario is None:
        raise _scenario_not_found

    results = await scenario_service.list_results_for_scenario(
        session, scenario_id
    )
    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Scenario has not been calculated yet. "
                "Run POST /api/projects/{project_id}/recalculate first "
                "(available after task 2.4)."
            ),
        )

    return [ScenarioResultRead.model_validate(r) for r in results]


# ============================================================
# B-06: Per-channel delta overrides
# ============================================================


@router.get(
    "/api/scenarios/{scenario_id}/channel-deltas",
    response_model=list[ChannelDeltaItem],
)
async def get_channel_deltas_endpoint(
    scenario_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[ChannelDeltaItem]:
    """Per-channel delta overrides для сценария."""
    scenario = await scenario_service.get_scenario(session, scenario_id)
    if scenario is None:
        raise _scenario_not_found
    return await scenario_service.list_channel_deltas(session, scenario_id)


@router.put(
    "/api/scenarios/{scenario_id}/channel-deltas",
    response_model=list[ChannelDeltaItem],
)
async def put_channel_deltas_endpoint(
    scenario_id: int,
    body: ChannelDeltaRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[ChannelDeltaItem]:
    """Полная замена per-channel overrides. Items без записей → fallback."""
    scenario = await scenario_service.get_scenario(session, scenario_id)
    if scenario is None:
        raise _scenario_not_found
    result = await scenario_service.replace_channel_deltas(
        session, scenario_id, body.items
    )
    await session.commit()
    return result
