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
    nd_target: float = 0.001,
    offtake_target: float = 1.0,
    shelf_price: float = 10.0,
) -> tuple[int, int, int, int]:
    """Создаёт project + sku + project_sku + bom + project_sku_channel.

    PeriodValue с predict-слоем создаются **автоматически** через
    auto_fill в `create_psk_channel` (задача 2.5). Тестам не нужно
    ничего добавлять руками.

    Дефолтные nd_target/offtake_target/shelf_price умышленно низкие чтобы
    итоговый ROI помещался в `Numeric(10, 6)` Excel quirk D-06: при всех
    положительных FCF формула ROI вырождается в среднее, и большие
    абсолютные значения не помещаются в БД scale.

    Возвращает (project_id, base_scenario_id, psk_id, psk_channel_id).
    """
    from app.schemas.project import ProjectCreate
    from app.schemas.project_sku_channel import ProjectSKUChannelCreate
    from app.services.project_service import create_project
    from app.services.project_sku_channel_service import create_psk_channel

    # 1. Project (создаст 3 сценария автоматически)
    project = await create_project(
        db_session,
        ProjectCreate(name="Calc test project", start_date="2025-01-01"),
        created_by=None,
    )
    await db_session.flush()

    # 2. SKU + 3. ProjectSKU + 4. BOM
    sku = SKU(brand="Gorji", name="Calc test SKU", volume_l=Decimal("0.5"))
    db_session.add(sku)
    await db_session.flush()

    psk = ProjectSKU(
        project_id=project.id,
        sku_id=sku.id,
        production_cost_rate=Decimal("0.10"),
    )
    db_session.add(psk)
    await db_session.flush()

    bom = BOMItem(
        project_sku_id=psk.id,
        ingredient_name="Test material",
        quantity_per_unit=Decimal("1.0"),
        loss_pct=Decimal("0"),
        price_per_unit=Decimal("10.0"),
    )
    db_session.add(bom)
    await db_session.flush()

    # 5. PSC через сервис → auto_fill_predict=True (default) создаст 129 PeriodValue
    hm = await db_session.scalar(select(Channel).where(Channel.code == "HM"))
    assert hm is not None

    psc = await create_psk_channel(
        db_session,
        psk.id,
        ProjectSKUChannelCreate(
            channel_id=hm.id,
            nd_target=Decimal(str(nd_target)),
            offtake_target=Decimal(str(offtake_target)),
            channel_margin=Decimal("0.4"),
            promo_discount=Decimal("0.3"),
            promo_share=Decimal("1.0"),
            shelf_price_reg=Decimal(str(shelf_price)),
            logistics_cost_per_kg=Decimal("8.0"),
            # Q6 (2026-05-15): CA&M/Marketing per-channel.
            ca_m_rate=Decimal("0.16"),
            marketing_rate=Decimal("0.02"),
            nd_ramp_months=12,
        ),
        # auto_fill_predict=True (default) — predict_service автоматически
        # создаёт 43 PeriodValue × 3 сценария = 129 строк
    )

    base = await db_session.scalar(
        select(Scenario).where(
            Scenario.project_id == project.id,
            Scenario.type == ScenarioType.BASE,
        )
    )
    assert base is not None

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
        # D-20: channel_margin теперь tuple per-period
        assert all(v == pytest.approx(0.4) for v in inp.channel_margin)
        assert len(inp.channel_margin) == 43
        assert inp.vat_rate == pytest.approx(0.22)  # default Project (Q7, 2026-05-15)
        assert inp.wacc == pytest.approx(0.19)
        assert inp.wc_rate == pytest.approx(0.12)
        # bom_unit_cost теперь tuple длины 43 (per-period для инфляции).
        # Без inflation profile у тестового проекта серия должна быть
        # константой = базовое значение (1 × 10 × (1+0)).
        assert len(inp.bom_unit_cost) == 43
        assert inp.bom_unit_cost[0] == pytest.approx(10.0)
        assert all(v == pytest.approx(10.0) for v in inp.bom_unit_cost)
        # Effective values из PeriodValue (auto-fill после задачи 2.5):
        # ND рамп-ап от 0.001 × 0.20 = 0.0002 за 12 месяцев до 0.001
        # Y4..Y10 = 0.001 (плато)
        assert inp.nd[0] == pytest.approx(0.0002)        # M1 = nd_target × 0.20
        assert inp.nd[12] == pytest.approx(0.001)        # M13 = плато
        assert inp.nd[42] == pytest.approx(0.001)        # Y10 = плато
        # Offtake аналогично, target=1.0
        assert inp.offtake[0] == pytest.approx(0.20)     # M1 = 1.0 × 0.20
        assert inp.offtake[42] == pytest.approx(1.0)     # Y10

    async def test_project_not_found(self, db_session: AsyncSession):
        with pytest.raises(ProjectNotFoundError):
            await build_line_inputs(db_session, 999999, 1)

    async def test_launch_lag_zeros_periods_before_launch(
        self, db_session: AsyncSession
    ):
        """Launch year=2 month=2 → ND/offtake[0..12]=0, [13]+=non-zero.

        Проверяет launch lag (D-13): канал launches в Y2 Feb = M14 проекта.
        Periods 1..13 (Y1 Jan..Y2 Jan) должны быть обнулены, period 14
        (Y2 Feb) и далее — оригинальные значения из PeriodValue.

        После rollback (D-13 fix): launch живёт на ProjectSKUChannel, не
        на ProjectSKU. Excel хранит per (SKU × Channel) — TT/E-COM
        каналы запускаются раньше HM/SM/MM для одного SKU.
        """
        project_id, scenario_id, _, psc_id = await _seed_minimal_project(db_session)

        psc = await db_session.get(ProjectSKUChannel, psc_id)
        psc.launch_year = 2
        psc.launch_month = 2
        await db_session.flush()

        inputs = await build_line_inputs(db_session, project_id, scenario_id)
        inp = inputs[0]

        # Periods 1..13 (indices 0..12) обнулены
        for i in range(13):
            assert inp.nd[i] == 0.0, f"Period {i + 1} ND should be 0"
            assert inp.offtake[i] == 0.0, f"Period {i + 1} offtake should be 0"

        # Period 14 (index 13) — Y2 Feb — non-zero (predict ramp value)
        assert inp.nd[13] > 0.0
        assert inp.offtake[13] > 0.0

    async def test_launch_lag_default_y1m1_no_offset(
        self, db_session: AsyncSession
    ):
        """По умолчанию launch_year=1 month=1 → period 1 не обнулён."""
        project_id, scenario_id, _, _ = await _seed_minimal_project(db_session)
        inputs = await build_line_inputs(db_session, project_id, scenario_id)
        inp = inputs[0]
        assert inp.nd[0] > 0.0
        assert inp.offtake[0] > 0.0

    async def test_launch_lag_yearly_y4(
        self, db_session: AsyncSession
    ):
        """launch_year=4 → period_number < 37 обнулён, Y4 (37) активен."""
        project_id, scenario_id, _, psc_id = await _seed_minimal_project(db_session)

        psc = await db_session.get(ProjectSKUChannel, psc_id)
        psc.launch_year = 4
        psc.launch_month = 1
        await db_session.flush()

        inputs = await build_line_inputs(db_session, project_id, scenario_id)
        inp = inputs[0]
        for i in range(36):
            assert inp.nd[i] == 0.0
            assert inp.offtake[i] == 0.0
        assert inp.nd[36] > 0.0  # Y4 = period_number 37 = index 36

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
        """Conservative scenario с delta_nd = -0.10 → ND × 0.90.

        После задачи 2.5 auto-fill создаёт PeriodValue для всех 3 сценариев
        одинаковыми predict значениями. Delta применяется runtime в
        build_line_inputs.
        """
        project_id, _, _, _ = await _seed_minimal_project(db_session)
        cons = await db_session.scalar(
            select(Scenario).where(
                Scenario.project_id == project_id,
                Scenario.type == ScenarioType.CONSERVATIVE,
            )
        )
        cons.delta_nd = Decimal("-0.10")
        await db_session.flush()

        inputs = await build_line_inputs(db_session, project_id, cons.id)
        # ND[Y10] = nd_target × 0.90 = 0.001 × 0.9 = 0.0009
        assert inputs[0].nd[42] == pytest.approx(0.0009, rel=1e-9)
        # ND[M1] (start of ramp) = nd_target × 0.20 × 0.90 = 0.00018
        assert inputs[0].nd[0] == pytest.approx(0.00018, rel=1e-9)

    async def test_seasonality_profile_months_format(
        self, db_session: AsyncSession
    ):
        """Regression: parser должен поддерживать формат `{"months": [12]}`.

        Bug найден в Discovery V2: WTR / CSD / EN / TEA / JUI seasonality
        профили в seed_reference_data хранятся как
        `{"month_coefficients": {"months": [12 значений]}}`. Парсер
        `_load_seasonality_coefficients` ранее делал `int(k)` без try/except,
        что приводило к `ValueError: invalid literal for int() with base 10:
        'months'` при попытке использовать любой профиль из seed.

        Фикс в `calculation_service._load_seasonality_coefficients` — добавлена
        ветка для nested format `{"months": [...]}`.

        Этот тест:
        1. Создаёт проект с минимальным PSC
        2. Привязывает реальный seed профиль "WTR" (формат с "months")
        3. Запускает build_line_inputs → проверяет что seasonality
           правильно применён в monthly periods
        """
        from app.models import RefSeasonality, ProjectSKUChannel

        project_id, scenario_id, _, psc_id = await _seed_minimal_project(
            db_session
        )

        # Привязываем WTR seasonality (seed format: {"months": [12 vals]})
        wtr = await db_session.scalar(
            select(RefSeasonality).where(RefSeasonality.profile_name == "WTR")
        )
        assert wtr is not None, "WTR seed профиль должен быть в seed_reference_data"
        # Verify раздел формата (sanity check)
        assert isinstance(wtr.month_coefficients, dict)
        assert "months" in wtr.month_coefficients

        psc = await db_session.get(ProjectSKUChannel, psc_id)
        psc.seasonality_profile_id = wtr.id
        await db_session.flush()

        # build_line_inputs не должен падать с int("months") ValueError.
        # Это главное assertion — успешный вызов.
        inputs = await build_line_inputs(db_session, project_id, scenario_id)
        assert len(inputs) == 1
        inp = inputs[0]

        # Дополнительно: seasonality применён к monthly periods
        # WTR Jan = 0.876010, Feb = 0.796770, ..., июль = 1.369261, etc.
        # M1 = период month_num=1 = январь = 0.876
        assert inp.seasonality[0] == pytest.approx(0.876010, rel=1e-5)
        # M7 = июль = 1.369
        assert inp.seasonality[6] == pytest.approx(1.369261, rel=1e-5)
        # Yearly periods Y4..Y10 — seasonality = 1.0 (контракт PipelineInput)
        for i in range(36, 43):
            assert inp.seasonality[i] == pytest.approx(1.0)


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


