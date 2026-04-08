"""Pydantic схемы для read-only справочников.

В отличие от Channel/Period (свои файлы), мелкие справочники
объединены в один модуль `reference.py` чтобы не плодить файлы.
"""
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models import PeriodType


class RefInflationRead(BaseModel):
    """Профиль инфляции (Excel: DASH C2, Predikt Inflation).

    `month_coefficients` — JSONB структура, содержит:
        monthly_deltas: list[float] длиной 12 (Jan..Dec, % ступенек)
        yearly_growth: list[float] длиной 7 (Y4..Y10, годовой рост)
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_name: str
    month_coefficients: dict[str, Any]


class RefSeasonalityRead(BaseModel):
    """Профиль сезонности (Water, Energy drinks и т.д.).

    `month_coefficients` — JSONB список из 12 чисел по календарным месяцам
    январь..декабрь. Сумма обычно нормализована к 12.0 (среднее = 1.0).
    Применяется в `s01_volume` для monthly периодов M1..M36.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_name: str
    month_coefficients: dict[str, Any]


class PeriodRead(BaseModel):
    """Справочник периодов: 36 monthly (M1..M36) + 7 yearly (Y4..Y10) = 43.

    Используется frontend'ом для построения column structure в AG Grid
    таблице периодов (задача 4.1).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    type: PeriodType
    period_number: int  # 1..43, глобальный sequential
    model_year: int     # 1..10
    month_num: int | None  # 1..12 для monthly, None для yearly
    start_date: date
    end_date: date
