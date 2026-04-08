"""BOMItem endpoints.

Два префикса — один ресурс:
  /api/project-skus/{psk_id}/bom  — list + create (контекст ProjectSKU)
  /api/bom-items/{bom_id}         — patch/delete (плоский путь)
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db import get_db
from app.models import User
from app.schemas.bom import BOMItemCreate, BOMItemRead, BOMItemUpdate
from app.services import bom_service, project_sku_service

router = APIRouter(tags=["bom"])

_bom_not_found = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="BOM item not found",
)
_psk_not_found = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="ProjectSKU not found",
)


@router.get(
    "/api/project-skus/{psk_id}/bom",
    response_model=list[BOMItemRead],
)
async def list_bom_endpoint(
    psk_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[BOMItemRead]:
    psk = await project_sku_service.get_project_sku(session, psk_id)
    if psk is None:
        raise _psk_not_found
    items = await bom_service.list_bom_items(session, psk_id)
    return [BOMItemRead.model_validate(b) for b in items]


@router.post(
    "/api/project-skus/{psk_id}/bom",
    response_model=BOMItemRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_bom_endpoint(
    psk_id: int,
    data: BOMItemCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> BOMItemRead:
    psk = await project_sku_service.get_project_sku(session, psk_id)
    if psk is None:
        raise _psk_not_found
    bom = await bom_service.create_bom_item(session, psk_id, data)
    await session.commit()
    await session.refresh(bom)
    return BOMItemRead.model_validate(bom)


@router.patch(
    "/api/bom-items/{bom_id}",
    response_model=BOMItemRead,
)
async def update_bom_endpoint(
    bom_id: int,
    data: BOMItemUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> BOMItemRead:
    bom = await bom_service.get_bom_item(session, bom_id)
    if bom is None:
        raise _bom_not_found
    updated = await bom_service.update_bom_item(session, bom, data)
    await session.commit()
    await session.refresh(updated)
    return BOMItemRead.model_validate(updated)


@router.delete(
    "/api/bom-items/{bom_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_bom_endpoint(
    bom_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    bom = await bom_service.get_bom_item(session, bom_id)
    if bom is None:
        raise _bom_not_found
    await bom_service.delete_bom_item(session, bom)
    await session.commit()
