"""SKU справочник CRUD endpoints."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db import get_db
from app.models import User
from app.schemas.sku import SKUCreate, SKURead, SKUUpdate
from app.services import sku_service

router = APIRouter(prefix="/api/skus", tags=["skus"])

_not_found = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="SKU not found",
)


@router.get("", response_model=list[SKURead])
async def list_skus_endpoint(
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[SKURead]:
    skus = await sku_service.list_skus(session)
    return [SKURead.model_validate(s) for s in skus]


@router.post("", response_model=SKURead, status_code=status.HTTP_201_CREATED)
async def create_sku_endpoint(
    data: SKUCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SKURead:
    sku = await sku_service.create_sku(session, data)
    await session.commit()
    await session.refresh(sku)
    return SKURead.model_validate(sku)


@router.get("/{sku_id}", response_model=SKURead)
async def get_sku_endpoint(
    sku_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SKURead:
    sku = await sku_service.get_sku(session, sku_id)
    if sku is None:
        raise _not_found
    return SKURead.model_validate(sku)


@router.patch("/{sku_id}", response_model=SKURead)
async def update_sku_endpoint(
    sku_id: int,
    data: SKUUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SKURead:
    sku = await sku_service.get_sku(session, sku_id)
    if sku is None:
        raise _not_found
    updated = await sku_service.update_sku(session, sku, data)
    await session.commit()
    await session.refresh(updated)
    return SKURead.model_validate(updated)


@router.delete("/{sku_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sku_endpoint(
    sku_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    sku = await sku_service.get_sku(session, sku_id)
    if sku is None:
        raise _not_found
    try:
        await sku_service.delete_sku(session, sku)
    except sku_service.SKUInUseError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="SKU is referenced by one or more projects",
        )
    await session.commit()
