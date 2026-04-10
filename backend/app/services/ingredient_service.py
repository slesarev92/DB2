"""Service для справочника ингредиентов (B-04).

CRUD для ingredients + price history. Используется BOM auto-fill.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Ingredient, IngredientPrice
from app.schemas.ingredient import (
    IngredientCreate,
    IngredientPriceCreate,
    IngredientRead,
    IngredientUpdate,
)


async def list_ingredients(session: AsyncSession) -> list[IngredientRead]:
    """Все ингредиенты с latest_price."""
    rows = (
        await session.scalars(
            select(Ingredient).order_by(Ingredient.name)
        )
    ).all()

    result: list[IngredientRead] = []
    for ing in rows:
        latest = await _get_latest_price(session, ing.id)
        result.append(
            IngredientRead(
                id=ing.id,
                name=ing.name,
                unit=ing.unit,
                category=ing.category,
                latest_price=latest,
                created_at=ing.created_at,
            )
        )
    return result


async def get_ingredient(
    session: AsyncSession, ingredient_id: int
) -> Ingredient | None:
    return await session.get(Ingredient, ingredient_id)


async def create_ingredient(
    session: AsyncSession, data: IngredientCreate
) -> Ingredient:
    ing = Ingredient(
        name=data.name,
        unit=data.unit,
        category=data.category,
    )
    session.add(ing)
    await session.flush()
    await session.refresh(ing)
    return ing


async def update_ingredient(
    session: AsyncSession,
    ingredient: Ingredient,
    data: IngredientUpdate,
) -> Ingredient:
    update_fields = data.model_dump(exclude_unset=True)
    for key, value in update_fields.items():
        setattr(ingredient, key, value)
    await session.flush()
    await session.refresh(ingredient)
    return ingredient


async def delete_ingredient(
    session: AsyncSession, ingredient: Ingredient
) -> None:
    await session.delete(ingredient)
    await session.flush()


# ============================================================
# Price history
# ============================================================


async def list_prices(
    session: AsyncSession, ingredient_id: int
) -> list[IngredientPrice]:
    rows = (
        await session.scalars(
            select(IngredientPrice)
            .where(IngredientPrice.ingredient_id == ingredient_id)
            .order_by(IngredientPrice.effective_date.desc())
        )
    ).all()
    return list(rows)


async def add_price(
    session: AsyncSession,
    ingredient_id: int,
    data: IngredientPriceCreate,
) -> IngredientPrice:
    price = IngredientPrice(
        ingredient_id=ingredient_id,
        price_per_unit=data.price_per_unit,
        effective_date=data.effective_date,
        notes=data.notes,
    )
    session.add(price)
    await session.flush()
    await session.refresh(price)
    return price


async def _get_latest_price(
    session: AsyncSession,
    ingredient_id: int,
    as_of: date | None = None,
) -> Decimal | None:
    """Актуальная цена ингредиента на дату (default = сегодня)."""
    target = as_of or date.today()
    result = await session.scalar(
        select(IngredientPrice.price_per_unit)
        .where(
            IngredientPrice.ingredient_id == ingredient_id,
            IngredientPrice.effective_date <= target,
        )
        .order_by(IngredientPrice.effective_date.desc())
        .limit(1)
    )
    return result


async def get_latest_price(
    session: AsyncSession,
    ingredient_id: int,
) -> Decimal | None:
    """Public wrapper для auto-fill в BOM."""
    return await _get_latest_price(session, ingredient_id)
