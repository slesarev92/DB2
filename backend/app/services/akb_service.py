"""Service для AKB — план дистрибуции (B-12).

CRUD для akb_entries per project.
C #17: compute_auto_entries — read-only АКБ из nd_target × ОКБ канала.
"""
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import AKBEntry
from app.models.entities import Channel, ProjectSKU, ProjectSKUChannel, SKU
from app.schemas.akb import AKBAutoEntry, AKBCreate, AKBUpdate

# C #17: порядок сортировки групп каналов (по логике приоритетности в модели)
_CHANNEL_GROUP_ORDER = ("HM", "SM", "MM", "TT", "E_COM", "HORECA", "QSR", "OTHER")
_GROUP_RANK = {g: i for i, g in enumerate(_CHANNEL_GROUP_ORDER)}


async def compute_auto_entries(
    session: AsyncSession,
    project_id: int,
) -> list[AKBAutoEntry]:
    """C #17: compute target outlets per (PSK × Channel) from nd_target × universe_outlets.

    Read-only, не персистится. Сортировка: channel_group order → channel.code → sku.brand/name.
    """
    stmt = (
        select(ProjectSKUChannel, ProjectSKU, SKU, Channel)
        .join(ProjectSKU, ProjectSKUChannel.project_sku_id == ProjectSKU.id)
        .join(SKU, ProjectSKU.sku_id == SKU.id)
        .join(Channel, ProjectSKUChannel.channel_id == Channel.id)
        .where(ProjectSKU.project_id == project_id)
    )
    rows = (await session.execute(stmt)).all()

    entries: list[AKBAutoEntry] = []
    for psc, psk, sku, channel in rows:
        if channel.universe_outlets is not None:
            target: int | None = int(round(float(psc.nd_target) * channel.universe_outlets))
        else:
            target = None
        entries.append(
            AKBAutoEntry(
                psk_id=psk.id,
                sku_id=sku.id,
                sku_brand=sku.brand,
                sku_name=sku.name,
                channel_id=channel.id,
                channel_code=channel.code,
                channel_name=channel.name,
                channel_group=channel.channel_group,
                universe_outlets=channel.universe_outlets,
                nd_target=psc.nd_target,
                target_outlets=target,
            )
        )

    # Sort: group rank → channel code → sku brand → sku name
    entries.sort(
        key=lambda e: (
            _GROUP_RANK.get(e.channel_group, 99),
            e.channel_code,
            e.sku_brand,
            e.sku_name,
        )
    )
    return entries


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
