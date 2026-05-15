"""Тесты GET/PUT /api/projects/{id}/financial-plan.

B.9b (2026-05-15): per-period контракт. 43 элемента (1..43):
period 1..36 = monthly Y1-Y3, period 37..43 = yearly Y4-Y10.
"""
from decimal import Decimal

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OpexItem, Period, ProjectFinancialPlan
from app.schemas.financial_plan import FinancialPlanItem, FinancialPlanRequest
from app.services import financial_plan_service


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
# Schema contract
# ============================================================


def test_financial_plan_item_accepts_period_number() -> None:
    assert (
        FinancialPlanItem(period_number=1, capex="100", opex="0").period_number == 1
    )
    assert (
        FinancialPlanItem(period_number=43, capex="0", opex="0").period_number == 43
    )


def test_financial_plan_item_rejects_period_number_out_of_range() -> None:
    with pytest.raises(ValidationError):
        FinancialPlanItem(period_number=0, capex="0", opex="0")
    with pytest.raises(ValidationError):
        FinancialPlanItem(period_number=44, capex="0", opex="0")


def test_financial_plan_item_no_year_field() -> None:
    item = FinancialPlanItem(period_number=1, year=1, capex="0", opex="0")
    assert not hasattr(item, "year")


def test_financial_plan_request_rejects_duplicate_period_number() -> None:
    with pytest.raises(ValidationError):
        FinancialPlanRequest(items=[
            FinancialPlanItem(period_number=1, capex="100", opex="0"),
            FinancialPlanItem(period_number=1, capex="200", opex="0"),
        ])


# ============================================================
# Service: list_plan_by_period
# ============================================================


