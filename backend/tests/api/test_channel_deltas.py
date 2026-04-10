"""Тесты B-06: per-channel delta overrides.

GET/PUT /api/scenarios/{id}/channel-deltas
"""
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Channel,
    Scenario,
    ScenarioChannelDelta,
    ScenarioType,
)


# ============================================================
# Helpers
# ============================================================


SKU_BODY = {"brand": "Gorji", "name": "Delta Test SKU"}
PROJECT_BODY = {"name": "Channel deltas test", "start_date": "2025-01-01"}


async def _setup(
    auth_client: AsyncClient, db_session: AsyncSession
) -> tuple[int, int, int]:
    """Возвращает (project_id, conservative_scenario_id, psk_channel_id)."""
    from app.schemas.project_sku_channel import ProjectSKUChannelCreate
    from app.services.project_sku_channel_service import create_psk_channel

    project_id = (
        await auth_client.post("/api/projects", json=PROJECT_BODY)
    ).json()["id"]
    sku_id = (
        await auth_client.post("/api/skus", json=SKU_BODY)
    ).json()["id"]
    psk_id = (
        await auth_client.post(
            f"/api/projects/{project_id}/skus", json={"sku_id": sku_id}
        )
    ).json()["id"]

    hm = await db_session.scalar(select(Channel).where(Channel.code == "HM"))
    assert hm is not None

    psc = await create_psk_channel(
        db_session,
        psk_id,
        ProjectSKUChannelCreate(channel_id=hm.id),
        auto_fill_predict=False,
    )

    # Get conservative scenario (non-base to test deltas)
    conservative = await db_session.scalar(
        select(Scenario).where(
            Scenario.project_id == project_id,
            Scenario.type == ScenarioType.CONSERVATIVE,
        )
    )
    assert conservative is not None

    return project_id, conservative.id, psc.id


# ============================================================
# GET — empty by default
# ============================================================


async def test_get_channel_deltas_empty_by_default(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    _, scenario_id, _ = await _setup(auth_client, db_session)
    resp = await auth_client.get(
        f"/api/scenarios/{scenario_id}/channel-deltas"
    )
    assert resp.status_code == 200
    assert resp.json() == []


# ============================================================
# PUT — create overrides
# ============================================================


async def test_put_channel_deltas_creates(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    _, scenario_id, psc_id = await _setup(auth_client, db_session)

    body = {
        "items": [
            {
                "psk_channel_id": psc_id,
                "delta_nd": "-0.15",
                "delta_offtake": "-0.10",
            }
        ]
    }
    resp = await auth_client.put(
        f"/api/scenarios/{scenario_id}/channel-deltas", json=body
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["psk_channel_id"] == psc_id
    assert Decimal(data[0]["delta_nd"]) == Decimal("-0.15")

    # DB check
    rows = (
        await db_session.scalars(
            select(ScenarioChannelDelta).where(
                ScenarioChannelDelta.scenario_id == scenario_id
            )
        )
    ).all()
    assert len(list(rows)) == 1


# ============================================================
# PUT — replace (old records deleted)
# ============================================================


async def test_put_channel_deltas_replaces(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    _, scenario_id, psc_id = await _setup(auth_client, db_session)

    # First PUT
    await auth_client.put(
        f"/api/scenarios/{scenario_id}/channel-deltas",
        json={"items": [{"psk_channel_id": psc_id, "delta_nd": "-0.10"}]},
    )
    # Second PUT (different values)
    resp = await auth_client.put(
        f"/api/scenarios/{scenario_id}/channel-deltas",
        json={"items": [{"psk_channel_id": psc_id, "delta_nd": "-0.20"}]},
    )
    data = resp.json()
    assert len(data) == 1
    assert Decimal(data[0]["delta_nd"]) == Decimal("-0.20")


# ============================================================
# PUT — empty items clears all
# ============================================================


async def test_put_channel_deltas_empty_clears(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    _, scenario_id, psc_id = await _setup(auth_client, db_session)

    await auth_client.put(
        f"/api/scenarios/{scenario_id}/channel-deltas",
        json={"items": [{"psk_channel_id": psc_id, "delta_nd": "-0.10"}]},
    )
    resp = await auth_client.put(
        f"/api/scenarios/{scenario_id}/channel-deltas",
        json={"items": []},
    )
    assert resp.status_code == 200
    assert resp.json() == []


# ============================================================
# Auth required
# ============================================================


async def test_channel_deltas_unauthorized(client: AsyncClient) -> None:
    resp = await client.get("/api/scenarios/1/channel-deltas")
    assert resp.status_code == 401
