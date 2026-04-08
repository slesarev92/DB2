"""ProjectSKUChannel CRUD — параметры SKU в конкретном канале.

Дубликат (project_sku_id, channel_id) ловится через savepoint pattern
(см. ADR в задаче 1.3 и комментарии в project_sku_service).
"""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Channel, ProjectSKUChannel
from app.schemas.project_sku_channel import (
    ProjectSKUChannelCreate,
    ProjectSKUChannelUpdate,
)


class ChannelNotFoundError(Exception):
    """channel_id ссылается на несуществующий канал."""


class ProjectSKUChannelDuplicateError(Exception):
    """Этот канал уже привязан к данному ProjectSKU."""


async def list_channels_for_psk(
    session: AsyncSession,
    project_sku_id: int,
) -> list[ProjectSKUChannel]:
    stmt = (
        select(ProjectSKUChannel)
        .where(ProjectSKUChannel.project_sku_id == project_sku_id)
        .options(selectinload(ProjectSKUChannel.channel))
        .order_by(ProjectSKUChannel.created_at)
    )
    return list((await session.scalars(stmt)).all())


async def get_psk_channel(
    session: AsyncSession,
    psk_channel_id: int,
) -> ProjectSKUChannel | None:
    stmt = (
        select(ProjectSKUChannel)
        .where(ProjectSKUChannel.id == psk_channel_id)
        .options(selectinload(ProjectSKUChannel.channel))
    )
    return await session.scalar(stmt)


async def create_psk_channel(
    session: AsyncSession,
    project_sku_id: int,
    data: ProjectSKUChannelCreate,
) -> ProjectSKUChannel:
    """Создаёт ProjectSKUChannel.

    Поднимает ChannelNotFoundError / ProjectSKUChannelDuplicateError.
    Использует savepoint pattern для async-safe обработки IntegrityError.
    """
    channel = await session.get(Channel, data.channel_id)
    if channel is None:
        raise ChannelNotFoundError()

    psk_channel = ProjectSKUChannel(
        project_sku_id=project_sku_id,
        **data.model_dump(),
    )
    try:
        async with session.begin_nested():
            session.add(psk_channel)
            await session.flush()
    except IntegrityError as exc:
        raise ProjectSKUChannelDuplicateError() from exc

    # Перезагружаем с selectinload для корректной сериализации nested
    return await get_psk_channel(session, psk_channel.id)  # type: ignore[return-value]


async def update_psk_channel(
    session: AsyncSession,
    psk_channel: ProjectSKUChannel,
    data: ProjectSKUChannelUpdate,
) -> ProjectSKUChannel:
    update_fields = data.model_dump(exclude_unset=True)
    for key, value in update_fields.items():
        setattr(psk_channel, key, value)
    await session.flush()
    return await get_psk_channel(session, psk_channel.id)  # type: ignore[return-value]


async def delete_psk_channel(
    session: AsyncSession,
    psk_channel: ProjectSKUChannel,
) -> None:
    await session.delete(psk_channel)
    await session.flush()
