"""Тесты read-only справочников API (задача 3.2 backend extension).

GET /api/ref-inflation — список профилей инфляции для frontend dropdown.
"""
from httpx import AsyncClient


async def test_list_ref_inflation_returns_seeded_profiles(
    auth_client: AsyncClient,
) -> None:
    """conftest сидирует 16 профилей инфляции — endpoint должен их вернуть."""
    resp = await auth_client.get("/api/ref-inflation")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 16  # минимум столько в seed_reference_data

    # Профиль "No_Inflation" должен присутствовать
    names = {p["profile_name"] for p in data}
    assert "No_Inflation" in names
    assert "Апрель/Октябрь +7%" in names

    # Структура одной записи
    sample = data[0]
    assert "id" in sample
    assert "profile_name" in sample
    assert "month_coefficients" in sample
    assert isinstance(sample["month_coefficients"], dict)


async def test_list_ref_inflation_unauthorized(client: AsyncClient) -> None:
    resp = await client.get("/api/ref-inflation")
    assert resp.status_code == 401


async def test_list_ref_inflation_sorted_by_name(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/api/ref-inflation")
    data = resp.json()
    names = [p["profile_name"] for p in data]
    assert names == sorted(names)


# ============================================================
# GET /api/ref-seasonality
# ============================================================


async def test_list_ref_seasonality_returns_seeded_profiles(
    auth_client: AsyncClient,
) -> None:
    """conftest сидирует профили сезонности — endpoint должен их вернуть."""
    resp = await auth_client.get("/api/ref-seasonality")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1

    sample = data[0]
    assert "id" in sample
    assert "profile_name" in sample
    assert "month_coefficients" in sample
    assert isinstance(sample["month_coefficients"], dict)


async def test_list_ref_seasonality_unauthorized(client: AsyncClient) -> None:
    resp = await client.get("/api/ref-seasonality")
    assert resp.status_code == 401


async def test_list_ref_seasonality_sorted_by_name(
    auth_client: AsyncClient,
) -> None:
    resp = await auth_client.get("/api/ref-seasonality")
    data = resp.json()
    names = [p["profile_name"] for p in data]
    assert names == sorted(names)


# ============================================================
# GET /api/periods (для frontend AG Grid таблицы периодов, задача 4.1)
# ============================================================


async def test_list_periods_returns_43_rows(auth_client: AsyncClient) -> None:
    """Conftest сидирует 43 периода (36 monthly M1..M36 + 7 yearly Y4..Y10)."""
    resp = await auth_client.get("/api/periods")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 43

    # Структура одной записи
    sample = data[0]
    assert "id" in sample
    assert "type" in sample
    assert "period_number" in sample
    assert "model_year" in sample
    assert "month_num" in sample


async def test_list_periods_split_by_type(auth_client: AsyncClient) -> None:
    """36 monthly (M1..M36) и 7 yearly (Y4..Y10)."""
    resp = await auth_client.get("/api/periods")
    data = resp.json()

    monthly = [p for p in data if p["type"] == "monthly"]
    yearly = [p for p in data if p["type"] == "annual"]
    assert len(monthly) == 36
    assert len(yearly) == 7

    assert all(p["month_num"] is not None for p in monthly)
    assert all(p["month_num"] is None for p in yearly)


async def test_list_periods_sorted_by_period_number(
    auth_client: AsyncClient,
) -> None:
    resp = await auth_client.get("/api/periods")
    data = resp.json()
    numbers = [p["period_number"] for p in data]
    assert numbers == list(range(1, 44))  # 1..43


async def test_list_periods_unauthorized(client: AsyncClient) -> None:
    resp = await client.get("/api/periods")
    assert resp.status_code == 401
