"""Тесты B-12: AKB distribution plan CRUD.

C #17: тесты GET /api/projects/{id}/akb/auto — автоматический расчёт АКБ.
"""
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


# ============================================================
# C #17: AKB auto-compute tests
# ============================================================

_auto_ch_counter = {"n": 0}


async def _create_project_for_auto(client: AsyncClient) -> int:
    """Создаёт проект для auto-тестов, возвращает project_id."""
    resp = await client.post("/api/projects", json={"name": "AKB auto test project", "start_date": "2025-01-01"})
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_psk_for_auto(client: AsyncClient, project_id: int) -> int:
    """Создаёт SKU + ProjectSKU под заданный проект, возвращает psk_id."""
    sku_resp = await client.post(
        "/api/skus",
        json={"brand": "AutoBrand", "name": "AutoSKU"},
    )
    assert sku_resp.status_code == 201
    sku_id = sku_resp.json()["id"]

    psk_resp = await client.post(
        f"/api/projects/{project_id}/skus",
        json={"sku_id": sku_id},
    )
    assert psk_resp.status_code == 201
    return psk_resp.json()["id"]


async def _create_auto_channel(
    db_session: AsyncSession,
    universe_outlets: int | None,
) -> Channel:
    """Создаёт канал с заданным universe_outlets, возвращает Channel."""
    _auto_ch_counter["n"] += 1
    ch = Channel(
        code=f"AUTO_TEST_{_auto_ch_counter['n']}",
        name=f"Auto Test Channel {_auto_ch_counter['n']}",
        channel_group="OTHER",
        universe_outlets=universe_outlets,
    )
    db_session.add(ch)
    await db_session.flush()
    return ch


async def _link_psk_channel(
    db_session: AsyncSession,
    psk_id: int,
    channel_id: int,
    nd_target: str,
) -> None:
    """Создаёт ProjectSKUChannel с заданным nd_target."""
    from app.models.entities import ProjectSKUChannel

    psc = ProjectSKUChannel(
        project_sku_id=psk_id,
        channel_id=channel_id,
        nd_target=Decimal(nd_target),
    )
    db_session.add(psc)
    await db_session.flush()


async def test_akb_auto_empty_project_returns_empty_list(
    auth_client: AsyncClient,
) -> None:
    """C #17: проект без PSK → пустой список."""
    project_id = await _create_project_for_auto(auth_client)
    resp = await auth_client.get(f"/api/projects/{project_id}/akb/auto")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_akb_auto_returns_psk_channel_combinations(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """C #17: PSK с привязанным каналом → 1 entry с правильными полями."""
    project_id = await _create_project_for_auto(auth_client)
    psk_id = await _create_psk_for_auto(auth_client, project_id)
    channel = await _create_auto_channel(db_session, universe_outlets=1000)
    await _link_psk_channel(db_session, psk_id, channel.id, nd_target="0.5")

    resp = await auth_client.get(f"/api/projects/{project_id}/akb/auto")
    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) == 1
    e = entries[0]
    assert e["universe_outlets"] == 1000
    assert Decimal(e["nd_target"]) == Decimal("0.5")
    assert e["target_outlets"] == 500


async def test_akb_auto_target_outlets_computed(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """C #17: target = round(nd * universe). Проверяем округление: 0.333 × 1000 = 333."""
    project_id = await _create_project_for_auto(auth_client)
    psk_id = await _create_psk_for_auto(auth_client, project_id)
    channel = await _create_auto_channel(db_session, universe_outlets=1000)
    await _link_psk_channel(db_session, psk_id, channel.id, nd_target="0.333")

    resp = await auth_client.get(f"/api/projects/{project_id}/akb/auto")
    assert resp.status_code == 200
    assert resp.json()[0]["target_outlets"] == 333


async def test_akb_auto_universe_none_returns_target_none(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """C #17: если у канала universe_outlets is NULL → target_outlets is NULL."""
    project_id = await _create_project_for_auto(auth_client)
    psk_id = await _create_psk_for_auto(auth_client, project_id)
    channel = await _create_auto_channel(db_session, universe_outlets=None)
    await _link_psk_channel(db_session, psk_id, channel.id, nd_target="0.5")

    resp = await auth_client.get(f"/api/projects/{project_id}/akb/auto")
    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) == 1
    assert entries[0]["target_outlets"] is None
    assert entries[0]["universe_outlets"] is None
