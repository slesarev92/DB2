"""Integration tests для calculation_service + Celery task + recalculate API.

Стратегия:
- calculation_service.build_line_inputs тестируется на реальной БД с
  засеянным минимальным проектом (1 SKU, 1 канал, 43 PeriodValue).
- run_project_pipeline вызывается напрямую из теста через build_line_inputs.
- POST /api/projects/{id}/recalculate тестируется в **eager mode**:
  Celery task выполняется синхронно в том же процессе, без брокера.
  Это стандартная практика для тестов — реальный воркер работает
  изолированно в docker-compose service `celery-worker`, его не дёргаем
  из pytest.
- GET /api/tasks/{task_id} тоже тестируется через eager (task_id есть,
  результат сохранён в backend).

Conftest patches `celery_app.conf.task_always_eager = True` на сессионном
уровне через fixture autouse.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.pipeline import run_project_pipeline
from app.models import (
    BOMItem,
    Channel,
    Period,
    PeriodValue,
    PeriodType,
    Project,
    ProjectFinancialPlan,
    ProjectSKU,
    ProjectSKUChannel,
    SKU,
    Scenario,
    ScenarioResult,
    ScenarioType,
    SourceType,
)
from app.models.base import PeriodScope
from app.services.calculation_service import (
    NoLinesError,
    ProjectNotFoundError,
    build_line_inputs,
    calculate_all_scenarios,
    calculate_and_save_scenario,
)


# ============================================================
# Celery eager mode для всех тестов в этом модуле
# ============================================================


@pytest.fixture(autouse=True)
def celery_eager_mode():
    """Переводит Celery в eager mode на время теста.

    task.delay() выполняется синхронно в том же процессе, не идёт через
    Redis. Это позволяет проверить wiring API → task → service без
    реального broker'а.

    `task_store_eager_result=True` подавляет RuntimeWarning от Celery
    при опросе AsyncResult в eager mode.
    """
    from app.worker import celery_app

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    celery_app.conf.task_store_eager_result = True
    yield
    celery_app.conf.task_always_eager = False
    celery_app.conf.task_eager_propagates = False
    celery_app.conf.task_store_eager_result = False


# ============================================================
# Helpers — построение минимального проекта со всеми 43 PeriodValue
# ============================================================


async def _seed_minimal_project(
    db_session: AsyncSession,
    *,
    nd: float = 0.001,
    offtake: float = 1.0,
    shelf_price: float = 10.0,
) -> tuple[int, int, int, int]:
    """Создаёт project + sku + project_sku + bom + project_sku_channel +
    43 PeriodValue (predict-слой) для base сценария.

    Возвращает (project_id, base_scenario_id, psk_id, psk_channel_id).
    """
    # 1. Project (создаст 3 сценария автоматически через create_project)
    from app.schemas.project import ProjectCreate
    from app.services.project_service import create_project

    project = await create_project(
        db_session,
        ProjectCreate(name="Calc test project", start_date="2025-01-01"),
        created_by=None,
    )
    await db_session.flush()

    # 2. SKU
    sku = SKU(brand="Gorji", name="Calc test SKU", volume_l=Decimal("0.5"))
    db_session.add(sku)
    await db_session.flush()

    # 3. ProjectSKU
    psk = ProjectSKU(
        project_id=project.id,
        sku_id=sku.id,
        production_cost_rate=Decimal("0.10"),
        ca_m_rate=Decimal("0.16"),
        marketing_rate=Decimal("0.02"),
    )
    db_session.add(psk)
    await db_session.flush()

    # 4. BOM (один компонент)
    bom = BOMItem(
        project_sku_id=psk.id,
        ingredient_name="Test material",
        quantity_per_unit=Decimal("1.0"),
        loss_pct=Decimal("0"),
        price_per_unit=Decimal("10.0"),
    )
    db_session.add(bom)
    await db_session.flush()

    # 5. PSC (HM канал из засеянных)
    hm = await db_session.scalar(select(Channel).where(Channel.code == "HM"))
    assert hm is not None
    psc = ProjectSKUChannel(
        project_sku_id=psk.id,
        channel_id=hm.id,
        nd_target=Decimal("0.5"),
        offtake_target=Decimal("10.0"),
        channel_margin=Decimal("0.4"),
        promo_discount=Decimal("0.3"),
        promo_share=Decimal("1.0"),
        shelf_price_reg=Decimal(str(shelf_price)),
        logistics_cost_per_kg=Decimal("8.0"),
    )
    db_session.add(psc)
    await db_session.flush()

    # 6. Base scenario id
    base = await db_session.scalar(
        select(Scenario).where(
            Scenario.project_id == project.id,
            Scenario.type == ScenarioType.BASE,
        )
    )
    assert base is not None

    # 7. Все 43 PeriodValue с predict-слоем
    periods = (
        await db_session.scalars(select(Period).order_by(Period.period_number))
    ).all()
    assert len(periods) == 43

    for p in periods:
        db_session.add(
            PeriodValue(
                psk_channel_id=psc.id,
                scenario_id=base.id,
                period_id=p.id,
                source_type=SourceType.PREDICT,
                version_id=1,
                values={
                    "nd": nd,
                    "offtake": offtake,
                    "shelf_price": shelf_price,
                },
            )
        )
    await db_session.flush()

    return project.id, base.id, psk.id, psc.id


# ============================================================
# 1. build_line_inputs
# ============================================================


class TestBuildLineInputs:
    async def test_builds_one_input_for_one_psc(
        self, db_session: AsyncSession
    ):
        project_id, scenario_id, _, psc_id = await _seed_minimal_project(db_session)
        inputs = await build_line_inputs(db_session, project_id, scenario_id)

        assert len(inputs) == 1
        inp = inputs[0]
        assert inp.project_sku_channel_id == psc_id
        assert inp.scenario_id == scenario_id
        assert inp.period_count == 43
        # 36 monthly + 7 yearly
        assert sum(inp.period_is_monthly) == 36
        assert sum(1 for x in inp.period_is_monthly if not x) == 7
        # Параметры из БД
        assert inp.universe_outlets == 822  # HM seed
        assert inp.channel_margin == pytest.approx(0.4)
        assert inp.vat_rate == pytest.approx(0.20)  # default Project
        assert inp.wacc == pytest.approx(0.19)
        assert inp.wc_rate == pytest.approx(0.12)
        assert inp.bom_unit_cost == pytest.approx(10.0)  # 1 × 10 × (1+0)
        # Effective values из PeriodValue (default низкие — см. _seed_minimal_project)
        assert all(v == pytest.approx(0.001) for v in inp.nd)
        assert all(v == pytest.approx(1.0) for v in inp.offtake)

    async def test_project_not_found(self, db_session: AsyncSession):
        with pytest.raises(ProjectNotFoundError):
            await build_line_inputs(db_session, 999999, 1)

    async def test_no_lines_error(self, db_session: AsyncSession):
        """Проект без ProjectSKU → NoLinesError."""
        from app.schemas.project import ProjectCreate
        from app.services.project_service import create_project

        project = await create_project(
            db_session,
            ProjectCreate(name="Empty", start_date="2025-01-01"),
            created_by=None,
        )
        await db_session.flush()
        base = await db_session.scalar(
            select(Scenario).where(
                Scenario.project_id == project.id,
                Scenario.type == ScenarioType.BASE,
            )
        )
        with pytest.raises(NoLinesError):
            await build_line_inputs(db_session, project.id, base.id)

    async def test_scenario_delta_applied(self, db_session: AsyncSession):
        """Conservative scenario с delta_nd = -0.10 → ND × 0.90."""
        project_id, _, _, _ = await _seed_minimal_project(db_session)
        # Берём conservative и проставляем delta
        cons = await db_session.scalar(
            select(Scenario).where(
                Scenario.project_id == project_id,
                Scenario.type == ScenarioType.CONSERVATIVE,
            )
        )
        cons.delta_nd = Decimal("-0.10")
        await db_session.flush()

        # Создаём те же PeriodValue для conservative scenario, иначе
        # build_line_inputs увидит пустые ND.
        periods = (
            await db_session.scalars(select(Period).order_by(Period.period_number))
        ).all()
        # Берём psk_channel_id из base scenario PeriodValue
        psv = await db_session.scalar(select(PeriodValue).limit(1))
        assert psv is not None
        for p in periods:
            db_session.add(
                PeriodValue(
                    psk_channel_id=psv.psk_channel_id,
                    scenario_id=cons.id,
                    period_id=p.id,
                    source_type=SourceType.PREDICT,
                    version_id=1,
                    values={"nd": 0.001, "offtake": 1.0, "shelf_price": 10.0},
                )
            )
        await db_session.flush()

        inputs = await build_line_inputs(db_session, project_id, cons.id)
        # Все ND × 0.90 = 0.001 × 0.9 = 0.0009
        for v in inputs[0].nd:
            assert v == pytest.approx(0.0009, rel=1e-9)


# ============================================================
# 2. calculate_and_save_scenario
# ============================================================


class TestCalculateScenario:
    async def test_creates_3_results_per_scope(self, db_session: AsyncSession):
        project_id, scenario_id, _, _ = await _seed_minimal_project(db_session)
        results = await calculate_and_save_scenario(
            db_session, project_id, scenario_id
        )

        assert len(results) == 3
        scopes = {r.period_scope for r in results}
        assert scopes == {PeriodScope.Y1Y3, PeriodScope.Y1Y5, PeriodScope.Y1Y10}

    async def test_results_have_kpi_values(self, db_session: AsyncSession):
        project_id, scenario_id, _, _ = await _seed_minimal_project(db_session)
        results = await calculate_and_save_scenario(
            db_session, project_id, scenario_id
        )

        # Хотя бы один scope имеет non-None NPV/IRR/payback
        y10 = next(r for r in results if r.period_scope == PeriodScope.Y1Y10)
        assert y10.npv is not None
        # IRR может быть None (если все cashflows одного знака — но не наш случай)
        # ROI — должен быть Decimal
        assert y10.roi is not None
        assert y10.contribution_margin is not None
        assert y10.go_no_go is not None  # bool, не None

    async def test_no_financial_plan_means_zero_capex(
        self, db_session: AsyncSession
    ):
        """Без записей в project_financial_plans → FCF == OCF (без оттока).

        Это базовое поведение MVP — сейчас тесты не создают plan,
        и FCF строго равен OCF.
        """
        from app.engine.pipeline import run_project_pipeline
        from app.services.calculation_service import (
            _load_period_catalog,
            _load_project_financial_plan,
            build_line_inputs,
        )

        project_id, scenario_id, _, _ = await _seed_minimal_project(db_session)

        # Plan пустой → пустые tuples
        sorted_periods, _ = await _load_period_catalog(db_session)
        capex, opex = await _load_project_financial_plan(
            db_session, project_id, sorted_periods
        )
        assert capex == ()
        assert opex == ()

        line_inputs = await build_line_inputs(db_session, project_id, scenario_id)
        agg = run_project_pipeline(
            line_inputs, project_capex=capex, project_opex=opex
        )

        # FCF = OCF в каждом периоде (capex/opex не применены)
        for t in range(len(agg.free_cash_flow)):
            assert agg.free_cash_flow[t] == pytest.approx(
                agg.operating_cash_flow[t]
            )

    async def test_financial_plan_capex_reduces_fcf(
        self, db_session: AsyncSession
    ):
        """С записью CAPEX в plan → FCF на этот период уменьшается на capex."""
        from app.engine.pipeline import run_project_pipeline
        from app.services.calculation_service import (
            _load_period_catalog,
            _load_project_financial_plan,
            build_line_inputs,
        )

        project_id, scenario_id, _, _ = await _seed_minimal_project(db_session)

        # Создаём plan: 5000₽ capex на period_number=1 (M1)
        m1 = await db_session.scalar(
            select(Period).where(Period.period_number == 1)
        )
        db_session.add(
            ProjectFinancialPlan(
                project_id=project_id,
                period_id=m1.id,
                capex=Decimal("5000"),
                opex=Decimal("0"),
            )
        )
        await db_session.flush()

        # Загрузка plan
        sorted_periods, _ = await _load_period_catalog(db_session)
        capex, opex = await _load_project_financial_plan(
            db_session, project_id, sorted_periods
        )
        assert len(capex) == 43
        assert capex[0] == 5000.0  # M1 = первый в sorted_periods
        assert all(c == 0.0 for c in capex[1:])
        assert opex == tuple([0.0] * 43)

        # Сравним FCF с и без plan
        line_inputs = await build_line_inputs(db_session, project_id, scenario_id)

        agg_with = run_project_pipeline(
            line_inputs, project_capex=capex, project_opex=opex
        )
        agg_without = run_project_pipeline(line_inputs)

        # FCF[0] меньше на 5000 при plan
        assert agg_with.free_cash_flow[0] == pytest.approx(
            agg_without.free_cash_flow[0] - 5000.0
        )
        # ICF[0] = -5000 при plan, 0 без
        assert agg_with.investing_cash_flow[0] == pytest.approx(-5000.0)
        assert agg_without.investing_cash_flow[0] == pytest.approx(0.0)

    async def test_financial_plan_opex_reduces_contribution(
        self, db_session: AsyncSession
    ):
        """С записью OPEX в plan → contribution и OCF на этот период уменьшаются."""
        from app.engine.pipeline import run_project_pipeline
        from app.services.calculation_service import (
            _load_period_catalog,
            _load_project_financial_plan,
            build_line_inputs,
        )

        project_id, scenario_id, _, _ = await _seed_minimal_project(db_session)

        m1 = await db_session.scalar(
            select(Period).where(Period.period_number == 1)
        )
        db_session.add(
            ProjectFinancialPlan(
                project_id=project_id,
                period_id=m1.id,
                capex=Decimal("0"),
                opex=Decimal("100"),
            )
        )
        await db_session.flush()

        sorted_periods, _ = await _load_period_catalog(db_session)
        capex, opex = await _load_project_financial_plan(
            db_session, project_id, sorted_periods
        )
        assert opex[0] == 100.0

        line_inputs = await build_line_inputs(db_session, project_id, scenario_id)
        agg_with = run_project_pipeline(
            line_inputs, project_capex=capex, project_opex=opex
        )
        agg_without = run_project_pipeline(line_inputs)

        # contribution[0] меньше на 100
        assert agg_with.contribution[0] == pytest.approx(
            agg_without.contribution[0] - 100.0
        )
        # OCF[0] меньше на 100 (через cm в OCF = cm + ΔWC + tax)
        assert agg_with.operating_cash_flow[0] == pytest.approx(
            agg_without.operating_cash_flow[0] - 100.0
        )

    async def test_load_plan_with_partial_periods(
        self, db_session: AsyncSession
    ):
        """Plan с записями только для части периодов → tuples длины 43,
        отсутствующие = 0."""
        from app.services.calculation_service import (
            _load_period_catalog,
            _load_project_financial_plan,
        )

        project_id, _, _, _ = await _seed_minimal_project(db_session)

        # Записи для period_number = 1, 5, 10
        for pn in [1, 5, 10]:
            p = await db_session.scalar(
                select(Period).where(Period.period_number == pn)
            )
            db_session.add(
                ProjectFinancialPlan(
                    project_id=project_id,
                    period_id=p.id,
                    capex=Decimal(str(pn * 1000)),
                    opex=Decimal("0"),
                )
            )
        await db_session.flush()

        sorted_periods, _ = await _load_period_catalog(db_session)
        capex, _ = await _load_project_financial_plan(
            db_session, project_id, sorted_periods
        )

        assert len(capex) == 43
        assert capex[0] == 1000.0   # period_number=1
        assert capex[4] == 5000.0   # period_number=5 → index 4
        assert capex[9] == 10000.0  # period_number=10 → index 9
        # Остальные нули
        assert sum(1 for c in capex if c != 0.0) == 3

    async def test_recalculate_replaces_old_results(
        self, db_session: AsyncSession
    ):
        project_id, scenario_id, _, _ = await _seed_minimal_project(db_session)

        # Первый прогон
        first = await calculate_and_save_scenario(
            db_session, project_id, scenario_id
        )
        first_ids = {r.id for r in first}

        # Второй прогон должен удалить старые и создать новые
        second = await calculate_and_save_scenario(
            db_session, project_id, scenario_id
        )
        second_ids = {r.id for r in second}

        assert first_ids.isdisjoint(second_ids)
        # Только 3 строки в БД
        all_results = (
            await db_session.scalars(
                select(ScenarioResult).where(ScenarioResult.scenario_id == scenario_id)
            )
        ).all()
        assert len(list(all_results)) == 3


# ============================================================
# 3. POST /api/projects/{id}/recalculate (eager mode)
# ============================================================


class TestRecalculateEndpoint:
    async def test_returns_task_id(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Endpoint возвращает 202 + task_id.

        Task'а **не запускаем** — мокируем `calculate_project_task.delay`.
        Причина: в eager mode реальный task создаёт свою AsyncSession через
        `async_session_maker`, которая НЕ привязана к тестовой транзакции
        (см. conftest.py — db_session работает на уровне connection, а не
        engine). Task попытается прочитать project из реальной БД и упадёт
        с ProjectNotFoundError, потому что test transaction не закоммичен.

        Полная проверка цепочки service → сохранение результатов покрыта
        в TestCalculateScenario через прямой вызов calculate_and_save_scenario
        на тестовой сессии.
        """
        project_id, _, _, _ = await _seed_minimal_project(db_session)

        # Mock task.delay() — возвращает stub с .id
        from unittest.mock import MagicMock

        from app.tasks import calculate_project as cp_module

        fake_result = MagicMock()
        fake_result.id = "test-task-id-12345"
        monkeypatch.setattr(
            cp_module.calculate_project_task,
            "delay",
            MagicMock(return_value=fake_result),
        )

        resp = await auth_client.post(f"/api/projects/{project_id}/recalculate")
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["task_id"] == "test-task-id-12345"
        assert body["project_id"] == project_id
        assert body["status"] == "PENDING"

    async def test_404_for_unknown_project(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/projects/999999/recalculate")
        assert resp.status_code == 404

    async def test_unauthorized(self, client: AsyncClient):
        resp = await client.post("/api/projects/1/recalculate")
        assert resp.status_code == 401


# ============================================================
# 4. GET /api/tasks/{task_id}
# ============================================================


class TestGetTaskStatus:
    async def test_pending_for_unknown_task(
        self, auth_client: AsyncClient
    ):
        # AsyncResult несуществующего task = PENDING (Celery так дизайнен)
        resp = await auth_client.get("/api/tasks/non-existent-id")
        assert resp.status_code == 200
        body = resp.json()
        assert body["task_id"] == "non-existent-id"
        assert body["status"] == "PENDING"

    async def test_unauthorized(self, client: AsyncClient):
        resp = await client.get("/api/tasks/some-id")
        assert resp.status_code == 401


# ============================================================
# Helper: клонирование PeriodValue из base в conservative/aggressive
# ============================================================


async def _clone_period_values_to_other_scenarios(
    db_session: AsyncSession, project_id: int
) -> None:
    """Без этого calculate_all_scenarios упадёт на conservative/aggressive."""
    base = await db_session.scalar(
        select(Scenario).where(
            Scenario.project_id == project_id,
            Scenario.type == ScenarioType.BASE,
        )
    )
    base_pvs = (
        await db_session.scalars(
            select(PeriodValue).where(PeriodValue.scenario_id == base.id)
        )
    ).all()

    other_scenarios = (
        await db_session.scalars(
            select(Scenario).where(
                Scenario.project_id == project_id,
                Scenario.type != ScenarioType.BASE,
            )
        )
    ).all()

    for sc in other_scenarios:
        for pv in base_pvs:
            db_session.add(
                PeriodValue(
                    psk_channel_id=pv.psk_channel_id,
                    scenario_id=sc.id,
                    period_id=pv.period_id,
                    source_type=pv.source_type,
                    version_id=1,
                    values=dict(pv.values),
                )
            )
    await db_session.flush()
