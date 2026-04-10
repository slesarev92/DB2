"""Тесты B-12: AKB distribution plan CRUD."""
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel


# ============================================================
# Helpers
# ============================================================

PROJECT_BODY = {
    "name": "AKB test project",
    "start_date": "2025-01-01",
}


async def _create_project(client: AsyncClient) -> int:
    resp = await client.post("/api/projects", json=PROJECT_BODY)
    assert resp.status_code == 201
    return resp.json()["id"]


async def _get_channel_id(db_session: AsyncSession, code: str) -> int:
    channel = await db_session.scalar(
        select(Channel).where(Channel.code == code)
    )
    assert channel is not None, f"Channel {code} not seeded"
    return channel.id


# ============================================================
# CRUD
# ============================================================


async def test_create_akb_entry(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    project_id = await _create_project(auth_client)
    channel_id = await _get_channel_id(db_session, "HM")

    resp = await auth_client.post(
        f"/api/projects/{project_id}/akb",
        json={
            "channel_id": channel_id,
            "universe_outlets": 822,
            "target_outlets": 500,
            "coverage_pct": "0.608",
            "weighted_distribution": "0.75",
            "notes": "Phase 1 coverage",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["project_id"] == project_id
    assert data["channel_id"] == channel_id
    assert data["universe_outlets"] == 822
    assert data["target_outlets"] == 500
    assert Decimal(data["coverage_pct"]) == Decimal("0.608")
    assert data["channel"]["code"] == "HM"


async def test_list_akb_entries(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    project_id = await _create_project(auth_client)
    hm_id = await _get_channel_id(db_session, "HM")
    sm_id = await _get_channel_id(db_session, "SM")

    await auth_client.post(
        f"/api/projects/{project_id}/akb",
        json={"channel_id": hm_id, "universe_outlets": 822},
    )
    await auth_client.post(
        f"/api/projects/{project_id}/akb",
        json={"channel_id": sm_id, "universe_outlets": 5500},
    )

    resp = await auth_client.get(f"/api/projects/{project_id}/akb")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    codes = {e["channel"]["code"] for e in data}
    assert codes == {"HM", "SM"}


async def test_get_akb_entry(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    project_id = await _create_project(auth_client)
    channel_id = await _get_channel_id(db_session, "TT")

    create_resp = await auth_client.post(
        f"/api/projects/{project_id}/akb",
        json={"channel_id": channel_id, "target_outlets": 10000},
    )
    akb_id = create_resp.json()["id"]

    resp = await auth_client.get(f"/api/projects/{project_id}/akb/{akb_id}")
    assert resp.status_code == 200
    assert resp.json()["target_outlets"] == 10000
    assert resp.json()["channel"]["code"] == "TT"


async def test_update_akb_entry(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    project_id = await _create_project(auth_client)
    channel_id = await _get_channel_id(db_session, "HM")

    create_resp = await auth_client.post(
        f"/api/projects/{project_id}/akb",
        json={"channel_id": channel_id, "target_outlets": 300},
    )
    akb_id = create_resp.json()["id"]

    resp = await auth_client.patch(
        f"/api/projects/{project_id}/akb/{akb_id}",
        json={"target_outlets": 600, "notes": "Updated target"},
    )
    assert resp.status_code == 200
    assert resp.json()["target_outlets"] == 600
    assert resp.json()["notes"] == "Updated target"


async def test_delete_akb_entry(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    project_id = await _create_project(auth_client)
    channel_id = await _get_channel_id(db_session, "SM")

    create_resp = await auth_client.post(
        f"/api/projects/{project_id}/akb",
        json={"channel_id": channel_id},
    )
    akb_id = create_resp.json()["id"]

    resp = await auth_client.delete(
        f"/api/projects/{project_id}/akb/{akb_id}"
    )
    assert resp.status_code == 204

    get_resp = await auth_client.get(
        f"/api/projects/{project_id}/akb/{akb_id}"
    )
    assert get_resp.status_code == 404


async def test_akb_not_found(auth_client: AsyncClient) -> None:
    project_id = await _create_project(auth_client)
    resp = await auth_client.get(f"/api/projects/{project_id}/akb/999999")
    assert resp.status_code == 404


async def test_akb_unauthorized(client: AsyncClient) -> None:
    resp = await client.get("/api/projects/1/akb")
    assert resp.status_code == 401
