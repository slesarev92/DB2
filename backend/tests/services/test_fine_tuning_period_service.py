"""Pydantic schema tests for C #14 fine tuning overrides."""
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.fine_tuning import (
    ChannelOverridesPayload,
    ChannelOverridesResponse,
    SkuOverridesPayload,
    SkuOverridesResponse,
)


def test_sku_overrides_accepts_none() -> None:
    payload = SkuOverridesPayload(copacking_rate_by_period=None)
    assert payload.copacking_rate_by_period is None


def test_sku_overrides_accepts_43_element_array() -> None:
    arr = [Decimal("1.5")] * 43
    payload = SkuOverridesPayload(copacking_rate_by_period=arr)
    assert len(payload.copacking_rate_by_period) == 43


def test_sku_overrides_accepts_partial_null_elements() -> None:
    arr: list[Decimal | None] = [None] * 43
    arr[5] = Decimal("2.0")
    payload = SkuOverridesPayload(copacking_rate_by_period=arr)
    assert payload.copacking_rate_by_period[5] == Decimal("2.0")
    assert payload.copacking_rate_by_period[0] is None


def test_sku_overrides_rejects_wrong_length() -> None:
    with pytest.raises(ValidationError):
        SkuOverridesPayload(copacking_rate_by_period=[Decimal("1")] * 42)
    with pytest.raises(ValidationError):
        SkuOverridesPayload(copacking_rate_by_period=[Decimal("1")] * 44)


def test_sku_overrides_rejects_negative() -> None:
    arr = [Decimal("0")] * 43
    arr[0] = Decimal("-1")
    with pytest.raises(ValidationError):
        SkuOverridesPayload(copacking_rate_by_period=arr)


def test_channel_overrides_accepts_all_three_arrays() -> None:
    arr = [Decimal("0.1")] * 43
    payload = ChannelOverridesPayload(
        logistics_cost_per_kg_by_period=arr,
        ca_m_rate_by_period=arr,
        marketing_rate_by_period=arr,
    )
    assert payload.logistics_cost_per_kg_by_period == arr


def test_channel_overrides_rejects_rate_above_one() -> None:
    arr: list[Decimal | None] = [Decimal("0")] * 43
    arr[10] = Decimal("1.5")
    with pytest.raises(ValidationError):
        ChannelOverridesPayload(
            logistics_cost_per_kg_by_period=None,
            ca_m_rate_by_period=arr,
            marketing_rate_by_period=None,
        )


def test_channel_overrides_all_none_is_valid() -> None:
    payload = ChannelOverridesPayload(
        logistics_cost_per_kg_by_period=None,
        ca_m_rate_by_period=None,
        marketing_rate_by_period=None,
    )
    assert payload.ca_m_rate_by_period is None


def test_sku_overrides_response_round_trip() -> None:
    arr = [Decimal("5.5")] * 43
    resp = SkuOverridesResponse(copacking_rate_by_period=arr)
    dumped = resp.model_dump(mode="json")
    assert dumped["copacking_rate_by_period"][0] == "5.5"


def test_channel_overrides_response_round_trip() -> None:
    log_arr = [Decimal("12.34")] * 43
    rate_arr = [Decimal("0.05")] * 43
    resp = ChannelOverridesResponse(
        logistics_cost_per_kg_by_period=log_arr,
        ca_m_rate_by_period=rate_arr,
        marketing_rate_by_period=None,
    )
    dumped = resp.model_dump(mode="json")
    assert dumped["logistics_cost_per_kg_by_period"][0] == "12.34"
    assert dumped["ca_m_rate_by_period"][0] == "0.05"
    assert dumped["marketing_rate_by_period"] is None


def test_channel_overrides_rejects_negative_rate() -> None:
    arr: list[Decimal | None] = [Decimal("0")] * 43
    arr[7] = Decimal("-0.01")
    with pytest.raises(ValidationError):
        ChannelOverridesPayload(
            logistics_cost_per_kg_by_period=None,
            ca_m_rate_by_period=arr,
            marketing_rate_by_period=None,
        )
    with pytest.raises(ValidationError):
        ChannelOverridesPayload(
            logistics_cost_per_kg_by_period=None,
            ca_m_rate_by_period=None,
            marketing_rate_by_period=arr,
        )


# ============================================================
# C #14: service layer tests
# ============================================================
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Project, ProjectSKU, ProjectSKUChannel
from app.services.fine_tuning_period_service import (
    list_overrides_by_channel,
    list_overrides_by_sku,
    replace_channel_overrides,
    replace_sku_overrides,
)


