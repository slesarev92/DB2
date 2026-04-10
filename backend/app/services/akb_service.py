"""Service для AKB — план дистрибуции (B-12).

CRUD для akb_entries per project.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import AKBEntry
from app.schemas.akb import AKBCreate, AKBUpdate


async def list_entries(
    session: AsyncSession,
    project_id: int,
) -> list[AKBEntry]:
    rows = (
        await session.scalars(
            select(AKBEntry)
            .options(selectinload(AKBEntry.channel))
            .where(AKBEntry.project_id == project_id)
            .order_by(AKBEntry.id)
        )
    ).all()
    return list(rows)


async def get_entry(
    session: AsyncSession,
    entry_id: int,
) -> AKBEntry | None:
    result = await session.execute(
        select(AKBEntry)
        .options(selectinload(AKBEntry.channel))
        .where(AKBEntry.id == entry_id)
    )
    return result.scalar_one_or_none()


async def create_entry(
    session: AsyncSession,
    project_id: int,
    data: AKBCreate,
) -> AKBEntry:
    entry = AKBEntry(
        project_id=project_id,
        channel_id=data.channel_id,
        universe_outlets=data.universe_outlets,
        target_outlets=data.target_outlets,
        coverage_pct=data.coverage_pct,
        weighted_distribution=data.weighted_distribution,
        notes=data.notes,
    )
    session.add(entry)
    await session.flush()
    # Reload with channel relationship
    return await get_entry(session, entry.id)  # type: ignore[return-value]


async def update_entry(
    session: AsyncSession,
    entry: AKBEntry,
    data: AKBUpdate,
) -> AKBEntry:
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(entry, key, value)
    await session.flush()
    return await get_entry(session, entry.id)  # type: ignore[return-value]


async def delete_entry(session: AsyncSession, entry: AKBEntry) -> None:
    await session.delete(entry)
    await session.flush()
