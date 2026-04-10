"""Service для OBPPC — Price-Pack-Channel matrix (B-13).

CRUD для obppc_entries per project.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import OBPPCEntry
from app.schemas.obppc import OBPPCCreate, OBPPCUpdate


async def list_entries(
    session: AsyncSession,
    project_id: int,
) -> list[OBPPCEntry]:
    rows = (
        await session.scalars(
            select(OBPPCEntry)
            .options(
                selectinload(OBPPCEntry.sku),
                selectinload(OBPPCEntry.channel),
            )
            .where(OBPPCEntry.project_id == project_id)
            .order_by(OBPPCEntry.id)
        )
    ).all()
    return list(rows)


async def get_entry(
    session: AsyncSession,
    entry_id: int,
) -> OBPPCEntry | None:
    result = await session.execute(
        select(OBPPCEntry)
        .options(
            selectinload(OBPPCEntry.sku),
            selectinload(OBPPCEntry.channel),
        )
        .where(OBPPCEntry.id == entry_id)
    )
    return result.scalar_one_or_none()


async def create_entry(
    session: AsyncSession,
    project_id: int,
    data: OBPPCCreate,
) -> OBPPCEntry:
    entry = OBPPCEntry(
        project_id=project_id,
        sku_id=data.sku_id,
        channel_id=data.channel_id,
        occasion=data.occasion,
        price_tier=data.price_tier,
        pack_format=data.pack_format,
        pack_size_ml=data.pack_size_ml,
        price_point=data.price_point,
        is_active=data.is_active,
        notes=data.notes,
    )
    session.add(entry)
    await session.flush()
    return await get_entry(session, entry.id)  # type: ignore[return-value]


async def update_entry(
    session: AsyncSession,
    entry: OBPPCEntry,
    data: OBPPCUpdate,
) -> OBPPCEntry:
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(entry, key, value)
    await session.flush()
    return await get_entry(session, entry.id)  # type: ignore[return-value]


async def delete_entry(session: AsyncSession, entry: OBPPCEntry) -> None:
    await session.delete(entry)
    await session.flush()
