"""Pydantic схемы для read-only справочников.

В отличие от Channel/Period (свои файлы), мелкие справочники
объединены в один модуль `reference.py` чтобы не плодить файлы.
"""
from typing import Any

from pydantic import BaseModel, ConfigDict


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
