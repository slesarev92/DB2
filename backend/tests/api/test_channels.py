"""Channels + ProjectSKUChannel API tests (задача 1.4).

Channels — read-only (вариант A одобрен), 25 каналов засеяны через
test_engine fixture в conftest.py.
ProjectSKUChannel — full CRUD по аналогии с ProjectSKU из 1.3.

C #16: добавлены тесты на channel_group и source_type (4 теста).

11 + 4 = 15 кейсов всего.
"""
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel


# ============================================================
# Helpers
# ============================================================


SKU_BODY = {
    "brand": "Gorji",
    "name": "Gorji Citrus 0.5L",
}

PROJECT_BODY = {
    "name": "Test project for channels",
    "start_date": "2025-01-01",
}


async def _create_psk(client: AsyncClient) -> int:
    """Создаёт project + sku + project_sku, возвращает psk.id."""
    project_resp = await client.post("/api/projects", json=PROJECT_BODY)
    project_id = project_resp.json()["id"]

    sku_resp = await client.post("/api/skus", json=SKU_BODY)
    sku_id = sku_resp.json()["id"]

    psk_resp = await client.post(
        f"/api/projects/{project_id}/skus", json={"sku_id": sku_id}
    )
    return psk_resp.json()["id"]


async def _get_channel_id(db_session: AsyncSession, code: str) -> int:
    """Берёт id канала по коду из засеянных данных."""
    channel = await db_session.scalar(
        select(Channel).where(Channel.code == code)
    )
    assert channel is not None, f"Channel {code} not seeded"
    return channel.id


# ============================================================
# 1. GET /api/channels (auth) — список из 25 каналов из seed
# ============================================================


