"""API endpoints для ProjectFinancialPlan — CAPEX/OPEX per-period.

B.9b (2026-05-15): per-period вместо per-year. 43 элемента в массиве
(1..43): period 1..36 — monthly Y1-Y3, period 37..43 — yearly Y4-Y10.

- GET /api/projects/{project_id}/financial-plan
  → всегда 43 строки (нули если записи нет)
- PUT /api/projects/{project_id}/financial-plan
  Body: {items: [{period_number, capex, opex, opex_items?, capex_items?}, ...]}
  → полная замена плана; period_number уникальны в массиве.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db import get_db
from app.models import User
from app.schemas.financial_plan import (
    FinancialPlanItem,
    FinancialPlanRequest,
)
from app.services import financial_plan_service, invalidation_service, project_service

router = APIRouter(tags=["financial-plan"])

_project_not_found = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Project not found",
)


@router.get(
    "/api/projects/{project_id}/financial-plan",
    response_model=list[FinancialPlanItem],
)
async def get_project_financial_plan_endpoint(
    project_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[FinancialPlanItem]:
    """Всегда 43 строки (period_number 1..43). Отсутствующие = 0."""
    project = await project_service.get_project(session, project_id, user=current_user)
    if project is None:
        raise _project_not_found
    return await financial_plan_service.list_plan_by_period(session, project_id)


@router.put(
    "/api/projects/{project_id}/financial-plan",
    response_model=list[FinancialPlanItem],
)
async def put_project_financial_plan_endpoint(
    project_id: int,
    body: FinancialPlanRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[FinancialPlanItem]:
    """Полная замена плана проекта. Возвращает обновлённый список из 43 элементов."""
    project = await project_service.get_project(session, project_id, user=current_user)
    if project is None:
        raise _project_not_found
    result = await financial_plan_service.replace_plan(
        session, project_id, body.items
    )
    await invalidation_service.mark_project_stale(session, project_id)
    await session.commit()
    return result
