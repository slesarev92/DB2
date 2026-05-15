"""C #14 _resolve_period_value helper unit tests."""
from decimal import Decimal

from app.services.calculation_service import _resolve_period_value


def test_returns_scalar_when_by_period_is_none() -> None:
    assert _resolve_period_value(None, Decimal("5"), 0) == Decimal("5")


def test_returns_scalar_when_element_is_none() -> None:
    arr: list[Decimal | None] = [None] * 43
    assert _resolve_period_value(arr, Decimal("5"), 10) == Decimal("5")


def test_returns_override_when_element_present() -> None:
    arr: list[Decimal | None] = [None] * 43
    arr[10] = Decimal("99")
    assert _resolve_period_value(arr, Decimal("5"), 10) == Decimal("99")


def test_decimal_string_in_jsonb_converted_to_decimal() -> None:
    arr: list = [None] * 43
    arr[10] = "99.5"  # как читается из JSONB
    result = _resolve_period_value(arr, Decimal("5"), 10)
    assert result == Decimal("99.5")


def test_float_from_asyncpg_jsonb_converted_correctly() -> None:
    """asyncpg deserializes JSONB number → Python float (real-world path)."""
    arr: list = [None] * 43
    arr[10] = 12.5
    result = _resolve_period_value(arr, Decimal("5"), 10)
    assert result == Decimal("12.5")
