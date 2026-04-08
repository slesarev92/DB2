"""Seed справочных данных: periods, channels, ref_inflation, ref_seasonality.

Запуск:
    docker compose -f infra/docker-compose.dev.yml exec backend \
        python -m scripts.seed_reference_data

Скрипт идемпотентен: при повторном запуске пропускает уже существующие записи
(проверка по уникальным колонкам profile_name / code / period_number).

Источник данных: лист `DASH MENU` модели `PASSPORT_MODEL_GORJI_2025-09-05.xlsx`.
Все значения захардкожены, чтобы скрипт не зависел от наличия xlsx
на машине разработчика или в CI.

При расхождении с актуальной Excel-моделью — обновлять значения в этом файле
вручную. См. ADR-CE-01: Excel-модель — источник истины.
"""
import asyncio
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session_maker
from app.models import (
    Channel,
    Period,
    PeriodType,
    RefInflation,
    RefSeasonality,
)

# ============================================================
# Channels — 25 каналов из GORJI DASH MENU (B4..B28, C = ОКБ)
# ============================================================

CHANNELS_DATA: list[dict[str, Any]] = [
    {"code": "HM", "name": "Гипермаркеты", "universe_outlets": 822},
    {"code": "SM", "name": "Супермаркеты", "universe_outlets": 34_083},
    {"code": "MM", "name": "Минимаркеты", "universe_outlets": 58_080},
    {"code": "TT", "name": "Традиционная розница", "universe_outlets": 91_444},
    {"code": "Beauty", "name": "Beauty (магазины красоты)", "universe_outlets": 600_000},
    {"code": "Beauty-NS", "name": "Beauty Non-Standard", "universe_outlets": 100},
    {"code": "DS_Pyaterochka", "name": "Пятерочка (Discounter)", "universe_outlets": 18_200},
    {"code": "DS_Magnit", "name": "Магнит (Discounter)", "universe_outlets": 13_528},
    {"code": "HDS", "name": "Hard Discounter", "universe_outlets": 10_003},
    {"code": "ALCO", "name": "Алкомаркеты", "universe_outlets": 18_500},
    {"code": "E-COM_OZ", "name": "E-Commerce Ozon", "universe_outlets": 1},
    {"code": "E-COM_WB", "name": "E-Commerce Wildberries", "universe_outlets": 1},
    {"code": "E-COM_YA", "name": "E-Commerce Яндекс Маркет", "universe_outlets": 1},
    {"code": "E-COM_SBER", "name": "E-Commerce Сбер Маркет", "universe_outlets": 1},
    {"code": "E_COM_E-grocery", "name": "E-Grocery (агрегатор)", "universe_outlets": 10},
    {"code": "HORECA_АЗС", "name": "HoReCa: АЗС", "universe_outlets": 10_000},
    {"code": "HORECA_СПОРТ", "name": "HoReCa: спортивные объекты", "universe_outlets": 355_000},
    {"code": "HORECA_HOTEL", "name": "HoReCa: отели", "universe_outlets": 30_000},
    {"code": "HORECA_Cafe&Rest", "name": "HoReCa: кафе и рестораны", "universe_outlets": 176_000},
    {"code": "Vkusno I tochka", "name": "Вкусно и точка", "universe_outlets": 900},
    {"code": "Burger king", "name": "Burger King", "universe_outlets": 817},
    {"code": "Rostics", "name": "Rostic's", "universe_outlets": 1_150},
    {"code": "Do-Do_pizza", "name": "Додо Пицца", "universe_outlets": 817},
    {"code": "VEND_machine", "name": "Вендинговые автоматы", "universe_outlets": 51_450},
    {"code": "E-COM_OZ_Fresh", "name": "E-Commerce Ozon Fresh", "universe_outlets": 1},
]


