"""Pydantic-схемы для пользователя."""
from pydantic import BaseModel, ConfigDict

from app.models import UserRole


class UserBase(BaseModel):
    email: str
    role: UserRole = UserRole.ANALYST


class UserCreate(UserBase):
    """Используется при создании пользователя (содержит plaintext пароль)."""

    password: str


class UserRead(UserBase):
    """Возвращается клиенту: без пароля и хеша."""

    model_config = ConfigDict(from_attributes=True)

    id: int
