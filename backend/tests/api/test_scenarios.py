"""Scenarios API tests (задача 1.6).

Сценарии создаются автоматически при POST /api/projects (3 шт.).
Здесь тестируется их чтение, обновление дельт и эндпоинт результатов
расчёта (который вернёт 404 пока расчётное ядро не реализовано в Фазе 2).
"""
from datetime import datetime, timezone
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    PeriodScope,
    Scenario,
    ScenarioResult,
    ScenarioType,
)


PROJECT_BODY = {
    "name": "Scenarios test project",
    "start_date": "2025-01-01",
}


async def _create_project(client: AsyncClient) -> int:
    return (await client.post("/api/projects", json=PROJECT_BODY)).json()["id"]


async def _get_base_scenario_id(
    db_session: AsyncSession, project_id: int
) -> int:
    scenario = await db_session.scalar(
        select(Scenario).where(
            Scenario.project_id == project_id,
            Scenario.type == ScenarioType.BASE,
        )
    )
    assert scenario is not None
    return scenario.id


# ============================================================
# 1. GET /api/projects/{id}/scenarios → 3 сценария в порядке Base → Cons → Aggr
# ============================================================


async def test_list_project_scenarios_returns_three_in_order(
    auth_client: AsyncClient,
) -> None:
    project_id = await _create_project(auth_client)

    resp = await auth_client.get(f"/api/projects/{project_id}/scenarios")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    types = [s["type"] for s in data]
    assert types == ["base", "conservative", "aggressive"]


# ============================================================
# 2. GET без auth → 401
# ============================================================


async def test_list_scenarios_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/projects/1/scenarios")
    assert resp.status_code == 401


# ============================================================
# 3. GET для несуществующего проекта → 404
# ============================================================


async def test_list_scenarios_unknown_project_returns_404(
    auth_client: AsyncClient,
) -> None:
    resp = await auth_client.get("/api/projects/99999/scenarios")
    assert resp.status_code == 404


# ============================================================
# 4. GET /api/scenarios/{id} → 200
# ============================================================


async def test_get_single_scenario(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    project_id = await _create_project(auth_client)
    scenario_id = await _get_base_scenario_id(db_session, project_id)

    resp = await auth_client.get(f"/api/scenarios/{scenario_id}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == scenario_id
    assert data["type"] == "base"
    assert data["project_id"] == project_id
    # Default дельты при создании
    assert Decimal(data["delta_nd"]) == Decimal("0")


# ============================================================
# 5. PATCH /api/scenarios/{id} — обновить дельты + notes
# ============================================================


async def test_patch_scenario_deltas(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    project_id = await _create_project(auth_client)
    # Берём Conservative для отрицательных дельт
    cons_scenario = await db_session.scalar(
        select(Scenario).where(
            Scenario.project_id == project_id,
            Scenario.type == ScenarioType.CONSERVATIVE,
        )
    )
    assert cons_scenario is not None

    resp = await auth_client.patch(
        f"/api/scenarios/{cons_scenario.id}",
        json={
            "delta_nd": "-0.10",
            "delta_offtake": "-0.15",
            "notes": "Кризисный сценарий: ND и offtake ниже Base на 10-15%",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert Decimal(data["delta_nd"]) == Decimal("-0.10")
    assert Decimal(data["delta_offtake"]) == Decimal("-0.15")
    assert data["notes"].startswith("Кризисный")
    # delta_opex не передавали — должна остаться 0
    assert Decimal(data["delta_opex"]) == Decimal("0")
    # type не изменился
    assert data["type"] == "conservative"


# ============================================================
# 6. PATCH с поданным type — игнорируется (нет в ScenarioUpdate)
# ============================================================


async def test_patch_scenario_ignores_type_field(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    project_id = await _create_project(auth_client)
    scenario_id = await _get_base_scenario_id(db_session, project_id)

    resp = await auth_client.patch(
        f"/api/scenarios/{scenario_id}",
        json={"type": "aggressive", "delta_nd": "0.15"},
    )

    assert resp.status_code == 200
    data = resp.json()
    # delta_nd обновлён
    assert Decimal(data["delta_nd"]) == Decimal("0.15")
    # type НЕ изменился (поле проигнорировано Pydantic'ом)
    assert data["type"] == "base"


# ============================================================
# 7. PATCH с невалидной дельтой (>1) → 422
# ============================================================


async def test_patch_scenario_delta_out_of_range_returns_422(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    project_id = await _create_project(auth_client)
    scenario_id = await _get_base_scenario_id(db_session, project_id)

    resp = await auth_client.patch(
        f"/api/scenarios/{scenario_id}",
        json={"delta_nd": "1.5"},
    )
    assert resp.status_code == 422


# ============================================================
# 8. GET /api/scenarios/{id}/results без расчёта → 404 + actionable
# ============================================================


async def test_get_results_before_calculation_returns_404(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    project_id = await _create_project(auth_client)
    scenario_id = await _get_base_scenario_id(db_session, project_id)

    resp = await auth_client.get(f"/api/scenarios/{scenario_id}/results")

    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert "not been calculated" in detail
    assert "recalculate" in detail
    assert "task 2.4" in detail


# ============================================================
# 9. GET /api/scenarios/{id}/results → 3 scope в правильном порядке
# ============================================================


async def test_get_results_returns_three_scopes_in_order(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    project_id = await _create_project(auth_client)
    scenario_id = await _get_base_scenario_id(db_session, project_id)

    # Создаём 3 ScenarioResult вручную (расчётное ядро в Фазе 2 будет
    # делать это автоматически). В нарушение алфавитного порядка
    # вставляем Y1Y10 первым, чтобы убедиться в работе сортировки.
    now = datetime.now(timezone.utc)
    for scope, npv in [
        (PeriodScope.Y1Y10, Decimal("79983059.00")),
        (PeriodScope.Y1Y3, Decimal("-11593312.00")),
        (PeriodScope.Y1Y5, Decimal("27251350.00")),
    ]:
        db_session.add(
            ScenarioResult(
                scenario_id=scenario_id,
                period_scope=scope,
                npv=npv,
                go_no_go=(npv > 0),
                calculated_at=now,
            )
        )
    await db_session.flush()

    resp = await auth_client.get(f"/api/scenarios/{scenario_id}/results")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    # Должен быть порядок Y1Y3 → Y1Y5 → Y1Y10 (по бизнес-смыслу)
    scopes = [r["period_scope"] for r in data]
    assert scopes == ["y1y3", "y1y5", "y1y10"]
    # Эталонные значения NPV из плана задачи 2.3 (для GORJI+ референс)
    assert Decimal(data[0]["npv"]) == Decimal("-11593312.00")
    assert Decimal(data[1]["npv"]) == Decimal("27251350.00")
    assert Decimal(data[2]["npv"]) == Decimal("79983059.00")
    assert data[0]["go_no_go"] is False
    assert data[2]["go_no_go"] is True
