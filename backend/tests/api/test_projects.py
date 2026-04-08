"""Projects API tests (задача 1.2).

Покрывает критерии:
  - CRUD работает, данные персистируются
  - При создании проекта автоматически создаются 3 сценария
  - Параметры (wacc, tax_rate, wc_rate, vat_rate) сохраняются корректно
  - Soft delete: deleted проект не виден в list/get, но физически есть
  - Все маршруты защищены JWT

Замечание о сравнении Decimal: PostgreSQL возвращает Numeric(8,6) как
"0.190000" (с trailing нулями до объявленной точности), Pydantic v2
сохраняет это в JSON как есть. Тесты сравнивают через Decimal(), а не
строки — семантическое равенство, без хрупкого форматирования.
"""
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, Scenario, ScenarioType


VALID_BODY = {
    "name": "GORJI+ NEW NRG",
    "start_date": "2025-01-01",
    "horizon_years": 10,
    "wacc": "0.19",
    "tax_rate": "0.20",
    "wc_rate": "0.12",
    "vat_rate": "0.20",
    "currency": "RUB",
}


# ============================================================
# 1. POST /api/projects (auth) → 201 + создан + 3 scenarios
# ============================================================


async def test_create_project_creates_three_scenarios(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    resp = await auth_client.post("/api/projects", json=VALID_BODY)

    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "GORJI+ NEW NRG"
    assert Decimal(data["wacc"]) == Decimal("0.19")
    assert Decimal(data["wc_rate"]) == Decimal("0.12")
    project_id = data["id"]

    # Проверяем что сценарии созданы в БД
    scenarios = (
        await db_session.scalars(
            select(Scenario).where(Scenario.project_id == project_id)
        )
    ).all()
    assert len(scenarios) == 3
    types = {s.type for s in scenarios}
    assert types == {
        ScenarioType.BASE,
        ScenarioType.CONSERVATIVE,
        ScenarioType.AGGRESSIVE,
    }


# ============================================================
# 2. POST /api/projects (no auth) → 401
# ============================================================


async def test_create_project_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/api/projects", json=VALID_BODY)
    assert resp.status_code == 401


# ============================================================
# 3. POST с невалидным телом → 422
# ============================================================


async def test_create_project_invalid_body_returns_422(
    auth_client: AsyncClient,
) -> None:
    bad = {**VALID_BODY, "wacc": "1.5"}  # >1, нарушает Field(le=1)
    resp = await auth_client.post("/api/projects", json=bad)
    assert resp.status_code == 422


# ============================================================
# 4. POST с минимальным телом — defaults применяются
# ============================================================


async def test_create_project_minimal_body_uses_defaults(
    auth_client: AsyncClient,
) -> None:
    minimal = {"name": "Minimal", "start_date": "2026-01-01"}
    resp = await auth_client.post("/api/projects", json=minimal)

    assert resp.status_code == 201
    data = resp.json()
    assert data["horizon_years"] == 10
    assert Decimal(data["wacc"]) == Decimal("0.19")
    assert Decimal(data["wc_rate"]) == Decimal("0.12")   # ADR-CE-02 default
    assert Decimal(data["tax_rate"]) == Decimal("0.20")  # ADR-CE-04 default
    assert data["currency"] == "RUB"


# ============================================================
# 5. GET /api/projects → список с базовыми KPI = null
# ============================================================


async def test_list_projects_returns_kpi_null_until_calculated(
    auth_client: AsyncClient,
) -> None:
    await auth_client.post("/api/projects", json=VALID_BODY)

    resp = await auth_client.get("/api/projects")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    item = data[0]
    assert item["name"] == "GORJI+ NEW NRG"
    # KPI не рассчитаны (Фаза 2)
    assert item["npv_y1y10"] is None
    assert item["irr_y1y10"] is None
    assert item["go_no_go"] is None


async def test_list_projects_returns_kpi_after_calculation(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    """После сохранения ScenarioResult (Base, Y1Y10) — KPI попадают в list.

    Имитируем запись результатов через прямой INSERT, не через recalculate
    Celery task — этот тест проверяет JOIN в list_projects, не оркестратор.
    """
    from app.models import PeriodScope, ScenarioResult

    create_resp = await auth_client.post("/api/projects", json=VALID_BODY)
    project_id = create_resp.json()["id"]

    base = await db_session.scalar(
        select(Scenario).where(
            Scenario.project_id == project_id,
            Scenario.type == ScenarioType.BASE,
        )
    )
    db_session.add(
        ScenarioResult(
            scenario_id=base.id,
            period_scope=PeriodScope.Y1Y10,
            npv=Decimal("79983058.92"),
            irr=Decimal("0.786343"),
            go_no_go=True,
        )
    )
    await db_session.flush()

    resp = await auth_client.get("/api/projects")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert Decimal(items[0]["npv_y1y10"]) == Decimal("79983058.92")
    assert Decimal(items[0]["irr_y1y10"]) == Decimal("0.786343")
    assert items[0]["go_no_go"] is True


# ============================================================
# 6. GET /api/projects/{id} → 200 + detail
# ============================================================


async def test_get_project_by_id(auth_client: AsyncClient) -> None:
    create_resp = await auth_client.post("/api/projects", json=VALID_BODY)
    project_id = create_resp.json()["id"]

    resp = await auth_client.get(f"/api/projects/{project_id}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == project_id
    assert data["name"] == "GORJI+ NEW NRG"


# ============================================================
# 7. GET /api/projects/{id} (несуществующий) → 404
# ============================================================


async def test_get_project_nonexistent_returns_404(
    auth_client: AsyncClient,
) -> None:
    resp = await auth_client.get("/api/projects/99999")
    assert resp.status_code == 404


# ============================================================
# 8. PATCH /api/projects/{id} — обновить name
# ============================================================


async def test_patch_project_name(auth_client: AsyncClient) -> None:
    create_resp = await auth_client.post("/api/projects", json=VALID_BODY)
    project_id = create_resp.json()["id"]

    resp = await auth_client.patch(
        f"/api/projects/{project_id}",
        json={"name": "GORJI+ Renamed"},
    )

    assert resp.status_code == 200
    assert resp.json()["name"] == "GORJI+ Renamed"
    # Другие поля не изменились
    assert Decimal(resp.json()["wacc"]) == Decimal("0.19")


# ============================================================
# 9. PATCH partial — только wacc, остальное не трогать
# ============================================================


async def test_patch_project_partial_keeps_other_fields(
    auth_client: AsyncClient,
) -> None:
    create_resp = await auth_client.post("/api/projects", json=VALID_BODY)
    project_id = create_resp.json()["id"]

    resp = await auth_client.patch(
        f"/api/projects/{project_id}",
        json={"wacc": "0.15"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert Decimal(data["wacc"]) == Decimal("0.15")
    assert data["name"] == "GORJI+ NEW NRG"
    assert Decimal(data["wc_rate"]) == Decimal("0.12")


# ============================================================
# 10. DELETE /api/projects/{id} → 204 + soft delete
# ============================================================


async def test_delete_project_soft_deletes(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    create_resp = await auth_client.post("/api/projects", json=VALID_BODY)
    project_id = create_resp.json()["id"]

    resp = await auth_client.delete(f"/api/projects/{project_id}")
    assert resp.status_code == 204

    # Проверяем что физически проект остался, deleted_at проставлен
    project = await db_session.get(Project, project_id)
    assert project is not None
    assert project.deleted_at is not None


# ============================================================
# 11. GET /api/projects/{id} после DELETE → 404
# ============================================================


async def test_deleted_project_not_returned_by_get(
    auth_client: AsyncClient,
) -> None:
    create_resp = await auth_client.post("/api/projects", json=VALID_BODY)
    project_id = create_resp.json()["id"]

    await auth_client.delete(f"/api/projects/{project_id}")

    resp = await auth_client.get(f"/api/projects/{project_id}")
    assert resp.status_code == 404


# ============================================================
# 12. GET /api/projects после DELETE → удалённый не в списке
# ============================================================


async def test_deleted_project_not_in_list(auth_client: AsyncClient) -> None:
    # Создаём 2 проекта
    create1 = await auth_client.post("/api/projects", json=VALID_BODY)
    create2 = await auth_client.post(
        "/api/projects",
        json={**VALID_BODY, "name": "Survivor"},
    )
    deleted_id = create1.json()["id"]
    survivor_id = create2.json()["id"]

    # Удаляем первый
    await auth_client.delete(f"/api/projects/{deleted_id}")

    # Список содержит только Survivor
    resp = await auth_client.get("/api/projects")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == survivor_id
    assert data[0]["name"] == "Survivor"