# ============================================================
# Inflation profiles — 15 профилей из DASH MENU (E5..E19, F..Q + T..Z)
# ============================================================
#
# Структура `month_coefficients`:
#   "monthly_deltas": список из 12 значений по календарным месяцам янв..дек.
#                     Применяется к shelf price помесячно в M1..M36.
#   "yearly_growth":  список из 7 значений Y4..Y10 — кумулятивный годовой
#                     рост, применяется в годах Y4..Y10.
#
# Эта структура отражает Excel: помесячные ступеньки в первые 3 года плюс
# выровненный годовой рост в Y4..Y10. Расчётное ядро (Фаза 2) интерпретирует
# эти поля при применении инфляции к ценам.

INFLATION_PROFILES: list[dict[str, Any]] = [
    {
        "profile_name": "No_Inflation",
        "month_coefficients": {
            "monthly_deltas": [0.0] * 12,
            "yearly_growth": [0.0] * 7,
        },
    },
    # --- Апрель + N% ---
    {
        "profile_name": "Апрель +4%",
        "month_coefficients": {
            "monthly_deltas": [0, 0, 0, 0.04, 0, 0, 0, 0, 0, 0, 0, 0],
            "yearly_growth": [0.03] * 7,
        },
    },
    {
        "profile_name": "Апрель +5%",
        "month_coefficients": {
            "monthly_deltas": [0, 0, 0, 0.05, 0, 0, 0, 0, 0, 0, 0, 0],
            "yearly_growth": [0.0375] * 7,
        },
    },
    {
        "profile_name": "Апрель +6%",
        "month_coefficients": {
            "monthly_deltas": [0, 0, 0, 0.06, 0, 0, 0, 0, 0, 0, 0, 0],
            "yearly_growth": [0.045] * 7,
        },
    },
    {
        "profile_name": "Апрель +7%",
        "month_coefficients": {
            "monthly_deltas": [0, 0, 0, 0.07, 0, 0, 0, 0, 0, 0, 0, 0],
            "yearly_growth": [0.0525] * 7,
        },
    },
    # --- Октябрь + N% ---
    {
        "profile_name": "Октябрь +4%",
        "month_coefficients": {
            "monthly_deltas": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0.04, 0, 0],
            "yearly_growth": [0.01] * 7,
        },
    },
    {
        "profile_name": "Октябрь +5%",
        "month_coefficients": {
            "monthly_deltas": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0.05, 0, 0],
            "yearly_growth": [0.0125] * 7,
        },
    },
    {
        "profile_name": "Октябрь +6%",
        "month_coefficients": {
            "monthly_deltas": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0.06, 0, 0],
            "yearly_growth": [0.015] * 7,
        },
    },
    {
        "profile_name": "Октябрь +7%",
        "month_coefficients": {
            "monthly_deltas": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0.07, 0, 0],
            "yearly_growth": [0.0175] * 7,
        },
    },
    # --- Апрель/Октябрь + N% ---
    {
        "profile_name": "Апрель/Октябрь +4%",
        "month_coefficients": {
            "monthly_deltas": [0, 0, 0, 0.04, 0, 0, 0, 0, 0, 0.04, 0, 0],
            "yearly_growth": [0.0404] * 7,
        },
    },
    {
        "profile_name": "Апрель/Октябрь +5%",
        "month_coefficients": {
            "monthly_deltas": [0, 0, 0, 0.05, 0, 0, 0, 0, 0, 0.05, 0, 0],
            "yearly_growth": [0.050625] * 7,
        },
    },
    {
        "profile_name": "Апрель/Октябрь +6%",
        "month_coefficients": {
            "monthly_deltas": [0, 0, 0, 0.06, 0, 0, 0, 0, 0, 0.06, 0, 0],
            "yearly_growth": [0.0609] * 7,
        },
    },
    {
        "profile_name": "Апрель/Октябрь +7%",
        "month_coefficients": {
            "monthly_deltas": [0, 0, 0, 0.07, 0, 0, 0, 0, 0, 0.07, 0, 0],
            "yearly_growth": [0.071225] * 7,
        },
    },
    {
        "profile_name": "Апрель/Октябрь +8%",
        "month_coefficients": {
            "monthly_deltas": [0, 0, 0, 0.08, 0, 0, 0, 0, 0, 0.08, 0, 0],
            "yearly_growth": [0.081225] * 7,
        },
    },
    {
        "profile_name": "Апрель/Октябрь +9%",
        "month_coefficients": {
            "monthly_deltas": [0, 0, 0, 0.09, 0, 0, 0, 0, 0, 0.09, 0, 0],
            "yearly_growth": [0.091225] * 7,
        },
    },
    {
        "profile_name": "Апрель/Октябрь +10%",
        "month_coefficients": {
            "monthly_deltas": [0, 0, 0, 0.10, 0, 0, 0, 0, 0, 0.10, 0, 0],
            "yearly_growth": [0.101225] * 7,
        },
    },
]


