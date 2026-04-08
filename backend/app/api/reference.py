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
from app.models import RefInflation, User
from app.schemas.reference import RefInflationRead

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
