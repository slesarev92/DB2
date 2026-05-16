"""Unit-тесты для backfill-helper _resolve_group из миграции C #16.

Импорт по абсолютному пути к файлу миграции через importlib —
revision-id не статичный. Path resolved через __file__ чтобы быть
CWD-independent (на случай pytest из repo root).
"""
import importlib.util
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[2]
MIGRATION_FILE = next(
    (_BACKEND_DIR / "migrations" / "versions").glob(
        "*_c16_channel_group_source_type.py"
    )
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


def test_seed_data_matches_resolve_group() -> None:
    """Инвариант: для каждого кода в seed `channel_group` == `_resolve_group(code)`.

    Защита от рассинхрона: если кто-то добавит канал в seed с `channel_group=X`,
    но забудет добавить правило в EXACT_RULES/PREFIX_RULES — fresh DB через seed
    даст X, а existing prod после миграции даст OTHER. Тест ловит расхождение.
    """
    from scripts.seed_reference_data import CHANNELS_DATA

    mismatches = [
        (ch["code"], ch["channel_group"], mod._resolve_group(ch["code"]))
        for ch in CHANNELS_DATA
        if mod._resolve_group(ch["code"]) != ch["channel_group"]
    ]
    assert not mismatches, (
        f"Seed/migration mismatch: {mismatches}. "
        "Update EXACT_RULES/PREFIX_RULES or fix channel_group in seed."
    )
