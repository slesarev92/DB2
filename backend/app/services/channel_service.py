"""Channel service — CRUD + региональная фильтрация (B-05).

Каналы — справочная сущность. Seed через scripts/seed_reference_data.py.
B-05 добавляет region и полный CRUD.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel
from app.schemas.channel import ChannelCreate, ChannelUpdate


async def list_channels(
    session: AsyncSession,
    region: str | None = None,
) -> list[Channel]:
    stmt = select(Channel).order_by(Channel.code)
    if region is not None:
        stmt = stmt.where(Channel.region == region)
    return list((await session.scalars(stmt)).all())


async def get_channel(
    session: AsyncSession,
    channel_id: int,
) -> Channel | None:
    return await session.get(Channel, channel_id)


async def create_channel(
    session: AsyncSession,
    data: ChannelCreate,
) -> Channel:
    ch = Channel(**data.model_dump())
    session.add(ch)
    await session.flush()
    await session.refresh(ch)
    return ch


async def update_channel(
    session: AsyncSession,
    channel: Channel,
    data: ChannelUpdate,
) -> Channel:
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(channel, key, value)
    await session.flush()
    await session.refresh(channel)
    return channel


async def delete_channel(session: AsyncSession, channel: Channel) -> None:
    await session.delete(channel)
    await session.flush()
