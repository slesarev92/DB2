"""C #14 Fine Tuning API endpoint tests.

Adaptations vs plan template:
- `auth_client` (pre-authed AsyncClient) instead of async_client + auth_headers.
- `client` (unauthenticated) for 401 tests.
- `project.skus` relationship NOT eager-loaded → use explicit SELECT for
  ProjectSKU and ProjectSKUChannel IDs.
- Auth dep is get_current_user (no require_project_member in this codebase).
- Router paths: /api/projects/{id}/fine-tuning/per-period/sku/{sku_id} etc.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import ProjectSKU, ProjectSKUChannel


@pytest.mark.asyncio
async def test_get_sku_overrides_returns_none_for_clean(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    sample_project_with_sku,
) -> None:
    project = sample_project_with_sku
    psk = await db_session.scalar(
        select(ProjectSKU).where(ProjectSKU.project_id == project.id)
    )
    assert psk is not None
    resp = await auth_client.get(
        f"/api/projects/{project.id}/fine-tuning/per-period/sku/{psk.id}",
    )
    assert resp.status_code == 200
    assert resp.json()["copacking_rate_by_period"] is None


@pytest.mark.asyncio
async def test_put_sku_overrides_round_trip(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    sample_project_with_sku,
) -> None:
    project = sample_project_with_sku
    psk = await db_session.scalar(
        select(ProjectSKU).where(ProjectSKU.project_id == project.id)
    )
    assert psk is not None
    arr: list[str | None] = ["0"] * 43
    arr[5] = "99.5"
    resp = await auth_client.put(
        f"/api/projects/{project.id}/fine-tuning/per-period/sku/{psk.id}",
        json={"copacking_rate_by_period": arr},
    )
    assert resp.status_code == 204

    resp = await auth_client.get(
        f"/api/projects/{project.id}/fine-tuning/per-period/sku/{psk.id}",
    )
    assert resp.status_code == 200
    assert resp.json()["copacking_rate_by_period"][5] == "99.5"


@pytest.mark.asyncio
async def test_put_sku_overrides_rejects_wrong_length(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    sample_project_with_sku,
) -> None:
    project = sample_project_with_sku
    psk = await db_session.scalar(
        select(ProjectSKU).where(ProjectSKU.project_id == project.id)
    )
    assert psk is not None
    resp = await auth_client.put(
        f"/api/projects/{project.id}/fine-tuning/per-period/sku/{psk.id}",
        json={"copacking_rate_by_period": ["1"] * 42},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_channel_overrides_partial_fields(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    sample_project_with_channel,
) -> None:
    project = sample_project_with_channel
    psk = await db_session.scalar(
        select(ProjectSKU).where(ProjectSKU.project_id == project.id)
    )
    assert psk is not None
    psc = await db_session.scalar(
        select(ProjectSKUChannel).where(ProjectSKUChannel.project_sku_id == psk.id)
    )
    assert psc is not None

    # logistics_cost_per_kg: no upper bound — absolute cost (₽/kg)
    log_arr: list[str | None] = ["10"] * 43

    resp = await auth_client.put(
        f"/api/projects/{project.id}/fine-tuning/per-period/channel/{psc.id}",
        json={
            "logistics_cost_per_kg_by_period": log_arr,
            "ca_m_rate_by_period": None,
            "marketing_rate_by_period": None,
        },
    )
    assert resp.status_code == 204

    resp = await auth_client.get(
        f"/api/projects/{project.id}/fine-tuning/per-period/channel/{psc.id}",
    )
    assert resp.status_code == 200
    body = resp.json()
    # Service stores as float in JSONB: Decimal("10") → 10.0 → "10.0" in JSON.
    # Compare as Decimal to be robust to "10" vs "10.0" representation.
    from decimal import Decimal

    assert Decimal(body["logistics_cost_per_kg_by_period"][0]) == Decimal("10")
    assert body["ca_m_rate_by_period"] is None


@pytest.mark.asyncio
async def test_get_sku_overrides_unauthorized(
    client: AsyncClient,
    db_session: AsyncSession,
    sample_project_with_sku,
) -> None:
    project = sample_project_with_sku
    psk = await db_session.scalar(
        select(ProjectSKU).where(ProjectSKU.project_id == project.id)
    )
    assert psk is not None
    resp = await client.get(
        f"/api/projects/{project.id}/fine-tuning/per-period/sku/{psk.id}",
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_get_sku_overrides_not_found(
    auth_client: AsyncClient,
    sample_project_with_sku,
) -> None:
    project = sample_project_with_sku
    resp = await auth_client.get(
        f"/api/projects/{project.id}/fine-tuning/per-period/sku/999999",
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_channel_overrides_cross_project_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    sample_project_with_channel,
) -> None:
    """IDOR fix: ANALYST не-owner запрашивает channel чужого проекта → 404
    (одинаковый response с 'channel does not exist', нет timing-side-channel
    утечки о существовании id в чужом проекте).
    """
    from app.core.security import create_access_token, hash_password
    from app.models import User, UserRole

    project = sample_project_with_channel
    psk = await db_session.scalar(
        select(ProjectSKU).where(ProjectSKU.project_id == project.id)
    )
    assert psk is not None
    psc = await db_session.scalar(
        select(ProjectSKUChannel).where(ProjectSKUChannel.project_sku_id == psk.id)
    )
    assert psc is not None

    intruder = User(
        email="intruder-c14@example.com",
        hashed_password=hash_password("pass"),
        role=UserRole.ANALYST,
    )
    db_session.add(intruder)
    await db_session.flush()

    headers = {"Authorization": f"Bearer {create_access_token(intruder.id)}"}
    resp = await client.get(
        f"/api/projects/{project.id}/fine-tuning/per-period/channel/{psc.id}",
        headers=headers,
    )
    # 404 — IDOR fix: project gate ловит сначала, channel id никогда не
    # доходит до проверки в endpoint'е.
    assert resp.status_code == 404
