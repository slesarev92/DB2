"""Read-only API для справочников.

Только GET для использования в frontend dropdown'ах.
Запись справочников — через seed (см. backend/scripts/seed_reference_data.py)
или через миграции.
"""
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db import get_db
from app.models import Period, RefInflation, RefSeasonality, User
from app.schemas.reference import (
    PeriodRead,
    RefInflationRead,
    RefSeasonalityRead,
)

router = APIRouter(prefix="/api", tags=["reference"])


@router.get("/ref-inflation", response_model=list[RefInflationRead])
async def list_ref_inflation_endpoint(
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[RefInflation]:
    """Список профилей инфляции для dropdown в форме создания проекта.

    Сортировка по profile_name (алфавит). Если профилей нет в БД —
    возвращает пустой список (frontend покажет dropdown без вариантов).
    """
    stmt = select(RefInflation).order_by(RefInflation.profile_name)
    return list((await session.scalars(stmt)).all())


@router.get("/ref-seasonality", response_model=list[RefSeasonalityRead])
async def list_ref_seasonality_endpoint(
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[RefSeasonality]:
    """Список профилей сезонности для dropdown в форме канала.

    Применяется в `s01_volume` через `seasonality_profile_id` поля
    ProjectSKUChannel. Возвращает все сидированные профили (Water,
    Energy drinks и т.д. — см. backend/scripts/seed_reference_data.py).
    """
    stmt = select(RefSeasonality).order_by(RefSeasonality.profile_name)
    return list((await session.scalars(stmt)).all())


@router.get("/periods", response_model=list[PeriodRead])
async def list_periods_endpoint(
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[Period]:
    """Справочник 43 периодов (M1..M36 + Y4..Y10) для frontend AG Grid.

    Сортировка по `period_number` (1..43). Используется в табе "Периоды"
    карточки проекта для построения column structure: monthly периоды
    показываются как M1..M36, yearly — как Y4..Y10. Период `type` нужен
    для toggle режимов отображения.
    """
    stmt = select(Period).order_by(Period.period_number)
    return list((await session.scalars(stmt)).all())
