"""ProjectSKUChannel endpoints.

Два префикса — один ресурс (по аналогии с project_skus.py):
  /api/project-skus/{psk_id}/channels  — list + create (контекст ProjectSKU)
  /api/psk-channels/{id}               — get/patch/delete (плоский путь)
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db import get_db
from app.models import User
from app.schemas.project_sku_channel import (
    ProjectSKUChannelCreate,
    ProjectSKUChannelRead,
    ProjectSKUChannelUpdate,
)
from app.services import (
    invalidation_service,
    project_service,
    project_sku_channel_service,
    project_sku_service,
)

router = APIRouter(tags=["psk-channels"])

_psk_not_found = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="ProjectSKU not found",
)
_psk_channel_not_found = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="ProjectSKUChannel not found",
)


async def _require_psk_owned(
    session: AsyncSession, psk_id: int, user: User
):
    """Load ProjectSKU и проверить ownership через project. 404 если нет."""
    psk = await project_sku_service.get_project_sku(session, psk_id)
    if psk is None:
        raise _psk_not_found
    if not await project_service.is_project_owned_by(
        session, psk.project_id, user
    ):
        raise _psk_not_found
    return psk


async def _require_psk_channel_owned(
    session: AsyncSession, psk_channel_id: int, user: User
):
    """Load PSC и проверить ownership через psk → project. 404 если нет."""
    psc = await project_sku_channel_service.get_psk_channel(
        session, psk_channel_id
    )
    if psc is None:
        raise _psk_channel_not_found
    psk = await project_sku_service.get_project_sku(session, psc.project_sku_id)
    if psk is None or not await project_service.is_project_owned_by(
        session, psk.project_id, user
    ):
        raise _psk_channel_not_found
    return psc


@router.get(
    "/api/project-skus/{psk_id}/channels",
    response_model=list[ProjectSKUChannelRead],
)
async def list_psk_channels_endpoint(
    psk_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[ProjectSKUChannelRead]:
    await _require_psk_owned(session, psk_id, current_user)

    items = await project_sku_channel_service.list_channels_for_psk(
        session, psk_id
    )
    return [ProjectSKUChannelRead.model_validate(item) for item in items]


@router.post(
    "/api/project-skus/{psk_id}/channels",
    response_model=ProjectSKUChannelRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_channel_to_psk_endpoint(
    psk_id: int,
    data: ProjectSKUChannelCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ProjectSKUChannelRead:
    psk = await _require_psk_owned(session, psk_id, current_user)

    try:
        psk_channel = await project_sku_channel_service.create_psk_channel(
            session, psk_id, data
        )
    except project_sku_channel_service.ChannelNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel with id={data.channel_id} not found",
        )
    except project_sku_channel_service.ProjectSKUChannelDuplicateError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This channel is already attached to the ProjectSKU",
        )

    await invalidation_service.mark_project_stale(session, psk.project_id)
    await session.commit()
    return ProjectSKUChannelRead.model_validate(psk_channel)


@router.get(
    "/api/psk-channels/{psk_channel_id}",
    response_model=ProjectSKUChannelRead,
)
async def get_psk_channel_endpoint(
    psk_channel_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ProjectSKUChannelRead:
    psk_channel = await _require_psk_channel_owned(
        session, psk_channel_id, current_user
    )
    return ProjectSKUChannelRead.model_validate(psk_channel)


@router.patch(
    "/api/psk-channels/{psk_channel_id}",
    response_model=ProjectSKUChannelRead,
)
async def update_psk_channel_endpoint(
    psk_channel_id: int,
    data: ProjectSKUChannelUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ProjectSKUChannelRead:
    psk_channel = await _require_psk_channel_owned(
        session, psk_channel_id, current_user
    )
    psk = await project_sku_service.get_project_sku(session, psk_channel.project_sku_id)

    updated = await project_sku_channel_service.update_psk_channel(
        session, psk_channel, data
    )
    if psk is not None:
        await invalidation_service.mark_project_stale(session, psk.project_id)
    await session.commit()
    return ProjectSKUChannelRead.model_validate(updated)


@router.delete(
    "/api/psk-channels/{psk_channel_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_psk_channel_endpoint(
    psk_channel_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    psk_channel = await _require_psk_channel_owned(
        session, psk_channel_id, current_user
    )
    psk = await project_sku_service.get_project_sku(session, psk_channel.project_sku_id)
    project_id = psk.project_id if psk is not None else None

    await project_sku_channel_service.delete_psk_channel(session, psk_channel)
    if project_id is not None:
        await invalidation_service.mark_project_stale(session, project_id)
    await session.commit()
