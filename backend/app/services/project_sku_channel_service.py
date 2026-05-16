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
    ProjectSKUChannelDefaults,
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
    *,
    auto_fill_predict: bool = True,
) -> ProjectSKUChannel:
    """Создаёт ProjectSKUChannel + (опционально) генерирует predict-слой.

    Поднимает ChannelNotFoundError / ProjectSKUChannelDuplicateError.
    Использует savepoint pattern для async-safe обработки IntegrityError.

    Если `auto_fill_predict=True` (дефолт), после успешного create вызывает
    `predict_service.fill_predict_for_psk_channel` — заполняет 43×3=129
    PeriodValue с predict-слоем (ND/Offtake рамп-ап + shelf price с
    инфляцией) для всех 3 сценариев проекта. Это позволяет сразу запускать
    /recalculate без предварительного ручного ввода значений.

    `auto_fill_predict=False` нужен для тестов test_period_values, которые
    управляют слоями PeriodValue вручную и не должны конфликтовать с
    автогенерацией.
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

    if auto_fill_predict:
        # Импорт внутри функции — predict_service импортирует много моделей,
        # держим граф зависимостей сервисов плоским.
        from app.services.predict_service import fill_predict_for_psk_channel

        await fill_predict_for_psk_channel(session, psk_channel)

    # Перезагружаем с selectinload для корректной сериализации nested
    return await get_psk_channel(session, psk_channel.id)  # type: ignore[return-value]


async def bulk_create_psk_channels(
    session: AsyncSession,
    project_sku_id: int,
    channel_ids: list[int],
    defaults: ProjectSKUChannelDefaults,
) -> list[ProjectSKUChannel]:
    """C #16: создаёт N PSC в одной savepoint-транзакции (atomic).

    Весь loop обёрнут в `session.begin_nested()` — outer SAVEPOINT.
    Если любой iteration raise'ит (ChannelNotFoundError /
    ProjectSKUChannelDuplicateError из create_psk_channel), savepoint
    откатывается атомарно: уже flushed PSC + их predict-layer (43×3=129
    PeriodValue) исчезают. Outer transaction (test_user, project и т.п.)
    не затрагивается — критично для test-environment с shared session.

    Внутренний savepoint pattern внутри `create_psk_channel` для
    IntegrityError per-channel — это nested savepoint внутри нашего
    outer savepoint, конфликта нет (savepoints стекируются).

    Errors (пробрасываются как есть после savepoint rollback'а):
      - `ChannelNotFoundError` — первый невалидный channel_id
      - `ProjectSKUChannelDuplicateError` — первый duplicate (psk_id, channel_id)
    """
    created: list[ProjectSKUChannel] = []
    async with session.begin_nested():
        for ch_id in channel_ids:
            data = ProjectSKUChannelCreate(
                channel_id=ch_id,
                **defaults.model_dump(),
            )
            psc = await create_psk_channel(session, project_sku_id, data)
            created.append(psc)
    return created


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