# ============================================================
# Seasonality profiles — 6 профилей категорий из DASH MENU (AB4..AB9)
# ============================================================
#
# Коэффициенты сезонности по календарным месяцам янв..дек. Среднее ≈ 1.0.
# Применяется как множитель к offtake/volume в расчётном ядре.

SEASONALITY_PROFILES: list[dict[str, Any]] = [
    {
        "profile_name": "No_Seasonality",
        "month_coefficients": {"months": [1.0] * 12},
    },
    {
        # CSD = Carbonated Soft Drinks
        "profile_name": "CSD",
        "month_coefficients": {
            "months": [
                0.988042, 0.852450, 0.965162, 0.977710,
                1.105902, 1.151848, 1.236834, 1.221947,
                1.017260, 0.966450, 0.904538, 1.066262,
            ],
        },
    },
    {
        # WTR = Water
        "profile_name": "WTR",
        "month_coefficients": {
            "months": [
                0.876010, 0.796770, 0.928173, 0.992940,
                1.137069, 1.239147, 1.369261, 1.346636,
                1.020989, 0.933432, 0.859968, 0.894976,
            ],
        },
    },
    {
        # EN = Energy drinks
        "profile_name": "EN",
        "month_coefficients": {
            "months": [
                0.914371, 0.848587, 1.015288, 1.081608,
                1.210457, 1.282175, 1.385423, 1.440584,
                1.295077, 1.259163, 1.140035, 1.147342,
            ],
        },
    },
    {
        # TEA — копия EN в Excel-модели (помечено как заглушка)
        "profile_name": "TEA",
        "month_coefficients": {
            "months": [
                0.914371, 0.848587, 1.015288, 1.081608,
                1.210457, 1.282175, 1.385423, 1.440584,
                1.295077, 1.259163, 1.140035, 1.147342,
            ],
        },
    },
    {
        # JUI = Juice — копия EN в Excel-модели (помечено как заглушка)
        "profile_name": "JUI",
        "month_coefficients": {
            "months": [
                0.914371, 0.848587, 1.015288, 1.081608,
                1.210457, 1.282175, 1.385423, 1.440584,
                1.295077, 1.259163, 1.140035, 1.147342,
            ],
        },
    },
]


# ============================================================
# Periods — 43 строки: M1..M36 (помесячно) + Y4..Y10 (годами)
# ============================================================


