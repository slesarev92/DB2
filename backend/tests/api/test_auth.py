"""Auth endpoints tests (задача 1.1).

Покрывает критерии готовности из IMPLEMENTATION_PLAN:
  - Логин с верными данными → 200 + tokens
  - Логин с неверными → 401
  - Запрос без токена → 401
  - Запрос с истёкшим токеном → 401
+ refresh flow и edge cases (8 кейсов всего).
"""
from datetime import timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models import User, UserRole

# ============================================================
# Helper
# ============================================================

DEFAULT_EMAIL = "test@example.com"
DEFAULT_PASSWORD = "testpass123"


async def _make_user(
    session: AsyncSession,
    email: str = DEFAULT_EMAIL,
    password: str = DEFAULT_PASSWORD,
    role: UserRole = UserRole.ANALYST,
) -> User:
    user = User(
        email=email,
        hashed_password=hash_password(password),
        role=role,
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


# ============================================================
# 1. Login success → 200 + access + refresh
# ============================================================


async def test_login_success_returns_tokens(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _make_user(db_session)

    resp = await client.post(
        "/api/auth/login",
        data={"username": DEFAULT_EMAIL, "password": DEFAULT_PASSWORD},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["token_type"] == "bearer"
    assert isinstance(data["access_token"], str) and len(data["access_token"]) > 20
    assert isinstance(data["refresh_token"], str) and len(data["refresh_token"]) > 20


# ============================================================
# 2. Login wrong password → 401
# ============================================================


async def test_login_wrong_password_returns_401(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _make_user(db_session)

    resp = await client.post(
        "/api/auth/login",
        data={"username": DEFAULT_EMAIL, "password": "wrong-password"},
    )

    assert resp.status_code == 401
    assert "Incorrect" in resp.json()["detail"]


# ============================================================
# 3. Login non-existent user → 401
# ============================================================


async def test_login_unknown_user_returns_401(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/auth/login",
        data={"username": "nobody@example.com", "password": "irrelevant"},
    )

    assert resp.status_code == 401


# ============================================================
# 4. /me without token → 401
# ============================================================


async def test_me_without_token_returns_401(client: AsyncClient) -> None:
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


# ============================================================
# 5. /me with valid token → 200 + user data
# ============================================================


async def test_me_with_valid_token_returns_user(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _make_user(db_session)
    token = create_access_token(user.id)

    resp = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == user.id
    assert data["email"] == DEFAULT_EMAIL
    assert data["role"] == "analyst"  # lowercase из varchar_enum


# ============================================================
# 6. /me with expired token → 401
# ============================================================


async def test_me_with_expired_token_returns_401(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _make_user(db_session)
    token = create_access_token(user.id, expires_delta=timedelta(seconds=-10))

    resp = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 401


# ============================================================
# 7. /me with garbage token → 401
# ============================================================


async def test_me_with_garbage_token_returns_401(client: AsyncClient) -> None:
    resp = await client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer not.a.real.jwt"},
    )
    assert resp.status_code == 401


# ============================================================
# 8. Refresh flow: login → use refresh → call /me with new access
# ============================================================


async def test_refresh_token_yields_working_access(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _make_user(db_session)

    login_resp = await client.post(
        "/api/auth/login",
        data={"username": DEFAULT_EMAIL, "password": DEFAULT_PASSWORD},
    )
    refresh_token = login_resp.json()["refresh_token"]

    refresh_resp = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_resp.status_code == 200
    new_access = refresh_resp.json()["access_token"]
    assert isinstance(new_access, str) and len(new_access) > 20

    me_resp = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {new_access}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == DEFAULT_EMAIL
