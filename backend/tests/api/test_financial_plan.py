"""Тесты GET/PUT /api/projects/{id}/financial-plan.

CAPEX/OPEX по годам проекта для pipeline. UI работает per-year,
backend хранит per-period — сервис делает маппинг.
B-19: добавлены тесты для opex_items breakdown.
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


# ============================================================
# B-19: OPEX breakdown (opex_items)
# ============================================================


async def test_get_plan_returns_empty_opex_items_by_default(
    auth_client: AsyncClient,
) -> None:
    """По умолчанию opex_items = [] для каждого года."""
    project_id = await _create_project(auth_client)
    resp = await auth_client.get(f"/api/projects/{project_id}/financial-plan")
    assert resp.status_code == 200
    for item in resp.json():
        assert item["opex_items"] == []


async def test_put_plan_with_opex_items_auto_sums(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    """PUT с opex_items → opex = sum(items), items сохраняются в БД."""
    project_id = await _create_project(auth_client)
    body = {
        "items": [
            {
                "year": 1,
                "capex": "100000",
                "opex": "999",  # должен быть игнорирован (items есть)
                "opex_items": [
                    {"name": "Листинги", "amount": "500000"},
                    {"name": "Запускной маркетинг", "amount": "320000"},
                ],
            },
        ]
    }
    resp = await auth_client.put(
        f"/api/projects/{project_id}/financial-plan", json=body
    )
    assert resp.status_code == 200
    data = resp.json()

    y1 = next(i for i in data if i["year"] == 1)
    # opex = sum of items, not the explicit 999
    assert Decimal(y1["opex"]) == Decimal("820000")
    assert len(y1["opex_items"]) == 2
    names = {oi["name"] for oi in y1["opex_items"]}
    assert names == {"Листинги", "Запускной маркетинг"}

    # Проверяем что в БД реально 2 OpexItem записи
    opex_rows = (
        await db_session.scalars(select(OpexItem))
    ).all()
    assert len(list(opex_rows)) == 2


async def test_put_plan_without_opex_items_backward_compat(
    auth_client: AsyncClient,
) -> None:
    """PUT без opex_items → opex = явное число (обратная совместимость)."""
    project_id = await _create_project(auth_client)
    body = {
        "items": [
            {"year": 2, "capex": "0", "opex": "750000"},
        ]
    }
    resp = await auth_client.put(
        f"/api/projects/{project_id}/financial-plan", json=body
    )
    assert resp.status_code == 200
    data = resp.json()

    y2 = next(i for i in data if i["year"] == 2)
    assert Decimal(y2["opex"]) == Decimal("750000")
    assert y2["opex_items"] == []


async def test_put_plan_replace_clears_old_opex_items(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Повторный PUT удаляет старые opex_items (CASCADE)."""
    project_id = await _create_project(auth_client)

    # Первый PUT с items
    first = {
        "items": [
            {
                "year": 1,
                "capex": "0",
                "opex_items": [
                    {"name": "Листинги", "amount": "100000"},
                    {"name": "Промо", "amount": "200000"},
                ],
            },
        ]
    }
    await auth_client.put(
        f"/api/projects/{project_id}/financial-plan", json=first
    )

    # Второй PUT — другие items
    second = {
        "items": [
            {
                "year": 1,
                "capex": "0",
                "opex_items": [
                    {"name": "Новая статья", "amount": "50000"},
                ],
            },
        ]
    }
    resp = await auth_client.put(
        f"/api/projects/{project_id}/financial-plan", json=second
    )
    data = resp.json()
    y1 = next(i for i in data if i["year"] == 1)
    assert Decimal(y1["opex"]) == Decimal("50000")
    assert len(y1["opex_items"]) == 1
    assert y1["opex_items"][0]["name"] == "Новая статья"

    # В БД должна быть ровно 1 OpexItem (старые удалены CASCADE)
    opex_rows = (
        await db_session.scalars(select(OpexItem))
    ).all()
    assert len(list(opex_rows)) == 1


async def test_put_plan_mixed_years_with_and_without_items(
    auth_client: AsyncClient,
) -> None:
    """Один год с opex_items, другой без — оба работают корректно."""
    project_id = await _create_project(auth_client)
    body = {
        "items": [
            {
                "year": 1,
                "capex": "0",
                "opex": "0",
                "opex_items": [
                    {"name": "Листинги", "amount": "400000"},
                ],
            },
            {
                "year": 2,
                "capex": "0",
                "opex": "600000",
                # no opex_items → manual opex
            },
        ]
    }
    resp = await auth_client.put(
        f"/api/projects/{project_id}/financial-plan", json=body
    )
    data = resp.json()

    y1 = next(i for i in data if i["year"] == 1)
    assert Decimal(y1["opex"]) == Decimal("400000")
    assert len(y1["opex_items"]) == 1

    y2 = next(i for i in data if i["year"] == 2)
    assert Decimal(y2["opex"]) == Decimal("600000")
    assert y2["opex_items"] == []


# ============================================================
# B.9b: schema contract tests for period_number
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
    # year field is gone; passing it should be ignored (Pydantic v2 default extra="ignore").
    item = FinancialPlanItem(period_number=1, year=1, capex="0", opex="0")
    assert not hasattr(item, "year")


def test_financial_plan_request_rejects_duplicate_period_number() -> None:
    with pytest.raises(ValidationError):
        FinancialPlanRequest(items=[
            FinancialPlanItem(period_number=1, capex="100", opex="0"),
            FinancialPlanItem(period_number=1, capex="200", opex="0"),
        ])


# ============================================================
# B.9b: list_plan_by_period returns 43 elements
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
