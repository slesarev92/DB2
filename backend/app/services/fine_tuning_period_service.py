"""C #14 Fine Tuning per-period overrides — service layer.

Атомарная замена JSONB-массивов длины 43 (None = убрать override).
SQLAlchemy mutation требует flag_modified для JSONB-полей.

JSONB storage: значения хранятся как строки (str) для сохранения точности
Decimal без потерь на float-конверсию. При чтении из БД строки → Decimal
через SkuOverridesResponse/ChannelOverridesResponse validators.
"""
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.entities import ProjectSKU, ProjectSKUChannel
from app.schemas.fine_tuning import (
    ChannelOverridesResponse,
    SkuOverridesResponse,
)

PERIOD_COUNT = 43


def _check_length(arr: list[Decimal | None] | None) -> None:
    if arr is not None and len(arr) != PERIOD_COUNT:
        raise ValueError(f"Array must have exactly {PERIOD_COUNT} elements, got {len(arr)}")


def _to_jsonb(arr: list[Decimal | None] | None) -> list[float | None] | None:
    """Конвертирует Decimal-массив в JSON-сериализуемый список float.

    None-элементы сохраняются как None. Весь массив None → None (убрать override).
    float используется для JSON-совместимости; при чтении из JSONB asyncpg
    возвращает float, который корректно сравнивается с Decimal в Python ==.
    Для API-уровня точность восстанавливается через Pydantic Decimal validator.
    """
    if arr is None:
        return None
    return [float(v) if v is not None else None for v in arr]


async def list_overrides_by_sku(
    session: AsyncSession,
    project_id: int,
    sku_id: int,
) -> SkuOverridesResponse:
    sku = await session.get(ProjectSKU, sku_id)
    if sku is None or sku.project_id != project_id:
        raise LookupError(f"ProjectSKU {sku_id} not found in project {project_id}")
    return SkuOverridesResponse(copacking_rate_by_period=sku.copacking_rate_by_period)


async def replace_sku_overrides(
    session: AsyncSession,
    project_id: int,
    sku_id: int,
    copacking_rate_by_period: list[Decimal | None] | None,
) -> None:
    _check_length(copacking_rate_by_period)
    sku = await session.get(ProjectSKU, sku_id)
    if sku is None or sku.project_id != project_id:
        raise LookupError(f"ProjectSKU {sku_id} not found in project {project_id}")
    sku.copacking_rate_by_period = _to_jsonb(copacking_rate_by_period)
    flag_modified(sku, "copacking_rate_by_period")


async def list_overrides_by_channel(
    session: AsyncSession,
    project_id: int,
    sku_id: int,
    psk_channel_id: int,
) -> ChannelOverridesResponse:
    ch = await session.get(ProjectSKUChannel, psk_channel_id)
    if ch is None or ch.project_sku_id != sku_id:
        raise LookupError(f"ProjectSKUChannel {psk_channel_id} not found")
    sku = await session.get(ProjectSKU, sku_id)
    if sku is None or sku.project_id != project_id:
        raise LookupError(f"ProjectSKU {sku_id} not found in project {project_id}")
    return ChannelOverridesResponse(
        logistics_cost_per_kg_by_period=ch.logistics_cost_per_kg_by_period,
        ca_m_rate_by_period=ch.ca_m_rate_by_period,
        marketing_rate_by_period=ch.marketing_rate_by_period,
    )


async def replace_channel_overrides(
    session: AsyncSession,
    project_id: int,
    sku_id: int,
    psk_channel_id: int,
    *,
    logistics_cost_per_kg_by_period: list[Decimal | None] | None,
    ca_m_rate_by_period: list[Decimal | None] | None,
    marketing_rate_by_period: list[Decimal | None] | None,
) -> None:
    for arr in (logistics_cost_per_kg_by_period, ca_m_rate_by_period, marketing_rate_by_period):
        _check_length(arr)
    ch = await session.get(ProjectSKUChannel, psk_channel_id)
    if ch is None or ch.project_sku_id != sku_id:
        raise LookupError(f"ProjectSKUChannel {psk_channel_id} not found")
    sku = await session.get(ProjectSKU, sku_id)
    if sku is None or sku.project_id != project_id:
        raise LookupError(f"ProjectSKU {sku_id} not found in project {project_id}")

    ch.logistics_cost_per_kg_by_period = _to_jsonb(logistics_cost_per_kg_by_period)
    ch.ca_m_rate_by_period = _to_jsonb(ca_m_rate_by_period)
    ch.marketing_rate_by_period = _to_jsonb(marketing_rate_by_period)
    flag_modified(ch, "logistics_cost_per_kg_by_period")
    flag_modified(ch, "ca_m_rate_by_period")
    flag_modified(ch, "marketing_rate_by_period")
