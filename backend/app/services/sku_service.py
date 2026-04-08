"""SKU справочник CRUD.

DELETE проверяет наличие связей с ProjectSKU и поднимает SKUInUseError
если SKU используется хотя бы одним проектом — иначе RESTRICT в FK
поднял бы IntegrityError на flush, а нам нужна понятная семантика
для перевода в HTTP 409.
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SKU, ProjectSKU
from app.schemas.sku import SKUCreate, SKUUpdate


class SKUInUseError(Exception):
    """SKU нельзя удалить — на него ссылаются ProjectSKU записи."""


async def list_skus(session: AsyncSession) -> list[SKU]:
    stmt = select(SKU).order_by(SKU.brand, SKU.name)
    return list((await session.scalars(stmt)).all())


async def get_sku(session: AsyncSession, sku_id: int) -> SKU | None:
    return await session.get(SKU, sku_id)


async def create_sku(session: AsyncSession, data: SKUCreate) -> SKU:
    sku = SKU(**data.model_dump())
    session.add(sku)
    await session.flush()
    await session.refresh(sku)
    return sku


async def update_sku(
    session: AsyncSession,
    sku: SKU,
    data: SKUUpdate,
) -> SKU:
    update_fields = data.model_dump(exclude_unset=True)
    for key, value in update_fields.items():
        setattr(sku, key, value)
    await session.flush()
    await session.refresh(sku)
    return sku


async def delete_sku(session: AsyncSession, sku: SKU) -> None:
    """Удаляет SKU, если на него никто не ссылается. Иначе SKUInUseError."""
    refs = await session.scalar(
        select(func.count())
        .select_from(ProjectSKU)
        .where(ProjectSKU.sku_id == sku.id)
    )
    if refs and refs > 0:
        raise SKUInUseError()
    await session.delete(sku)
    await session.flush()
