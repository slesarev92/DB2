"""API endpoints для ProjectFinancialPlan — CAPEX/OPEX по годам проекта.

Минимальный CRUD:
- GET /api/projects/{project_id}/financial-plan
  → всегда 10 строк Y1..Y10 (нули если записи нет)
- PUT /api/projects/{project_id}/financial-plan
  Body: {items: [{year, capex, opex}, ...]}
  → полная замена плана, возвращает актуальное состояние

DELETE отдельных записей не реализован — PUT с items=[] полностью
очищает план. Это упрощает контракт для UI.
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
from app.services import financial_plan_service, project_service

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
    """Всегда 10 строк Y1..Y10. Отсутствующие значения = 0."""
    project = await project_service.get_project(session, project_id)
    if project is None:
        raise _project_not_found
    return await financial_plan_service.list_plan_by_year(session, project_id)


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
    """Полная замена плана проекта. Возвращает обновлённый список."""
    project = await project_service.get_project(session, project_id)
    if project is None:
        raise _project_not_found
    result = await financial_plan_service.replace_plan(
        session, project_id, body.items
    )
    await session.commit()
    return result
