"""Тесты GET/PUT /api/projects/{id}/financial-plan.

CAPEX/OPEX по годам проекта для pipeline. UI работает per-year,
backend хранит per-period — сервис делает маппинг.
"""
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Period, ProjectFinancialPlan


VALID_PROJECT = {
    "name": "Financial plan test",
    "start_date": "2025-01-01",
    "horizon_years": 10,
    "wacc": "0.19",
    "tax_rate": "0.20",
    "wc_rate": "0.12",
    "vat_rate": "0.20",
    "currency": "RUB",
}


async def _create_project(auth_client: AsyncClient) -> int:
    resp = await auth_client.post("/api/projects", json=VALID_PROJECT)
    assert resp.status_code == 201
    return resp.json()["id"]


# ============================================================
# GET — по умолчанию 10 строк нулей
# ============================================================


async def test_get_plan_returns_10_years_zeros_by_default(
    auth_client: AsyncClient,
) -> None:
    project_id = await _create_project(auth_client)
    resp = await auth_client.get(f"/api/projects/{project_id}/financial-plan")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 10
    years = [item["year"] for item in data]
    assert years == list(range(1, 11))
    for item in data:
        assert Decimal(item["capex"]) == Decimal("0")
        assert Decimal(item["opex"]) == Decimal("0")


async def test_get_plan_unknown_project_404(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/api/projects/999999/financial-plan")
    assert resp.status_code == 404


async def test_get_plan_unauthorized(client: AsyncClient) -> None:
    resp = await client.get("/api/projects/1/financial-plan")
    assert resp.status_code == 401


# ============================================================
# PUT — batch replace
# ============================================================


async def test_put_plan_creates_records(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    project_id = await _create_project(auth_client)
    body = {
        "items": [
            {"year": 1, "capex": "6602348", "opex": "0"},
            {"year": 2, "capex": "5440000", "opex": "320000"},
            {"year": 5, "capex": "0", "opex": "1500000"},
        ]
    }
    resp = await auth_client.put(
        f"/api/projects/{project_id}/financial-plan", json=body
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 10

    y1 = next(i for i in data if i["year"] == 1)
    assert Decimal(y1["capex"]) == Decimal("6602348")
    y2 = next(i for i in data if i["year"] == 2)
    assert Decimal(y2["capex"]) == Decimal("5440000")
    assert Decimal(y2["opex"]) == Decimal("320000")
    y5 = next(i for i in data if i["year"] == 5)
    assert Decimal(y5["opex"]) == Decimal("1500000")

    # Годы которых нет в items → нули
    y3 = next(i for i in data if i["year"] == 3)
    assert Decimal(y3["capex"]) == Decimal("0")
    assert Decimal(y3["opex"]) == Decimal("0")

    # В БД должны быть 3 реальные записи
    rows = (
        await db_session.scalars(
            select(ProjectFinancialPlan).where(
                ProjectFinancialPlan.project_id == project_id
            )
        )
    ).all()
    assert len(list(rows)) == 3


async def test_put_plan_replaces_existing(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Повторный PUT полностью заменяет — старые записи удаляются."""
    project_id = await _create_project(auth_client)

    first = {"items": [{"year": 1, "capex": "1000", "opex": "0"}]}
    await auth_client.put(
        f"/api/projects/{project_id}/financial-plan", json=first
    )

    second = {"items": [{"year": 2, "capex": "2000", "opex": "0"}]}
    resp = await auth_client.put(
        f"/api/projects/{project_id}/financial-plan", json=second
    )
    data = resp.json()

    y1 = next(i for i in data if i["year"] == 1)
    assert Decimal(y1["capex"]) == Decimal("0")  # старое удалено
    y2 = next(i for i in data if i["year"] == 2)
    assert Decimal(y2["capex"]) == Decimal("2000")  # новое вставлено

    # В БД ровно одна запись
    rows = (
        await db_session.scalars(
            select(ProjectFinancialPlan).where(
                ProjectFinancialPlan.project_id == project_id
            )
        )
    ).all()
    assert len(list(rows)) == 1


async def test_put_plan_empty_items_clears(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    """PUT с items=[] полностью очищает план."""
    project_id = await _create_project(auth_client)
    await auth_client.put(
        f"/api/projects/{project_id}/financial-plan",
        json={"items": [{"year": 1, "capex": "1000", "opex": "0"}]},
    )
    resp = await auth_client.put(
        f"/api/projects/{project_id}/financial-plan", json={"items": []}
    )
    assert resp.status_code == 200
    data = resp.json()
    for item in data:
        assert Decimal(item["capex"]) == Decimal("0")
        assert Decimal(item["opex"]) == Decimal("0")

    rows = (
        await db_session.scalars(
            select(ProjectFinancialPlan).where(
                ProjectFinancialPlan.project_id == project_id
            )
        )
    ).all()
    assert len(list(rows)) == 0


async def test_put_plan_mapped_to_correct_period(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Проверка что backend кладёт запись на правильный period_id
    (первый период model_year). Для Y1 это period_number=1 (M1),
    для Y4 — period_number=37 (первый yearly)."""
    project_id = await _create_project(auth_client)
    await auth_client.put(
        f"/api/projects/{project_id}/financial-plan",
        json={
            "items": [
                {"year": 1, "capex": "100", "opex": "0"},
                {"year": 4, "capex": "400", "opex": "0"},
            ]
        },
    )
    rows = (
        await db_session.execute(
            select(ProjectFinancialPlan, Period)
            .join(Period, Period.id == ProjectFinancialPlan.period_id)
            .where(ProjectFinancialPlan.project_id == project_id)
        )
    ).all()
    assert len(rows) == 2

    by_year = {p.model_year: (plan, p) for plan, p in rows}
    # Y1 → M1 (period_number=1)
    assert by_year[1][1].period_number == 1
    assert by_year[1][0].capex == Decimal("100")
    # Y4 → первый yearly period (period_number=37)
    assert by_year[4][1].period_number == 37
    assert by_year[4][0].capex == Decimal("400")


async def test_put_plan_unauthorized(client: AsyncClient) -> None:
    resp = await client.put(
        "/api/projects/1/financial-plan", json={"items": []}
    )
    assert resp.status_code == 401
