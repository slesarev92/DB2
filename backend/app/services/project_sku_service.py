"""ProjectSKU CRUD + COGS preview расчёт.

ProjectSKU — это включение SKU в конкретный проект с проектными rates
(production_cost_rate; ca_m_rate и marketing_rate с 2026-05-15 живут на
ProjectSKUChannel — см. Q6 в CLIENT_FEEDBACK_v2_DECISIONS.md). При delete
каскадно удаляются связанные BOMItem (FK ON DELETE CASCADE в схеме).
"""
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import BOMItem, ProjectSKU, SKU
from app.schemas.project_sku import ProjectSKUCreate, ProjectSKUUpdate


class ProjectSKUDuplicateError(Exception):
    """SKU уже включён в этот проект (нарушение UNIQUE project_id+sku_id)."""


class SKUNotFoundError(Exception):
    """sku_id ссылается на несуществующий SKU."""


async def list_project_skus(
    session: AsyncSession,
    project_id: int,
) -> list[ProjectSKU]:
    """Список ProjectSKU проекта с явно загруженным sku (selectinload)."""
    stmt = (
        select(ProjectSKU)
        .where(ProjectSKU.project_id == project_id)
        .options(selectinload(ProjectSKU.sku))
        .order_by(ProjectSKU.created_at)
    )
    return list((await session.scalars(stmt)).all())


async def get_project_sku(
    session: AsyncSession,
    psk_id: int,
) -> ProjectSKU | None:
    """Один ProjectSKU с загруженным sku."""
    stmt = (
        select(ProjectSKU)
        .where(ProjectSKU.id == psk_id)
        .options(selectinload(ProjectSKU.sku))
    )
    return await session.scalar(stmt)


async def create_project_sku(
    session: AsyncSession,
    project_id: int,
    data: ProjectSKUCreate,
) -> ProjectSKU:
    """Создаёт ProjectSKU. Поднимает SKUNotFoundError / ProjectSKUDuplicateError."""
    sku = await session.get(SKU, data.sku_id)
    if sku is None:
        raise SKUNotFoundError()

    psk = ProjectSKU(project_id=project_id, **data.model_dump())

    # Savepoint (begin_nested) — попытка вставки в изолированной точке
    # сохранения. При IntegrityError откатываем только savepoint,
    # а не всю outer-транзакцию. Это критично:
    #   - в production: get_db() работает с одной транзакцией на запрос
    #   - в тестах: outer transaction идёт от conftest db_session fixture
    # Без savepoint простой rollback в сервисе деассоциирует сессию и
    # ломает обе модели работы (даёт SAWarning).
    try:
        async with session.begin_nested():
            session.add(psk)
            await session.flush()
    except IntegrityError as exc:
        raise ProjectSKUDuplicateError() from exc

    # Перезагружаем с selectinload(sku) для корректной сериализации nested
    return await get_project_sku(session, psk.id)  # type: ignore[return-value]


async def update_project_sku(
    session: AsyncSession,
    psk: ProjectSKU,
    data: ProjectSKUUpdate,
) -> ProjectSKU:
    update_fields = data.model_dump(exclude_unset=True)
    for key, value in update_fields.items():
        setattr(psk, key, value)
    await session.flush()
    return await get_project_sku(session, psk.id)  # type: ignore[return-value]


async def delete_project_sku(
    session: AsyncSession,
    psk: ProjectSKU,
) -> None:
    """Удаляет ProjectSKU. BOMItem удаляются каскадно (FK ON DELETE CASCADE)."""
    await session.delete(psk)
    await session.flush()


async def calculate_cogs_per_unit_preview(
    session: AsyncSession,
    psk_id: int,
) -> Decimal:
    """Preview-расчёт COGS на единицу по BOM-позициям.

    Формула:  Σ (quantity_per_unit × price_per_unit × (1 + loss_pct))

    Это упрощённая preview-формула для UI. Реальная формула COGS
    из эталонной модели GORJI (включая copacking, production rate,
    логистику в %) реализуется в задаче 2.1 расчётного ядра по ADR-CE-01.
    """
    boms = (
        await session.scalars(
            select(BOMItem).where(BOMItem.project_sku_id == psk_id)
        )
    ).all()

    if not boms:
        return Decimal("0")

    total = Decimal("0")
    for b in boms:
        total += b.quantity_per_unit * b.price_per_unit * (Decimal("1") + b.loss_pct)
    return total
