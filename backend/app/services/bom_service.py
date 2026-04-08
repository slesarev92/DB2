"""BOMItem CRUD."""
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
    bom = BOMItem(project_sku_id=project_sku_id, **data.model_dump())
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
