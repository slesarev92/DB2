"""Pydantic-схемы для аутентификации (JWT)."""
from pydantic import BaseModel


class Token(BaseModel):
    """Ответ на /api/auth/login: пара access + refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessToken(BaseModel):
    """Ответ на /api/auth/refresh: только новый access token."""

    access_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Тело запроса /api/auth/refresh."""

    refresh_token: str