async def test_list_plan_by_period_returns_43_elements(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    project_id = await _create_project(auth_client)
    plan = await financial_plan_service.list_plan_by_period(
        db_session, project_id
    )
    assert len(plan) == 43
    period_numbers = [item.period_number for item in plan]
    assert period_numbers == list(range(1, 44))
    for item in plan:
        assert item.capex == Decimal("0")
        assert item.opex == Decimal("0")
        assert item.opex_items == []
        assert item.capex_items == []


# ============================================================
# GET — empty project returns 43 zeros
# ============================================================


async def test_get_plan_returns_43_periods_zeros_by_default(
    auth_client: AsyncClient,
) -> None:
    project_id = await _create_project(auth_client)
    resp = await auth_client.get(f"/api/projects/{project_id}/financial-plan")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 43
    period_numbers = [item["period_number"] for item in data]
    assert period_numbers == list(range(1, 44))
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
# PUT — basic record creation
# ============================================================


async def test_put_plan_creates_records_at_specific_periods(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    project_id = await _create_project(auth_client)
    body = {
        "items": [
            {"period_number": 3,  "capex": "15000000", "opex": "0"},
            {"period_number": 13, "capex": "5440000",  "opex": "320000"},
            {"period_number": 37, "capex": "0",        "opex": "1500000"},
        ]
    }
    resp = await auth_client.put(
        f"/api/projects/{project_id}/financial-plan", json=body
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 43

    p3 = next(i for i in data if i["period_number"] == 3)
    assert Decimal(p3["capex"]) == Decimal("15000000")
    p13 = next(i for i in data if i["period_number"] == 13)
    assert Decimal(p13["capex"]) == Decimal("5440000")
    assert Decimal(p13["opex"]) == Decimal("320000")
    p37 = next(i for i in data if i["period_number"] == 37)
    assert Decimal(p37["opex"]) == Decimal("1500000")

    p1 = next(i for i in data if i["period_number"] == 1)
    assert Decimal(p1["capex"]) == Decimal("0")
    assert Decimal(p1["opex"]) == Decimal("0")

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
    project_id = await _create_project(auth_client)
    first = {"items": [{"period_number": 1, "capex": "1000", "opex": "0"}]}
    await auth_client.put(
        f"/api/projects/{project_id}/financial-plan", json=first
    )
    second = {"items": [{"period_number": 5, "capex": "2000", "opex": "0"}]}
    resp = await auth_client.put(
        f"/api/projects/{project_id}/financial-plan", json=second
    )
    data = resp.json()
    p1 = next(i for i in data if i["period_number"] == 1)
    assert Decimal(p1["capex"]) == Decimal("0")
    p5 = next(i for i in data if i["period_number"] == 5)
    assert Decimal(p5["capex"]) == Decimal("2000")

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
    project_id = await _create_project(auth_client)
    await auth_client.put(
        f"/api/projects/{project_id}/financial-plan",
        json={"items": [{"period_number": 1, "capex": "1000", "opex": "0"}]},
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
    """period_number 1 → M1, period_number 37 → первый yearly (Y4)."""
    project_id = await _create_project(auth_client)
    await auth_client.put(
        f"/api/projects/{project_id}/financial-plan",
        json={
            "items": [
                {"period_number": 1,  "capex": "100", "opex": "0"},
                {"period_number": 37, "capex": "400", "opex": "0"},
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
    by_pn = {p.period_number: (plan, p) for plan, p in rows}
    assert by_pn[1][1].model_year == 1
    assert by_pn[1][0].capex == Decimal("100")
    assert by_pn[37][1].model_year == 4
    assert by_pn[37][0].capex == Decimal("400")


async def test_put_plan_rejects_duplicate_period_numbers(
    auth_client: AsyncClient,
) -> None:
    project_id = await _create_project(auth_client)
    resp = await auth_client.put(
        f"/api/projects/{project_id}/financial-plan",
        json={
            "items": [
                {"period_number": 1, "capex": "100", "opex": "0"},
                {"period_number": 1, "capex": "200", "opex": "0"},
            ]
        },
    )
    assert resp.status_code == 422


async def test_put_plan_unauthorized(client: AsyncClient) -> None:
    resp = await client.put(
        "/api/projects/1/financial-plan", json={"items": []}
    )
    assert resp.status_code == 401


# ============================================================
# OPEX/CAPEX items breakdown
# ============================================================


async def test_get_plan_returns_empty_items_by_default(
    auth_client: AsyncClient,
) -> None:
    project_id = await _create_project(auth_client)
    resp = await auth_client.get(f"/api/projects/{project_id}/financial-plan")
    assert resp.status_code == 200
    for item in resp.json():
        assert item["opex_items"] == []
        assert item["capex_items"] == []


async def test_put_plan_with_opex_items_auto_sums(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    project_id = await _create_project(auth_client)
    body = {
        "items": [
            {
                "period_number": 1,
                "capex": "100000",
                "opex": "999",
                "opex_items": [
                    {"name": "Аренда", "amount": "200000"},
                    {"name": "ЗП", "amount": "500000"},
                ],
            },
        ]
    }
    resp = await auth_client.put(
        f"/api/projects/{project_id}/financial-plan", json=body
    )
    assert resp.status_code == 200
    data = resp.json()
    p1 = next(i for i in data if i["period_number"] == 1)
    assert Decimal(p1["opex"]) == Decimal("700000")
    assert len(p1["opex_items"]) == 2

    opex_rows = (await db_session.scalars(select(OpexItem))).all()
    assert len(list(opex_rows)) == 2


async def test_put_plan_with_capex_items_auto_sums(
    auth_client: AsyncClient,
) -> None:
    project_id = await _create_project(auth_client)
    body = {
        "items": [
            {
                "period_number": 3,
                "capex": "999",
                "opex": "0",
                "capex_items": [
                    {"category": "molds", "name": "Молды партия 1", "amount": "10000000"},
                    {"category": "line",  "name": "Линия розлива",   "amount": "5000000"},
                ],
            },
        ]
    }
    resp = await auth_client.put(
        f"/api/projects/{project_id}/financial-plan", json=body
    )
    assert resp.status_code == 200
    p3 = next(i for i in resp.json() if i["period_number"] == 3)
    assert Decimal(p3["capex"]) == Decimal("15000000")
    assert len(p3["capex_items"]) == 2


async def test_put_plan_replace_clears_old_items(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    project_id = await _create_project(auth_client)
    first = {
        "items": [
            {
                "period_number": 1,
                "capex": "0",
                "opex_items": [
                    {"name": "Аренда", "amount": "100000"},
                    {"name": "ЗП", "amount": "200000"},
                ],
            },
        ]
    }
    await auth_client.put(
        f"/api/projects/{project_id}/financial-plan", json=first
    )
    second = {
        "items": [
            {
                "period_number": 1,
                "capex": "0",
                "opex_items": [
                    {"name": "Новая", "amount": "50000"},
                ],
            },
        ]
    }
    resp = await auth_client.put(
        f"/api/projects/{project_id}/financial-plan", json=second
    )
    p1 = next(i for i in resp.json() if i["period_number"] == 1)
    assert Decimal(p1["opex"]) == Decimal("50000")
    assert len(p1["opex_items"]) == 1

    opex_rows = (await db_session.scalars(select(OpexItem))).all()
    assert len(list(opex_rows)) == 1
