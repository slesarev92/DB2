"""Unit-тесты для backfill-helper _resolve_group из миграции C #16.

Импорт по абсолютному пути к файлу миграции через importlib —
revision-id не статичный. Можно адаптировать под точное имя файла
после `alembic revision` (см. Step 5).
"""
import importlib.util
from pathlib import Path

import pytest

MIGRATION_FILE = next(
    Path("migrations/versions").glob("*_c16_channel_group_source_type.py")
)
spec = importlib.util.spec_from_file_location("c16_migration", MIGRATION_FILE)
mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
spec.loader.exec_module(mod)  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "code, expected",
    [
        ("HM", "HM"),
        ("SM", "SM"),
        ("MM", "MM"),
        ("TT", "TT"),
        ("Vkusno I tochka", "QSR"),
        ("Burger king", "QSR"),
        ("Rostics", "QSR"),
        ("Do-Do_pizza", "QSR"),
    ],
)
def test_resolve_group_exact_match(code: str, expected: str) -> None:
    assert mod._resolve_group(code) == expected


@pytest.mark.parametrize(
    "code, expected",
    [
        ("E-COM_OZ", "E_COM"),
        ("E-COM_WB", "E_COM"),
        ("E_COM_E-grocery", "E_COM"),
        ("E-COM_OZ_Fresh", "E_COM"),
        ("HORECA_АЗС", "HORECA"),
        ("HORECA_HOTEL", "HORECA"),
    ],
)
def test_resolve_group_prefix(code: str, expected: str) -> None:
    assert mod._resolve_group(code) == expected


@pytest.mark.parametrize(
    "code",
    ["Beauty", "Beauty-NS", "DS_Pyaterochka", "HDS", "ALCO", "VEND_machine", "UnknownCustomCode"],
)
def test_resolve_group_fallback_other(code: str) -> None:
    assert mod._resolve_group(code) == "OTHER"
