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


# ============================================================
# 4.5.1 Контент паспорта (16 scalar + 5 JSONB полей)
# ============================================================


async def test_create_project_without_content_fields_returns_nulls(
    auth_client: AsyncClient,
) -> None:
    """Backward compat: проект без content fields → они NULL в response."""
    resp = await auth_client.post("/api/projects", json=VALID_BODY)
    assert resp.status_code == 201
    data = resp.json()
    # Все 16 scalar полей nullable, без значений = None
    assert data["description"] is None
    assert data["gate_stage"] is None
    assert data["passport_date"] is None
    assert data["project_owner"] is None
    assert data["project_goal"] is None
    assert data["innovation_type"] is None
    assert data["growth_opportunity"] is None
    assert data["concept_text"] is None
    assert data["target_audience"] is None
    assert data["executive_summary"] is None
    # JSONB
    assert data["risks"] is None
    assert data["validation_tests"] is None
    assert data["function_readiness"] is None
    assert data["roadmap_tasks"] is None
    assert data["approvers"] is None


async def test_create_project_with_full_content_fields(
    auth_client: AsyncClient,
) -> None:
    """POST /api/projects с полным набором content полей → 201 + сохранены."""
    body = {
        **VALID_BODY,
        "name": "Test ELEKTRA passport",
        "description": "Спортивная вода с электролитами",
        "gate_stage": "G4",
        "passport_date": "2025-09-22",
        "project_owner": "Иван Иванов",
        "project_goal": "Заявить первыми новый сегмент спортивной воды",
        "innovation_type": "Новая категория",
        "geography": "РФ (потенциально СНГ)",
        "production_type": "Копакинг",
        "growth_opportunity": "Сегмент воды с электролитами растёт",
        "concept_text": "Запустить спортивную воду с электролитами",
        "rationale": "Спорт напитки в мире — растущая категория",
        "idea_short": "Восполнить силы через полезную энергию",
        "target_audience": "Активные люди, спорт, танцы",
        "replacement_target": "Бутилированная вода и энергетики",
        "technology": "Холодный розлив",
        "rnd_progress": "Рецепт разработан и утверждён",
        "executive_summary": "(будет AI-generated в Phase 7)",
        "risks": [
            "Скорость конкурентов",
            "Утечка инфо по концепции",
            "Отсутствие мощностей АОН",
        ],
        "validation_tests": {
            "concept_test": {"score": 0.86, "notes": "86% попробуют"},
            "naming_test": {"score": 0.50, "notes": ">50 нравится"},
            "design_test": {"score": 0.60, "notes": "60% нравится"},
            "product_test": {"score": 1.0, "notes": "Лидирует с бенчмарком"},
            "price_test": {"score": 0.45, "notes": "45% считают приемлемой"},
        },
        "function_readiness": {
            "МАРКЕТИНГ": {"status": "yellow", "notes": "Разработка комстрата"},
            "RND": {"status": "green", "notes": "Рецепт готов"},
            "АНАЛИТИКА": {"status": "green", "notes": ""},
            "ФИНАНСЫ": {"status": "yellow", "notes": "Источник молдов"},
            "ДТР": {"status": "green", "notes": ""},
            "ЮРИДИЧЕСКИЕ": {"status": "green", "notes": ""},
            "ЗАКУПКИ": {"status": "green", "notes": ""},
            "ПРОИЗВОДСТВО": {"status": "yellow", "notes": "Тест ГП Мегапак"},
        },
        "roadmap_tasks": [
            {
                "name": "Согласовать копакера",
                "start_date": "2024-12-01",
                "end_date": "2024-12-26",
                "status": "done",
                "owner": "Закупки",
            },
            {
                "name": "Первый розлив ПЭТ 0,5",
                "start_date": "2025-03-01",
                "end_date": "2025-03-06",
                "status": "done",
                "owner": "Производство",
            },
        ],
        "approvers": [
            {
                "metric": "Уровень инфляции",
                "approver": "А.Даниловский",
                "source": "Экспертное мнение",
            },
            {
                "metric": "Дистрибуция",
                "approver": "А.Бубнов",
                "source": "Nielsen",
            },
        ],
    }
    resp = await auth_client.post("/api/projects", json=body)
    assert resp.status_code == 201, resp.text
    data = resp.json()

    # Scalar поля
    assert data["description"] == "Спортивная вода с электролитами"
    assert data["gate_stage"] == "G4"
    assert data["passport_date"] == "2025-09-22"
    assert data["project_owner"] == "Иван Иванов"
    assert data["innovation_type"] == "Новая категория"
    assert "Активные люди" in data["target_audience"]

    # JSONB roundtrip
    assert data["risks"] == [
        "Скорость конкурентов",
        "Утечка инфо по концепции",
        "Отсутствие мощностей АОН",
    ]
    assert data["validation_tests"]["concept_test"]["score"] == 0.86
    assert data["function_readiness"]["RND"]["status"] == "green"
    assert len(data["roadmap_tasks"]) == 2
    assert data["roadmap_tasks"][0]["name"] == "Согласовать копакера"
    assert data["approvers"][1]["approver"] == "А.Бубнов"


async def test_patch_project_content_fields(
    auth_client: AsyncClient,
) -> None:
    """PATCH /api/projects/{id} с content fields → обновляет, остальное не трогает."""
    create = await auth_client.post("/api/projects", json=VALID_BODY)
    project_id = create.json()["id"]

    # Patch только content поля
    patch_body = {
        "gate_stage": "G3",
        "project_goal": "Цель: обновлённая",
        "risks": ["Риск 1", "Риск 2"],
    }
    resp = await auth_client.patch(
        f"/api/projects/{project_id}", json=patch_body
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["gate_stage"] == "G3"
    assert data["project_goal"] == "Цель: обновлённая"
    assert data["risks"] == ["Риск 1", "Риск 2"]
    # Остальные поля не изменились
    assert data["name"] == "GORJI+ NEW NRG"
    assert data["description"] is None  # не было — осталось None


async def test_invalid_gate_stage_returns_422(
    auth_client: AsyncClient,
) -> None:
    """Pydantic Literal валидация: gate_stage='G99' → 422."""
    body = {**VALID_BODY, "gate_stage": "G99"}
    resp = await auth_client.post("/api/projects", json=body)
    assert resp.status_code == 422


async def test_gate_stage_check_constraint_db_level(
    db_session: AsyncSession,
) -> None:
    """DB CHECK constraint защищает от прямого raw INSERT с invalid gate_stage.

    Это второй уровень валидации (после Pydantic). Если кто-то напишет
    raw SQL или ORM с обходом валидации — БД отбросит с IntegrityError.

    Используем savepoint pattern (паттерн #2 из CLAUDE.md): begin_nested
    создаёт savepoint, после IntegrityError outer-транзакция остаётся
    живой для остальных тестов.
    """
    from datetime import date as _date

    from sqlalchemy.exc import IntegrityError

    try:
        async with db_session.begin_nested():
            project = Project(
                name="DB constraint test",
                start_date=_date(2025, 1, 1),
                gate_stage="INVALID",  # обходим Pydantic
            )
            db_session.add(project)
            await db_session.flush()
        # Если flush прошёл — CHECK не сработал, тест fail
        assert False, "CHECK constraint должен был сработать"
    except IntegrityError as exc:
        # Ожидаемо: PostgreSQL отверг INSERT
        assert "ck_projects_gate_stage" in str(exc) or "check" in str(exc).lower()
