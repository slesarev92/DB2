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
