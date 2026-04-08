"""Security utilities: bcrypt password hashing + JWT encode/decode.

Используется auth endpoints (app/api/auth.py) и dependency get_current_user
(app/api/deps.py).
"""
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

# bcrypt с автоматической миграцией старых хешей при verify
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ============================================================
# Passwords
# ============================================================


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ============================================================
# JWT
# ============================================================


def _create_token(
    subject: str | int,
    token_type: str,
    expires_delta: timedelta,
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": now,
        "exp": now + expires_delta,
        "type": token_type,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(
    subject: str | int,
    expires_delta: timedelta | None = None,
) -> str:
    return _create_token(
        subject,
        token_type="access",
        expires_delta=expires_delta
        or timedelta(minutes=settings.jwt_access_token_expire_minutes),
    )


def create_refresh_token(
    subject: str | int,
    expires_delta: timedelta | None = None,
) -> str:
    return _create_token(
        subject,
        token_type="refresh",
        expires_delta=expires_delta
        or timedelta(days=settings.jwt_refresh_token_expire_days),
    )


def decode_token(token: str) -> dict[str, Any]:
    """Декодирует JWT и проверяет подпись + срок действия.

    Поднимает jose.JWTError при невалидной подписи, истёкшем сроке,
    повреждённом payload.
    """
    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
