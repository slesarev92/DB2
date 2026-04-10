"""Ingredient catalog API (B-04).

CRUD /api/ingredients + price history.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db import get_db
from app.models import User
from app.schemas.ingredient import (
    IngredientCreate,
    IngredientPriceCreate,
    IngredientPriceRead,
    IngredientRead,
    IngredientUpdate,
)
from app.services import ingredient_service

router = APIRouter(prefix="/api/ingredients", tags=["ingredients"])

_not_found = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Ingredient not found",
)


@router.get("", response_model=list[IngredientRead])
async def list_ingredients_endpoint(
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[IngredientRead]:
    return await ingredient_service.list_ingredients(session)


@router.post("", response_model=IngredientRead, status_code=status.HTTP_201_CREATED)
async def create_ingredient_endpoint(
    data: IngredientCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> IngredientRead:
    ing = await ingredient_service.create_ingredient(session, data)
    await session.commit()
    return IngredientRead(
        id=ing.id,
        name=ing.name,
        unit=ing.unit,
        category=ing.category,
        latest_price=None,
        created_at=ing.created_at,
    )


@router.patch("/{ingredient_id}", response_model=IngredientRead)
async def update_ingredient_endpoint(
    ingredient_id: int,
    data: IngredientUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> IngredientRead:
    ing = await ingredient_service.get_ingredient(session, ingredient_id)
    if ing is None:
        raise _not_found
    updated = await ingredient_service.update_ingredient(session, ing, data)
    await session.commit()
    latest = await ingredient_service.get_latest_price(session, updated.id)
    return IngredientRead(
        id=updated.id,
        name=updated.name,
        unit=updated.unit,
        category=updated.category,
        latest_price=latest,
        created_at=updated.created_at,
    )


@router.delete("/{ingredient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ingredient_endpoint(
    ingredient_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    ing = await ingredient_service.get_ingredient(session, ingredient_id)
    if ing is None:
        raise _not_found
    await ingredient_service.delete_ingredient(session, ing)
    await session.commit()


# ============================================================
# Price history
# ============================================================


@router.get(
    "/{ingredient_id}/prices",
    response_model=list[IngredientPriceRead],
)
async def list_prices_endpoint(
    ingredient_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[IngredientPriceRead]:
    ing = await ingredient_service.get_ingredient(session, ingredient_id)
    if ing is None:
        raise _not_found
    prices = await ingredient_service.list_prices(session, ingredient_id)
    return [IngredientPriceRead.model_validate(p) for p in prices]


@router.post(
    "/{ingredient_id}/prices",
    response_model=IngredientPriceRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_price_endpoint(
    ingredient_id: int,
    data: IngredientPriceCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> IngredientPriceRead:
    ing = await ingredient_service.get_ingredient(session, ingredient_id)
    if ing is None:
        raise _not_found
    price = await ingredient_service.add_price(session, ingredient_id, data)
    await session.commit()
    return IngredientPriceRead.model_validate(price)
