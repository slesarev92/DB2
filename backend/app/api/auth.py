"""Auth endpoints: login, refresh, me."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.rate_limit import limiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.db import get_db
from app.models import User
from app.schemas.auth import AccessToken, RefreshRequest, Token
from app.schemas.user import UserRead
from app.services.user_service import authenticate_user, get_user_by_id

router = APIRouter(prefix="/api/auth", tags=["auth"])


_invalid_credentials = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Incorrect email or password",
    headers={"WWW-Authenticate": "Bearer"},
)
_invalid_refresh = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid refresh token",
    headers={"WWW-Authenticate": "Bearer"},
)


@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
async def login(
    request: Request,  # noqa: ARG001 — slowapi key_func читает request.client
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Token:
    """OAuth2 password flow: form data username (email) + password → JWT пара.

    S-04 rate limit: 10/min per IP — защита от brute-force. При NAT 10 юзеров
    с одного IP разделяют лимит; для enterprise-доменов этого достаточно
    (реальные пользователи не логинятся чаще 1 раза в минуту). Превышение
    возвращает 429 с заголовком Retry-After.
    """
    user = await authenticate_user(session, form_data.username, form_data.password)
    if user is None:
        raise _invalid_credentials

    return Token(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=AccessToken)
async def refresh(
    body: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AccessToken:
    """Принимает refresh token, возвращает новый access token."""
    try:
        payload = decode_token(body.refresh_token)
    except JWTError as exc:
        raise _invalid_refresh from exc

    if payload.get("type") != "refresh":
        raise _invalid_refresh

    sub = payload.get("sub")
    if sub is None:
        raise _invalid_refresh
    try:
        user_id = int(sub)
    except (TypeError, ValueError) as exc:
        raise _invalid_refresh from exc

    user = await get_user_by_id(session, user_id)
    if user is None:
        raise _invalid_refresh

    return AccessToken(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserRead)
async def me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Возвращает информацию о текущем пользователе по access token."""
    return current_user
