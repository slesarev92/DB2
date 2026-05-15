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
