"""C #14 Fine Tuning per-period overrides — API endpoints.

4 endpoints:
  GET  /api/projects/{project_id}/fine-tuning/per-period/sku/{sku_id}
  PUT  /api/projects/{project_id}/fine-tuning/per-period/sku/{sku_id}
  GET  /api/projects/{project_id}/fine-tuning/per-period/channel/{psk_channel_id}
  PUT  /api/projects/{project_id}/fine-tuning/per-period/channel/{psk_channel_id}

Auth: get_current_user (401 if no/invalid token) + project ownership check
via project_service (same pattern as financial_plan.py).
LookupError from service → 404.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_owned_project
from app.db import get_db
from app.models import Project
from app.models.entities import ProjectSKU, ProjectSKUChannel
from app.schemas.fine_tuning import (
    ChannelOverridesPayload,
    ChannelOverridesResponse,
    SkuOverridesPayload,
    SkuOverridesResponse,
)
from app.services import fine_tuning_period_service

router = APIRouter(tags=["fine-tuning"])

_BASE = "/api/projects/{project_id}/fine-tuning/per-period"


async def _resolve_owned_channel(
    session: AsyncSession,
    project_id: int,
    psk_channel_id: int,
) -> ProjectSKUChannel:
    """Найти channel и убедиться что он принадлежит project_id через SKU.

    Защита от IDOR timing-side-channel: возврат 404 если channel не найден
    ИЛИ принадлежит другому проекту (одинаковый response, нет утечки
    о существовании id в чужом проекте).
    """
    ch = await session.get(ProjectSKUChannel, psk_channel_id)
    if ch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found"
        )
    sku = await session.get(ProjectSKU, ch.project_sku_id)
    if sku is None or sku.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found"
        )
    return ch


@router.get(f"{_BASE}/sku/{{sku_id}}", response_model=SkuOverridesResponse)
async def get_sku_overrides(
    project_id: int,
    sku_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    project: Annotated[Project, Depends(require_owned_project)],
) -> SkuOverridesResponse:
    """Возвращает per-period override массивы SKU-уровня.

    copacking_rate_by_period=None если override не задан.
    """
    try:
        return await fine_tuning_period_service.list_overrides_by_sku(
            session, project_id, sku_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.put(
    f"{_BASE}/sku/{{sku_id}}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def put_sku_overrides(
    project_id: int,
    sku_id: int,
    payload: SkuOverridesPayload,
    session: Annotated[AsyncSession, Depends(get_db)],
    project: Annotated[Project, Depends(require_owned_project)],
) -> None:
    """Полная замена per-period override для SKU.

    Передать copacking_rate_by_period=None — удалить override.
    """
    try:
        await fine_tuning_period_service.replace_sku_overrides(
            session, project_id, sku_id, payload.copacking_rate_by_period
        )
        await session.commit()
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    f"{_BASE}/channel/{{psk_channel_id}}",
    response_model=ChannelOverridesResponse,
)
async def get_channel_overrides(
    project_id: int,
    psk_channel_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    project: Annotated[Project, Depends(require_owned_project)],
) -> ChannelOverridesResponse:
    """Возвращает per-period override массивы Channel-уровня (3 поля).

    Поля = None если override не задан.
    """
    ch = await _resolve_owned_channel(session, project_id, psk_channel_id)
    try:
        return await fine_tuning_period_service.list_overrides_by_channel(
            session, project_id, ch.project_sku_id, psk_channel_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.put(
    f"{_BASE}/channel/{{psk_channel_id}}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def put_channel_overrides(
    project_id: int,
    psk_channel_id: int,
    payload: ChannelOverridesPayload,
    session: Annotated[AsyncSession, Depends(get_db)],
    project: Annotated[Project, Depends(require_owned_project)],
) -> None:
    """Полная замена per-period overrides для Channel (3 поля).

    Передать поле=None — удалить override для этого поля.
    """
    ch = await _resolve_owned_channel(session, project_id, psk_channel_id)
    try:
        await fine_tuning_period_service.replace_channel_overrides(
            session,
            project_id,
            ch.project_sku_id,
            psk_channel_id,
            logistics_cost_per_kg_by_period=payload.logistics_cost_per_kg_by_period,
            ca_m_rate_by_period=payload.ca_m_rate_by_period,
            marketing_rate_by_period=payload.marketing_rate_by_period,
        )
        await session.commit()
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
