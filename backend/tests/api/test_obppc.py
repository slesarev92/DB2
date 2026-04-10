"""Тесты B-13: OBPPC Price-Pack-Channel matrix CRUD."""
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel


# ============================================================
# Helpers
# ============================================================

PROJECT_BODY = {
    "name": "OBPPC test project",
    "start_date": "2025-01-01",
}

SKU_BODY = {
    "brand": "TestBrand",
    "name": "Test SKU 0.5L",
}


async def _create_project(client: AsyncClient) -> int:
    resp = await client.post("/api/projects", json=PROJECT_BODY)
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_sku(client: AsyncClient, **overrides) -> int:
    body = {**SKU_BODY, **overrides}
    resp = await client.post("/api/skus", json=body)
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


async def test_create_obppc_entry(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    project_id = await _create_project(auth_client)
    sku_id = await _create_sku(auth_client)
    channel_id = await _get_channel_id(db_session, "HM")

    resp = await auth_client.post(
        f"/api/projects/{project_id}/obppc",
        json={
            "sku_id": sku_id,
            "channel_id": channel_id,
            "occasion": "on-the-go",
            "price_tier": "premium",
            "pack_format": "can",
            "pack_size_ml": 330,
            "price_point": "149.90",
            "is_active": True,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["project_id"] == project_id
    assert data["sku_id"] == sku_id
    assert data["channel_id"] == channel_id
    assert data["occasion"] == "on-the-go"
    assert data["price_tier"] == "premium"
    assert data["pack_format"] == "can"
    assert data["pack_size_ml"] == 330
    assert Decimal(data["price_point"]) == Decimal("149.90")
    assert data["sku"]["brand"] == "TestBrand"
    assert data["channel"]["code"] == "HM"


async def test_list_obppc_entries(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    project_id = await _create_project(auth_client)
    sku_id = await _create_sku(auth_client, name="List SKU")
    hm_id = await _get_channel_id(db_session, "HM")
    sm_id = await _get_channel_id(db_session, "SM")

    await auth_client.post(
        f"/api/projects/{project_id}/obppc",
        json={
            "sku_id": sku_id,
            "channel_id": hm_id,
            "pack_format": "bottle",
            "price_tier": "mainstream",
        },
    )
    await auth_client.post(
        f"/api/projects/{project_id}/obppc",
        json={
            "sku_id": sku_id,
            "channel_id": sm_id,
            "pack_format": "can",
            "price_tier": "value",
        },
    )

    resp = await auth_client.get(f"/api/projects/{project_id}/obppc")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    channels = {e["channel"]["code"] for e in data}
    assert channels == {"HM", "SM"}


async def test_get_obppc_entry(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    project_id = await _create_project(auth_client)
    sku_id = await _create_sku(auth_client, name="Get SKU")
    channel_id = await _get_channel_id(db_session, "TT")

    create_resp = await auth_client.post(
        f"/api/projects/{project_id}/obppc",
        json={
            "sku_id": sku_id,
            "channel_id": channel_id,
            "pack_format": "pouch",
            "price_tier": "value",
            "pack_size_ml": 200,
        },
    )
    entry_id = create_resp.json()["id"]

    resp = await auth_client.get(
        f"/api/projects/{project_id}/obppc/{entry_id}"
    )
    assert resp.status_code == 200
    assert resp.json()["pack_format"] == "pouch"
    assert resp.json()["pack_size_ml"] == 200
    assert resp.json()["channel"]["code"] == "TT"


async def test_update_obppc_entry(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    project_id = await _create_project(auth_client)
    sku_id = await _create_sku(auth_client, name="Update SKU")
    channel_id = await _get_channel_id(db_session, "HM")

    create_resp = await auth_client.post(
        f"/api/projects/{project_id}/obppc",
        json={
            "sku_id": sku_id,
            "channel_id": channel_id,
            "pack_format": "bottle",
            "price_tier": "mainstream",
            "price_point": "100.00",
        },
    )
    entry_id = create_resp.json()["id"]

    resp = await auth_client.patch(
        f"/api/projects/{project_id}/obppc/{entry_id}",
        json={
            "price_tier": "premium",
            "price_point": "179.90",
            "notes": "Repositioned",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["price_tier"] == "premium"
    assert Decimal(resp.json()["price_point"]) == Decimal("179.90")
    assert resp.json()["notes"] == "Repositioned"


async def test_delete_obppc_entry(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    project_id = await _create_project(auth_client)
    sku_id = await _create_sku(auth_client, name="Delete SKU")
    channel_id = await _get_channel_id(db_session, "SM")

    create_resp = await auth_client.post(
        f"/api/projects/{project_id}/obppc",
        json={
            "sku_id": sku_id,
            "channel_id": channel_id,
            "pack_format": "bottle",
        },
    )
    entry_id = create_resp.json()["id"]

    resp = await auth_client.delete(
        f"/api/projects/{project_id}/obppc/{entry_id}"
    )
    assert resp.status_code == 204

    get_resp = await auth_client.get(
        f"/api/projects/{project_id}/obppc/{entry_id}"
    )
    assert get_resp.status_code == 404


async def test_obppc_not_found(auth_client: AsyncClient) -> None:
    project_id = await _create_project(auth_client)
    resp = await auth_client.get(
        f"/api/projects/{project_id}/obppc/999999"
    )
    assert resp.status_code == 404


async def test_obppc_unauthorized(client: AsyncClient) -> None:
    resp = await client.get("/api/projects/1/obppc")
    assert resp.status_code == 401


async def test_obppc_invalid_price_tier(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    """price_tier must be premium/mainstream/value."""
    project_id = await _create_project(auth_client)
    sku_id = await _create_sku(auth_client, name="Invalid Tier SKU")
    channel_id = await _get_channel_id(db_session, "HM")

    resp = await auth_client.post(
        f"/api/projects/{project_id}/obppc",
        json={
            "sku_id": sku_id,
            "channel_id": channel_id,
            "pack_format": "bottle",
            "price_tier": "ultra_premium",
        },
    )
    assert resp.status_code == 422
