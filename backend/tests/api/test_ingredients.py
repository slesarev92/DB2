"""Тесты B-04: Ingredient catalog + price history + BOM auto-fill."""
from decimal import Decimal

from httpx import AsyncClient


# ============================================================
# Helpers
# ============================================================

INGREDIENT = {
    "name": "Sugar",
    "unit": "kg",
    "category": "raw_material",
}


async def _create_ingredient(auth_client: AsyncClient, **overrides) -> int:
    body = {**INGREDIENT, **overrides}
    resp = await auth_client.post("/api/ingredients", json=body)
    assert resp.status_code == 201
    return resp.json()["id"]


# ============================================================
# CRUD ingredients
# ============================================================


async def test_create_ingredient(auth_client: AsyncClient) -> None:
    resp = await auth_client.post("/api/ingredients", json=INGREDIENT)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Sugar"
    assert data["unit"] == "kg"
    assert data["category"] == "raw_material"
    assert data["latest_price"] is None


async def test_list_ingredients(auth_client: AsyncClient) -> None:
    await _create_ingredient(auth_client, name="Citric Acid")
    await _create_ingredient(auth_client, name="PET Preform")
    resp = await auth_client.get("/api/ingredients")
    assert resp.status_code == 200
    names = [i["name"] for i in resp.json()]
    assert "Citric Acid" in names
    assert "PET Preform" in names


async def test_update_ingredient(auth_client: AsyncClient) -> None:
    ing_id = await _create_ingredient(auth_client, name="Old Name")
    resp = await auth_client.patch(
        f"/api/ingredients/{ing_id}", json={"name": "New Name"}
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"


async def test_delete_ingredient(auth_client: AsyncClient) -> None:
    ing_id = await _create_ingredient(auth_client, name="To Delete")
    resp = await auth_client.delete(f"/api/ingredients/{ing_id}")
    assert resp.status_code == 204


async def test_ingredient_not_found(auth_client: AsyncClient) -> None:
    resp = await auth_client.patch(
        "/api/ingredients/999999", json={"name": "X"}
    )
    assert resp.status_code == 404


async def test_ingredient_unauthorized(client: AsyncClient) -> None:
    resp = await client.get("/api/ingredients")
    assert resp.status_code == 401


# ============================================================
# Price history
# ============================================================


async def test_add_and_list_prices(auth_client: AsyncClient) -> None:
    ing_id = await _create_ingredient(auth_client, name="Price Test")
    # Add two prices
    resp1 = await auth_client.post(
        f"/api/ingredients/{ing_id}/prices",
        json={"price_per_unit": "120.50", "effective_date": "2025-01-01"},
    )
    assert resp1.status_code == 201

    resp2 = await auth_client.post(
        f"/api/ingredients/{ing_id}/prices",
        json={
            "price_per_unit": "135.00",
            "effective_date": "2025-06-01",
            "notes": "Q2 price increase",
        },
    )
    assert resp2.status_code == 201

    # List prices (newest first)
    resp = await auth_client.get(f"/api/ingredients/{ing_id}/prices")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert Decimal(data[0]["price_per_unit"]) == Decimal("135.00")
    assert data[0]["notes"] == "Q2 price increase"


async def test_latest_price_in_list(auth_client: AsyncClient) -> None:
    """After adding prices, GET /ingredients shows latest_price."""
    ing_id = await _create_ingredient(auth_client, name="Latest Price Test")
    await auth_client.post(
        f"/api/ingredients/{ing_id}/prices",
        json={"price_per_unit": "100", "effective_date": "2025-01-01"},
    )
    await auth_client.post(
        f"/api/ingredients/{ing_id}/prices",
        json={"price_per_unit": "110", "effective_date": "2025-06-01"},
    )

    resp = await auth_client.get("/api/ingredients")
    data = resp.json()
    ing = next(i for i in data if i["id"] == ing_id)
    assert Decimal(ing["latest_price"]) == Decimal("110")


# ============================================================
# BOM auto-fill from ingredient
# ============================================================


async def test_bom_create_with_ingredient_id_autofills(
    auth_client: AsyncClient,
) -> None:
    """POST BOM with ingredient_id → ingredient_name and price auto-filled."""
    ing_id = await _create_ingredient(auth_client, name="Auto Fill Test")
    await auth_client.post(
        f"/api/ingredients/{ing_id}/prices",
        json={"price_per_unit": "250.00", "effective_date": "2025-01-01"},
    )

    # Create project + SKU + PSK
    project_id = (
        await auth_client.post(
            "/api/projects",
            json={"name": "BOM autofill test", "start_date": "2025-01-01"},
        )
    ).json()["id"]
    sku_id = (
        await auth_client.post(
            "/api/skus",
            json={"brand": "Test", "name": "Autofill SKU"},
        )
    ).json()["id"]
    psk_id = (
        await auth_client.post(
            f"/api/projects/{project_id}/skus",
            json={"sku_id": sku_id},
        )
    ).json()["id"]

    # Create BOM item with ingredient_id
    resp = await auth_client.post(
        f"/api/project-skus/{psk_id}/bom",
        json={
            "ingredient_name": "Auto Fill Test",
            "quantity_per_unit": "0.5",
            "ingredient_id": ing_id,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["ingredient_name"] == "Auto Fill Test"
    assert Decimal(data["price_per_unit"]) == Decimal("250.00")
    assert data["ingredient_id"] == ing_id
