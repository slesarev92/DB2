"""SKU + ProjectSKU + BOM API tests (задача 1.3).

Покрывает:
  - Справочник SKU CRUD (5 кейсов + 1 edge case с RESTRICT)
  - ProjectSKU CRUD (4 кейса)
  - BOM CRUD + COGS preview (4 кейса)

Всего 14 тестов. Пользуется фикстурами из conftest.py:
  - auth_client    — HTTPX с JWT
  - db_session     — изолированная транзакция
"""
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BOMItem


# ============================================================
# Helpers
# ============================================================


SKU_BODY = {
    "brand": "Gorji",
    "name": "Gorji Citrus 0.5L PET",
    "format": "PET",
    "volume_l": "0.5",
    "package_type": "Bottle",
    "segment": "CSD",
}

PROJECT_BODY = {
    "name": "Test project",
    "start_date": "2025-01-01",
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


# ============================================================
# 1. SKU CRUD: POST /api/skus (auth) → 201
# ============================================================


async def test_create_sku(auth_client: AsyncClient) -> None:
    resp = await auth_client.post("/api/skus", json=SKU_BODY)
    assert resp.status_code == 201
    data = resp.json()
    assert data["brand"] == "Gorji"
    assert data["name"] == "Gorji Citrus 0.5L PET"
    assert Decimal(data["volume_l"]) == Decimal("0.5")
    assert "id" in data


# ============================================================
# 2. SKU CRUD: POST /api/skus (no auth) → 401
# ============================================================


async def test_create_sku_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/api/skus", json=SKU_BODY)
    assert resp.status_code == 401


# ============================================================
# 3. SKU CRUD: GET list + GET by id
# ============================================================


async def test_list_and_get_sku(auth_client: AsyncClient) -> None:
    sku_id = await _create_sku(auth_client)
    await _create_sku(auth_client, name="Gorji Cherry 0.5L")

    list_resp = await auth_client.get("/api/skus")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 2

    get_resp = await auth_client.get(f"/api/skus/{sku_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == sku_id


# ============================================================
# 4. SKU CRUD: PATCH
# ============================================================


async def test_patch_sku(auth_client: AsyncClient) -> None:
    sku_id = await _create_sku(auth_client)

    resp = await auth_client.patch(
        f"/api/skus/{sku_id}",
        json={"name": "Gorji Citrus Renamed"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Gorji Citrus Renamed"
    # Прочие поля не изменились
    assert resp.json()["brand"] == "Gorji"


# ============================================================
# 5. SKU CRUD: DELETE без связей → 204
# ============================================================


async def test_delete_unused_sku(auth_client: AsyncClient) -> None:
    sku_id = await _create_sku(auth_client)

    resp = await auth_client.delete(f"/api/skus/{sku_id}")
    assert resp.status_code == 204

    get_resp = await auth_client.get(f"/api/skus/{sku_id}")
    assert get_resp.status_code == 404


# ============================================================
# 6. SKU CRUD: DELETE со связями → 409
# ============================================================


async def test_delete_sku_in_use_returns_409(auth_client: AsyncClient) -> None:
    project_id = await _create_project(auth_client)
    sku_id = await _create_sku(auth_client)

    add_resp = await auth_client.post(
        f"/api/projects/{project_id}/skus",
        json={"sku_id": sku_id},
    )
    assert add_resp.status_code == 201

    delete_resp = await auth_client.delete(f"/api/skus/{sku_id}")
    assert delete_resp.status_code == 409
    assert "referenced" in delete_resp.json()["detail"].lower()


# ============================================================
# 7. ProjectSKU: POST /api/projects/{id}/skus → 201 + nested sku
# ============================================================


async def test_add_sku_to_project_returns_nested_sku(
    auth_client: AsyncClient,
) -> None:
    project_id = await _create_project(auth_client)
    sku_id = await _create_sku(auth_client)

    resp = await auth_client.post(
        f"/api/projects/{project_id}/skus",
        json={"sku_id": sku_id, "production_cost_rate": "0.05"},
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["project_id"] == project_id
    assert data["sku_id"] == sku_id
    assert Decimal(data["production_cost_rate"]) == Decimal("0.05")
    # nested SKU включён
    assert data["sku"]["id"] == sku_id
    assert data["sku"]["brand"] == "Gorji"


# ============================================================
# 8. ProjectSKU: дубликат → 409
# ============================================================


async def test_add_same_sku_twice_returns_409(auth_client: AsyncClient) -> None:
    project_id = await _create_project(auth_client)
    sku_id = await _create_sku(auth_client)

    first = await auth_client.post(
        f"/api/projects/{project_id}/skus",
        json={"sku_id": sku_id},
    )
    assert first.status_code == 201

    second = await auth_client.post(
        f"/api/projects/{project_id}/skus",
        json={"sku_id": sku_id},
    )
    assert second.status_code == 409


# ============================================================
# 9. ProjectSKU: GET list возвращает все с nested SKU
# ============================================================


async def test_list_project_skus_with_nested(auth_client: AsyncClient) -> None:
    project_id = await _create_project(auth_client)
    sku1 = await _create_sku(auth_client, name="SKU One")
    sku2 = await _create_sku(auth_client, name="SKU Two")

    await auth_client.post(
        f"/api/projects/{project_id}/skus", json={"sku_id": sku1}
    )
    await auth_client.post(
        f"/api/projects/{project_id}/skus", json={"sku_id": sku2}
    )

    resp = await auth_client.get(f"/api/projects/{project_id}/skus")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert {item["sku"]["name"] for item in data} == {"SKU One", "SKU Two"}


# ============================================================
# 10. ProjectSKU: PATCH rates
# ============================================================


async def test_patch_project_sku_rates(auth_client: AsyncClient) -> None:
    project_id = await _create_project(auth_client)
    sku_id = await _create_sku(auth_client)
    add_resp = await auth_client.post(
        f"/api/projects/{project_id}/skus", json={"sku_id": sku_id}
    )
    psk_id = add_resp.json()["id"]

    resp = await auth_client.patch(
        f"/api/project-skus/{psk_id}",
        json={"production_cost_rate": "0.07", "marketing_rate": "0.03"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert Decimal(data["production_cost_rate"]) == Decimal("0.07")
    assert Decimal(data["marketing_rate"]) == Decimal("0.03")
    assert Decimal(data["ca_m_rate"]) == Decimal("0")  # не трогали


# ============================================================
# 11. BOM: POST /api/project-skus/{id}/bom → 201
# ============================================================


async def test_create_bom_item(auth_client: AsyncClient) -> None:
    project_id = await _create_project(auth_client)
    sku_id = await _create_sku(auth_client)
    add_resp = await auth_client.post(
        f"/api/projects/{project_id}/skus", json={"sku_id": sku_id}
    )
    psk_id = add_resp.json()["id"]

    resp = await auth_client.post(
        f"/api/project-skus/{psk_id}/bom",
        json={
            "ingredient_name": "Sugar",
            "quantity_per_unit": "0.05",
            "loss_pct": "0.02",
            "price_per_unit": "60.0",
        },
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["ingredient_name"] == "Sugar"
    assert data["project_sku_id"] == psk_id


# ============================================================
# 12. BOM: GET list
# ============================================================


async def test_list_bom_items(auth_client: AsyncClient) -> None:
    project_id = await _create_project(auth_client)
    sku_id = await _create_sku(auth_client)
    psk_id = (
        await auth_client.post(
            f"/api/projects/{project_id}/skus", json={"sku_id": sku_id}
        )
    ).json()["id"]

    for ingredient in ("Sugar", "Water", "CO2"):
        await auth_client.post(
            f"/api/project-skus/{psk_id}/bom",
            json={
                "ingredient_name": ingredient,
                "quantity_per_unit": "0.1",
                "price_per_unit": "10.0",
            },
        )

    resp = await auth_client.get(f"/api/project-skus/{psk_id}/bom")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    assert {item["ingredient_name"] for item in data} == {"Sugar", "Water", "CO2"}


# ============================================================
# 13. ProjectSKU detail возвращает COGS preview из BOM
# ============================================================


async def test_get_project_sku_detail_calculates_cogs_preview(
    auth_client: AsyncClient,
) -> None:
    project_id = await _create_project(auth_client)
    sku_id = await _create_sku(auth_client)
    psk_id = (
        await auth_client.post(
            f"/api/projects/{project_id}/skus", json={"sku_id": sku_id}
        )
    ).json()["id"]

    # До добавления BOM — COGS = 0
    detail0 = await auth_client.get(f"/api/project-skus/{psk_id}")
    assert detail0.status_code == 200
    assert Decimal(detail0.json()["cogs_per_unit_estimated"]) == Decimal("0")

    # Sugar: qty=0.05 × price=60 × (1+loss=0.02) = 3.06
    await auth_client.post(
        f"/api/project-skus/{psk_id}/bom",
        json={
            "ingredient_name": "Sugar",
            "quantity_per_unit": "0.05",
            "loss_pct": "0.02",
            "price_per_unit": "60.0",
        },
    )
    # Water: qty=0.5 × price=2 × (1+0) = 1
    await auth_client.post(
        f"/api/project-skus/{psk_id}/bom",
        json={
            "ingredient_name": "Water",
            "quantity_per_unit": "0.5",
            "loss_pct": "0",
            "price_per_unit": "2.0",
        },
    )

    detail = await auth_client.get(f"/api/project-skus/{psk_id}")
    assert detail.status_code == 200
    expected = Decimal("0.05") * Decimal("60.0") * (Decimal("1") + Decimal("0.02"))
    expected += Decimal("0.5") * Decimal("2.0") * Decimal("1")  # = 4.06
    assert Decimal(detail.json()["cogs_per_unit_estimated"]) == expected
    assert Decimal(detail.json()["cogs_per_unit_estimated"]) == Decimal("4.06")


# ============================================================
# 14. DELETE ProjectSKU каскадно удаляет BOM (CASCADE на FK)
# ============================================================


async def test_delete_project_sku_cascades_bom(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    project_id = await _create_project(auth_client)
    sku_id = await _create_sku(auth_client)
    psk_id = (
        await auth_client.post(
            f"/api/projects/{project_id}/skus", json={"sku_id": sku_id}
        )
    ).json()["id"]

    await auth_client.post(
        f"/api/project-skus/{psk_id}/bom",
        json={
            "ingredient_name": "Test",
            "quantity_per_unit": "0.1",
            "price_per_unit": "1.0",
        },
    )

    # Подтверждаем что BOM существует в БД
    bom_count = len(
        (
            await db_session.scalars(
                select(BOMItem).where(BOMItem.project_sku_id == psk_id)
            )
        ).all()
    )
    assert bom_count == 1

    # Удаляем ProjectSKU
    resp = await auth_client.delete(f"/api/project-skus/{psk_id}")
    assert resp.status_code == 204

    # BOM физически удалён через CASCADE
    bom_count_after = len(
        (
            await db_session.scalars(
                select(BOMItem).where(BOMItem.project_sku_id == psk_id)
            )
        ).all()
    )
    assert bom_count_after == 0
