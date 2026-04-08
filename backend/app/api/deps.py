"""Общие FastAPI dependencies для API роутов."""
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db import get_db
from app.models import User
from app.services.user_service import get_user_by_id

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# Используется во всех защищённых endpoint'ах: 401 если токен невалиден.
_credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Декодирует JWT, достаёт пользователя из БД.

    Поднимает 401 если: токен невалиден / истёк / тип не access /
    sub не int / пользователь не найден.
    """
    try:
        payload = decode_token(token)
    except JWTError as exc:
        raise _credentials_exception from exc

    if payload.get("type") != "access":
        raise _credentials_exception

    sub = payload.get("sub")
    if sub is None:
        raise _credentials_exception
    try:
        user_id = int(sub)
    except (TypeError, ValueError) as exc:
        raise _credentials_exception from exc

    user = await get_user_by_id(session, user_id)
    if user is None:
        raise _credentials_exception
    return user
