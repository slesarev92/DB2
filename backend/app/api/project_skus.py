"""ProjectSKU endpoints.

Два префикса — один ресурс:
  /api/projects/{project_id}/skus  — list + create (контекст проекта)
  /api/project-skus/{psk_id}       — get/patch/delete (плоский путь)
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db import get_db
from app.models import User
from app.schemas.project_sku import (
    ProjectSKUCreate,
    ProjectSKUDetail,
    ProjectSKURead,
    ProjectSKUUpdate,
)
from app.services import invalidation_service, project_service, project_sku_service

router = APIRouter(tags=["project-skus"])

_not_found = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="ProjectSKU not found",
)
_project_not_found = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Project not found",
)


@router.get(
    "/api/projects/{project_id}/skus",
    response_model=list[ProjectSKURead],
)
async def list_project_skus_endpoint(
    project_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[ProjectSKURead]:
    project = await project_service.get_project(session, project_id, user=current_user)
    if project is None:
        raise _project_not_found

    psks = await project_sku_service.list_project_skus(session, project_id)
    return [ProjectSKURead.model_validate(p) for p in psks]


@router.post(
    "/api/projects/{project_id}/skus",
    response_model=ProjectSKURead,
    status_code=status.HTTP_201_CREATED,
)
async def add_sku_to_project_endpoint(
    project_id: int,
    data: ProjectSKUCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ProjectSKURead:
    project = await project_service.get_project(session, project_id, user=current_user)
    if project is None:
        raise _project_not_found

    try:
        psk = await project_sku_service.create_project_sku(session, project_id, data)
    except project_sku_service.SKUNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SKU with id={data.sku_id} not found",
        )
    except project_sku_service.ProjectSKUDuplicateError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This SKU is already added to the project",
        )

    await invalidation_service.mark_project_stale(session, project_id)
    await session.commit()
    return ProjectSKURead.model_validate(psk)


async def _load_owned_psk(
    session: AsyncSession, psk_id: int, user: User
):
    """Резолвит ProjectSKU и проверяет что его проект принадлежит user.
    Возвращает psk или raises 404 (не раскрывая факт существования).
    """
    psk = await project_sku_service.get_project_sku(session, psk_id)
    if psk is None:
        raise _not_found
    # S-01 IDOR: verify the project belongs to current user.
    owned = await project_service.get_project(session, psk.project_id, user=user)
    if owned is None:
        raise _not_found
    return psk


@router.get(
    "/api/project-skus/{psk_id}",
    response_model=ProjectSKUDetail,
)
async def get_project_sku_endpoint(
    psk_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ProjectSKUDetail:
    """Detail с preview-расчётом COGS_PER_UNIT (только на single GET)."""
    psk = await _load_owned_psk(session, psk_id, current_user)

    cogs = await project_sku_service.calculate_cogs_per_unit_preview(
        session, psk_id
    )
    return ProjectSKUDetail(
        **ProjectSKURead.model_validate(psk).model_dump(),
        cogs_per_unit_estimated=cogs,
    )


@router.patch(
    "/api/project-skus/{psk_id}",
    response_model=ProjectSKURead,
)
async def update_project_sku_endpoint(
    psk_id: int,
    data: ProjectSKUUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ProjectSKURead:
    psk = await _load_owned_psk(session, psk_id, current_user)
    updated = await project_sku_service.update_project_sku(session, psk, data)
    await invalidation_service.mark_project_stale(session, psk.project_id)
    await session.commit()
    return ProjectSKURead.model_validate(updated)


@router.delete(
    "/api/project-skus/{psk_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_project_sku_endpoint(
    psk_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Удаляет ProjectSKU. Связанные BOMItem каскадно удаляются (FK CASCADE)."""
    psk = await _load_owned_psk(session, psk_id, current_user)
    project_id = psk.project_id
    await project_sku_service.delete_project_sku(session, psk)
    await invalidation_service.mark_project_stale(session, project_id)
    await session.commit()