async def test_list_channels_returns_seeded(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/api/channels")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 25
    codes = {c["code"] for c in data}
    assert "HM" in codes
    assert "SM" in codes
    assert "E-COM_OZ" in codes


# ============================================================
# 2. GET /api/channels (no auth) → 401
# ============================================================


async def test_list_channels_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/channels")
    assert resp.status_code == 401


# ============================================================
# 3. GET /api/channels/{id} → 200
# ============================================================


async def test_get_channel_by_id(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    channel_id = await _get_channel_id(db_session, "HM")
    resp = await auth_client.get(f"/api/channels/{channel_id}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == "HM"
    assert data["name"] == "Гипермаркеты"
    assert data["universe_outlets"] == 822


# ============================================================
# 4. GET /api/channels/{id} (несуществующий) → 404
# ============================================================


async def test_get_channel_nonexistent_returns_404(
    auth_client: AsyncClient,
) -> None:
    resp = await auth_client.get("/api/channels/99999")
    assert resp.status_code == 404


# ============================================================
# 5. POST /api/project-skus/{psk_id}/channels → 201 + nested channel
# ============================================================


async def test_attach_channel_to_psk_returns_nested(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    psk_id = await _create_psk(auth_client)
    hm_id = await _get_channel_id(db_session, "HM")

    resp = await auth_client.post(
        f"/api/project-skus/{psk_id}/channels",
        json={
            "channel_id": hm_id,
            "nd_target": "0.6",
            "nd_ramp_months": 12,
            "offtake_target": "10.5",
            "shelf_price_reg": "89.90",
        },
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["project_sku_id"] == psk_id
    assert data["channel_id"] == hm_id
    assert Decimal(data["nd_target"]) == Decimal("0.6")
    assert Decimal(data["shelf_price_reg"]) == Decimal("89.90")
    # nested channel
    assert data["channel"]["code"] == "HM"
    assert data["channel"]["universe_outlets"] == 822


# ============================================================
# 6. POST дубликат → 409
# ============================================================


async def test_attach_same_channel_twice_returns_409(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    psk_id = await _create_psk(auth_client)
    sm_id = await _get_channel_id(db_session, "SM")

    first = await auth_client.post(
        f"/api/project-skus/{psk_id}/channels", json={"channel_id": sm_id}
    )
    assert first.status_code == 201

    second = await auth_client.post(
        f"/api/project-skus/{psk_id}/channels", json={"channel_id": sm_id}
    )
    assert second.status_code == 409


# ============================================================
# 7. POST с несуществующим channel_id → 404
# ============================================================


async def test_attach_nonexistent_channel_returns_404(
    auth_client: AsyncClient,
) -> None:
    psk_id = await _create_psk(auth_client)

    resp = await auth_client.post(
        f"/api/project-skus/{psk_id}/channels", json={"channel_id": 99999}
    )
    assert resp.status_code == 404


# ============================================================
# 8. GET list — все каналы SKU с nested channel
# ============================================================


async def test_list_psk_channels_with_nested(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    psk_id = await _create_psk(auth_client)
    hm_id = await _get_channel_id(db_session, "HM")
    sm_id = await _get_channel_id(db_session, "SM")
    mm_id = await _get_channel_id(db_session, "MM")

    for ch_id in (hm_id, sm_id, mm_id):
        await auth_client.post(
            f"/api/project-skus/{psk_id}/channels", json={"channel_id": ch_id}
        )

    resp = await auth_client.get(f"/api/project-skus/{psk_id}/channels")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    assert {item["channel"]["code"] for item in data} == {"HM", "SM", "MM"}


# ============================================================
# 9. GET /api/psk-channels/{id} → detail с nested channel
# ============================================================


async def test_get_psk_channel_detail(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    psk_id = await _create_psk(auth_client)
    tt_id = await _get_channel_id(db_session, "TT")

    create_resp = await auth_client.post(
        f"/api/project-skus/{psk_id}/channels", json={"channel_id": tt_id}
    )
    psk_channel_id = create_resp.json()["id"]

    resp = await auth_client.get(f"/api/psk-channels/{psk_channel_id}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == psk_channel_id
    assert data["channel"]["code"] == "TT"
    assert data["channel"]["universe_outlets"] == 91_444


# ============================================================
# 10. PATCH параметры
# ============================================================


async def test_patch_psk_channel_parameters(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    psk_id = await _create_psk(auth_client)
    hm_id = await _get_channel_id(db_session, "HM")

    create_resp = await auth_client.post(
        f"/api/project-skus/{psk_id}/channels",
        json={"channel_id": hm_id, "nd_target": "0.5"},
    )
    psk_channel_id = create_resp.json()["id"]

    resp = await auth_client.patch(
        f"/api/psk-channels/{psk_channel_id}",
        json={
            "nd_target": "0.75",
            "shelf_price_reg": "99.90",
            "promo_share": "0.20",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert Decimal(data["nd_target"]) == Decimal("0.75")
    assert Decimal(data["shelf_price_reg"]) == Decimal("99.90")
    assert Decimal(data["promo_share"]) == Decimal("0.20")
    # Не трогали — должны остаться defaults / прежние
    assert data["nd_ramp_months"] == 12


# ============================================================
# 11. DELETE → 204
# ============================================================


async def test_delete_psk_channel(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    psk_id = await _create_psk(auth_client)
    hm_id = await _get_channel_id(db_session, "HM")

    create_resp = await auth_client.post(
        f"/api/project-skus/{psk_id}/channels", json={"channel_id": hm_id}
    )
    psk_channel_id = create_resp.json()["id"]

    delete_resp = await auth_client.delete(
        f"/api/psk-channels/{psk_channel_id}"
    )
    assert delete_resp.status_code == 204

    get_resp = await auth_client.get(f"/api/psk-channels/{psk_channel_id}")
    assert get_resp.status_code == 404


# ============================================================
# C #16: channel_group + source_type field tests (4 новых теста)
# ============================================================


async def test_create_channel_with_group_and_source(
    auth_client: AsyncClient,
) -> None:
    """C #16: POST /api/channels принимает channel_group и source_type."""
    resp = await auth_client.post(
        "/api/channels",
        json={
            "code": "TEST_HM_C16",
            "name": "Test Hypermarket C16",
            "channel_group": "HM",
            "source_type": "nielsen",
            "universe_outlets": 100,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["channel_group"] == "HM"
    assert body["source_type"] == "nielsen"


async def test_patch_channel_group(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """C #16: PATCH channel_group переводит канал в другую группу."""
    # Используем существующий засеянный канал OTHER (Beauty)
    channel_id = await _get_channel_id(db_session, "Beauty")
    resp = await auth_client.patch(
        f"/api/channels/{channel_id}",
        json={"channel_group": "HM"},
    )
    assert resp.status_code == 200
    assert resp.json()["channel_group"] == "HM"


async def test_create_channel_invalid_group_422(
    auth_client: AsyncClient,
) -> None:
    """C #16: Pydantic отвергает channel_group вне 8 значений."""
    resp = await auth_client.post(
        "/api/channels",
        json={
            "code": "X_INVALID",
            "name": "X Invalid",
            "channel_group": "INVALID_GROUP",
        },
    )
    assert resp.status_code == 422


async def test_create_channel_invalid_source_type_422(
    auth_client: AsyncClient,
) -> None:
    """C #16: Pydantic отвергает source_type вне 5 значений."""
    resp = await auth_client.post(
        "/api/channels",
        json={
            "code": "X_INVALID2",
            "name": "X Invalid Source",
            "channel_group": "OTHER",
            "source_type": "other_source",
        },
    )
    assert resp.status_code == 422
