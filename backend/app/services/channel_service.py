"""Channels read-only service.

Channels — справочная сущность. Наполняется один раз через
scripts/seed_reference_data.py (25 каналов из листа DASH MENU GORJI).
В MVP не редактируется через UI: приходит новая Excel-модель → запускаем
seed → обновляются справочники.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel


async def list_channels(session: AsyncSession) -> list[Channel]:
    stmt = select(Channel).order_by(Channel.code)
    return list((await session.scalars(stmt)).all())


async def get_channel(
    session: AsyncSession,
    channel_id: int,
) -> Channel | None:
    return await session.get(Channel, channel_id)
