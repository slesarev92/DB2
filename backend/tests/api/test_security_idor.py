"""Regression tests for S-01 IDOR fix.

Убеждаются что пользователь не может читать / редактировать / удалять
проекты другого пользователя. Тест-кейс из SECURITY_AUDIT_2026-04-14.md.

Важно: `test_user` fixture в conftest имеет роль ADMIN (для тестов
бизнес-логики). Здесь мы создаём **двух** ANALYST пользователей и
явно задаём их credentials.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models import Project, User, UserRole


@pytest_asyncio.fixture
async def analyst_a(db_session: AsyncSession) -> User:
    """Analyst пользователь A — создаёт проект, owner."""
    user = User(
        email="analyst-a@example.com",
        hashed_password=hash_password("passA123"),
        role=UserRole.ANALYST,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def analyst_b(db_session: AsyncSession) -> User:
    """Analyst пользователь B — пытается получить проект A."""
    user = User(
        email="analyst-b@example.com",
        hashed_password=hash_password("passB123"),
        role=UserRole.ANALYST,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def project_of_a(
    db_session: AsyncSession, analyst_a: User
) -> Project:
    """Проект принадлежащий analyst_a."""
    project = Project(
        name="Secret project A",
        created_by=analyst_a.id,
        start_date=date(2026, 1, 1),
        horizon_years=10,
        wacc=Decimal("0.19"),
        vat_rate=Decimal("0.20"),
        tax_rate=Decimal("0.20"),
        wc_rate=Decimal("0.12"),
    )
    db_session.add(project)
    await db_session.flush()
    await db_session.refresh(project)
    return project


def _auth_headers(user: User) -> dict[str, str]:
    """Bearer-токен для запросов от имени user."""
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


# ============================================================
# Тесты: analyst_b НЕ должен видеть / менять / удалять проект analyst_a
# ============================================================


async def test_get_project_of_other_user_returns_404(
    client: AsyncClient,
    analyst_b: User,
    project_of_a: Project,
) -> None:
    """GET /api/projects/{id} чужого проекта возвращает 404 (не 200/403)."""
    resp = await client.get(
        f"/api/projects/{project_of_a.id}",
        headers=_auth_headers(analyst_b),
    )
    assert resp.status_code == 404, (
        f"Expected 404, got {resp.status_code}: {resp.text}"
    )
    # 404 без раскрытия существования проекта
    assert "Secret project A" not in resp.text


async def test_patch_project_of_other_user_returns_404(
    client: AsyncClient,
    analyst_b: User,
    project_of_a: Project,
) -> None:
    """PATCH /api/projects/{id} чужого проекта возвращает 404."""
    resp = await client.patch(
        f"/api/projects/{project_of_a.id}",
        json={"name": "Hijacked by B"},
        headers=_auth_headers(analyst_b),
    )
    assert resp.status_code == 404


async def test_delete_project_of_other_user_returns_404(
    client: AsyncClient,
    analyst_b: User,
    project_of_a: Project,
) -> None:
    """DELETE /api/projects/{id} чужого проекта возвращает 404."""
    resp = await client.delete(
        f"/api/projects/{project_of_a.id}",
        headers=_auth_headers(analyst_b),
    )
    assert resp.status_code == 404


async def test_recalculate_project_of_other_user_returns_404(
    client: AsyncClient,
    analyst_b: User,
    project_of_a: Project,
) -> None:
    """POST /api/projects/{id}/recalculate чужого — 404."""
    resp = await client.post(
        f"/api/projects/{project_of_a.id}/recalculate",
        headers=_auth_headers(analyst_b),
    )
    assert resp.status_code == 404


async def test_list_projects_does_not_return_other_user_projects(
    client: AsyncClient,
    analyst_b: User,
    project_of_a: Project,
) -> None:
    """GET /api/projects от user-B не возвращает проекты user-A."""
    resp = await client.get(
        "/api/projects",
        headers=_auth_headers(analyst_b),
    )
    assert resp.status_code == 200
    projects = resp.json()
    project_ids = [p["id"] for p in projects]
    assert project_of_a.id not in project_ids


# ============================================================
# Тесты: analyst_a МОЖЕТ видеть / менять свой проект
# ============================================================


async def test_owner_can_access_own_project(
    client: AsyncClient,
    analyst_a: User,
    project_of_a: Project,
) -> None:
    """Owner видит свой проект через GET."""
    resp = await client.get(
        f"/api/projects/{project_of_a.id}",
        headers=_auth_headers(analyst_a),
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Secret project A"


# ============================================================
# Тесты: admin видит все проекты (даже не свои)
# ============================================================


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    user = User(
        email="admin-audit@example.com",
        hashed_password=hash_password("adminPass"),
        role=UserRole.ADMIN,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


async def test_admin_can_access_other_user_project(
    client: AsyncClient,
    admin_user: User,
    project_of_a: Project,
) -> None:
    """Admin видит чужие проекты (sysadmin access pattern)."""
    resp = await client.get(
        f"/api/projects/{project_of_a.id}",
        headers=_auth_headers(admin_user),
    )
    assert resp.status_code == 200