@pytest.mark.asyncio
async def test_list_sku_overrides_returns_none_for_clean_project(
    db_session: AsyncSession,
    sample_project_with_sku: Project,
) -> None:
    project = sample_project_with_sku
    sku = (await db_session.scalars(select(ProjectSKU).where(ProjectSKU.project_id == project.id))).first()

    result = await list_overrides_by_sku(db_session, project.id, sku.id)
    assert result.copacking_rate_by_period is None


@pytest.mark.asyncio
async def test_replace_sku_overrides_persists_array(
    db_session: AsyncSession,
    sample_project_with_sku: Project,
) -> None:
    project = sample_project_with_sku
    sku = (await db_session.scalars(select(ProjectSKU).where(ProjectSKU.project_id == project.id))).first()
    arr = [Decimal("0")] * 43
    arr[5] = Decimal("99.5")

    await replace_sku_overrides(db_session, project.id, sku.id, arr)
    await db_session.flush()

    await db_session.refresh(sku)
    # JSONB round-trip: Decimal→float→stored as JSON number→returned as float.
    assert float(sku.copacking_rate_by_period[5]) == pytest.approx(float(Decimal("99.5")))


@pytest.mark.asyncio
async def test_replace_sku_overrides_with_none_clears(
    db_session: AsyncSession,
    sample_project_with_sku: Project,
) -> None:
    project = sample_project_with_sku
    sku = (await db_session.scalars(select(ProjectSKU).where(ProjectSKU.project_id == project.id))).first()
    # Store via service to ensure JSONB-serializable values.
    await replace_sku_overrides(db_session, project.id, sku.id, [Decimal("1")] * 43)
    await db_session.flush()

    await replace_sku_overrides(db_session, project.id, sku.id, None)
    await db_session.flush()
    await db_session.refresh(sku)

    assert sku.copacking_rate_by_period is None


@pytest.mark.asyncio
async def test_list_channel_overrides_returns_all_none(
    db_session: AsyncSession,
    sample_project_with_channel: Project,
) -> None:
    project = sample_project_with_channel
    sku = (await db_session.scalars(select(ProjectSKU).where(ProjectSKU.project_id == project.id))).first()
    ch = (await db_session.scalars(
        select(ProjectSKUChannel).where(ProjectSKUChannel.project_sku_id == sku.id)
    )).first()

    result = await list_overrides_by_channel(db_session, project.id, sku.id, ch.id)
    assert result.logistics_cost_per_kg_by_period is None
    assert result.ca_m_rate_by_period is None
    assert result.marketing_rate_by_period is None


@pytest.mark.asyncio
async def test_replace_channel_overrides_atomic_three_fields(
    db_session: AsyncSession,
    sample_project_with_channel: Project,
) -> None:
    project = sample_project_with_channel
    sku = (await db_session.scalars(select(ProjectSKU).where(ProjectSKU.project_id == project.id))).first()
    ch = (await db_session.scalars(
        select(ProjectSKUChannel).where(ProjectSKUChannel.project_sku_id == sku.id)
    )).first()
    log_arr = [Decimal("10")] * 43
    ca_m_arr = [Decimal("0.05")] * 43

    await replace_channel_overrides(
        db_session,
        project.id, sku.id, ch.id,
        logistics_cost_per_kg_by_period=log_arr,
        ca_m_rate_by_period=ca_m_arr,
        marketing_rate_by_period=None,
    )
    await db_session.flush()
    await db_session.refresh(ch)

    # JSONB round-trip: Decimal→float→stored as JSON number→returned as float.
    assert float(ch.logistics_cost_per_kg_by_period[0]) == pytest.approx(float(Decimal("10")))
    assert float(ch.ca_m_rate_by_period[0]) == pytest.approx(float(Decimal("0.05")))
    assert ch.marketing_rate_by_period is None


@pytest.mark.asyncio
async def test_replace_sku_overrides_rejects_wrong_length(
    db_session: AsyncSession,
    sample_project_with_sku: Project,
) -> None:
    project = sample_project_with_sku
    sku = (await db_session.scalars(select(ProjectSKU).where(ProjectSKU.project_id == project.id))).first()

    with pytest.raises(ValueError):
        await replace_sku_overrides(db_session, project.id, sku.id, [Decimal("1")] * 42)
