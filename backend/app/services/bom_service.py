"""BOMItem CRUD.

B-04: при create с ingredient_id — auto-fill ingredient_name и
price_per_unit из каталога (если не заданы явно).
"""
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BOMItem
from app.schemas.bom import BOMItemCreate, BOMItemUpdate


async def list_bom_items(
    session: AsyncSession,
    project_sku_id: int,
) -> list[BOMItem]:
    stmt = (
        select(BOMItem)
        .where(BOMItem.project_sku_id == project_sku_id)
        .order_by(BOMItem.created_at)
    )
    return list((await session.scalars(stmt)).all())


async def get_bom_item(
    session: AsyncSession,
    bom_id: int,
) -> BOMItem | None:
    return await session.get(BOMItem, bom_id)


async def create_bom_item(
    session: AsyncSession,
    project_sku_id: int,
    data: BOMItemCreate,
) -> BOMItem:
    fields = data.model_dump()

    # B-04: auto-fill from ingredient catalog if ingredient_id is set
    if data.ingredient_id is not None:
        from app.services.ingredient_service import get_ingredient, get_latest_price

        ing = await get_ingredient(session, data.ingredient_id)
        if ing is not None:
            # Auto-fill ingredient_name if not explicitly provided or is placeholder
            if not data.ingredient_name or data.ingredient_name == ing.name:
                fields["ingredient_name"] = ing.name
            # Auto-fill price if still at default (0)
            if data.price_per_unit == Decimal("0"):
                latest = await get_latest_price(session, ing.id)
                if latest is not None:
                    fields["price_per_unit"] = latest

    bom = BOMItem(project_sku_id=project_sku_id, **fields)
    session.add(bom)
    await session.flush()
    await session.refresh(bom)
    return bom


async def update_bom_item(
    session: AsyncSession,
    bom: BOMItem,
    data: BOMItemUpdate,
) -> BOMItem:
    update_fields = data.model_dump(exclude_unset=True)
    for key, value in update_fields.items():
        setattr(bom, key, value)
    await session.flush()
    await session.refresh(bom)
    return bom


async def delete_bom_item(
    session: AsyncSession,
    bom: BOMItem,
) -> None:
    await session.delete(bom)
    await session.flush()