def generate_periods() -> list[dict[str, Any]]:
    """Генерирует 43 строки справочника периодов.

    Колонки start_date / end_date — плейсхолдеры от 2025-01-01. Period —
    абстрактный справочник: реальные даты конкретного проекта вычисляются
    из project.start_date в расчётном ядре. Эти колонки нужны только для
    NOT NULL constraint в текущей схеме (см. backend/app/models/entities.py
    Period). При желании можно сделать nullable в следующей миграции.
    """
    base_year = 2025
    periods: list[dict[str, Any]] = []

    # M1..M36 — помесячно за первые 3 года.
    for i in range(36):
        period_number = i + 1
        model_year = (i // 12) + 1     # 1, 2, 3
        month_in_year = (i % 12) + 1   # 1..12 (январь..декабрь)
        year = base_year + (i // 12)

        if month_in_year == 12:
            end = date(year, 12, 31)
        else:
            end = date(year, month_in_year + 1, 1) - timedelta(days=1)

        periods.append(
            {
                "type": PeriodType.MONTHLY,
                "period_number": period_number,
                "model_year": model_year,
                "month_num": month_in_year,
                "start_date": date(year, month_in_year, 1),
                "end_date": end,
            }
        )

    # Y4..Y10 — годовые периоды.
    for y in range(4, 11):  # 4, 5, 6, 7, 8, 9, 10
        year = base_year + y - 1
        periods.append(
            {
                "type": PeriodType.ANNUAL,
                "period_number": 36 + (y - 3),  # 37..43
                "model_year": y,
                "month_num": None,
                "start_date": date(year, 1, 1),
                "end_date": date(year, 12, 31),
            }
        )

    return periods


# ============================================================
# Seed functions
# ============================================================


async def seed_periods(session: AsyncSession) -> tuple[int, int]:
    """Возвращает (existing, inserted)."""
    existing = await session.scalar(
        select(func.count()).select_from(Period)
    )
    if existing == 43:
        return existing, 0
    if existing not in (0, 43):
        raise RuntimeError(
            f"Periods table has {existing} rows (expected 0 или 43). "
            "Не уверен в состоянии таблицы — очистите вручную."
        )

    for row in generate_periods():
        session.add(Period(**row))
    await session.flush()
    return 0, 43


async def seed_channels(session: AsyncSession) -> tuple[int, int]:
    existing_codes = set(
        (await session.scalars(select(Channel.code))).all()
    )
    inserted = 0
    for ch in CHANNELS_DATA:
        if ch["code"] in existing_codes:
            continue
        session.add(Channel(**ch))
        inserted += 1
    await session.flush()
    return len(existing_codes), inserted


async def seed_inflation(session: AsyncSession) -> tuple[int, int]:
    existing_names = set(
        (await session.scalars(select(RefInflation.profile_name))).all()
    )
    inserted = 0
    for prof in INFLATION_PROFILES:
        if prof["profile_name"] in existing_names:
            continue
        session.add(RefInflation(**prof))
        inserted += 1
    await session.flush()
    return len(existing_names), inserted


async def seed_seasonality(session: AsyncSession) -> tuple[int, int]:
    existing_names = set(
        (await session.scalars(select(RefSeasonality.profile_name))).all()
    )
    inserted = 0
    for prof in SEASONALITY_PROFILES:
        if prof["profile_name"] in existing_names:
            continue
        session.add(RefSeasonality(**prof))
        inserted += 1
    await session.flush()
    return len(existing_names), inserted


async def main() -> None:
    async with async_session_maker() as session:
        existing_p, inserted_p = await seed_periods(session)
        existing_c, inserted_c = await seed_channels(session)
        existing_i, inserted_i = await seed_inflation(session)
        existing_s, inserted_s = await seed_seasonality(session)
        await session.commit()

    print("Seed reference data complete.")
    print(f"  periods         : existing={existing_p:>3}  inserted={inserted_p:>3}  total=43")
    print(f"  channels        : existing={existing_c:>3}  inserted={inserted_c:>3}  total={len(CHANNELS_DATA)}")
    print(f"  ref_inflation   : existing={existing_i:>3}  inserted={inserted_i:>3}  total={len(INFLATION_PROFILES)}")
    print(f"  ref_seasonality : existing={existing_s:>3}  inserted={inserted_s:>3}  total={len(SEASONALITY_PROFILES)}")


if __name__ == "__main__":
    asyncio.run(main())
