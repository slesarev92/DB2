"""Тесты predict-слоя автогенерации (задача 2.5).

Покрывает:
- 43 PeriodValue × 3 сценария = 129 строк создаются автоматически при PSC
- ND/Offtake линейный рамп-ап от target × 0.20 до target за nd_ramp_months
- После рамп-апа значения = target (плато)
- Y4..Y10 (yearly периоды) — всегда target (после рамп-апа)
- Shelf price инфляционный профиль "Апрель/Октябрь +7%": цена растёт
  на 7% в апреле и октябре, в остальные месяцы константа
- Идемпотентность: повторный вызов удаляет старые predict и создаёт новые
- Финетюненные/actual слои не трогаются при пересоздании predict
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BOMItem,
    Channel,
    Period,
    PeriodType,
    PeriodValue,
    Project,
    ProjectSKU,
    RefInflation,
    Scenario,
    ScenarioType,
    SKU,
    SourceType,
)
from app.schemas.project import ProjectCreate
from app.schemas.project_sku_channel import ProjectSKUChannelCreate
from app.services.predict_service import (
    ND_START_PCT,
    OFFTAKE_START_PCT,
    fill_predict_for_psk_channel,
    _ramp_values,
    _shelf_price_series,
)
from app.services.project_service import create_project
from app.services.project_sku_channel_service import create_psk_channel


# ============================================================
# Pure-function helpers
# ============================================================


class TestRampValues:
    def test_target_zero_returns_all_zeros(self):
        assert _ramp_values(0.0, 12, start_pct=0.20, n_monthly=36) == [0.0] * 36

    def test_zero_ramp_months_starts_at_target(self):
        assert _ramp_values(0.5, 0, start_pct=0.20, n_monthly=3) == [0.5] * 3

    def test_linear_ramp_first_and_last(self):
        # target=1.0, ramp_months=10, start_pct=0.20
        # M1 = 1.0 × 0.20 = 0.20
        # инкремент = (1.0 − 0.20) / 10 = 0.08
        # M10 = 0.20 + 9 × 0.08 = 0.92
        # M11+ = 1.0 (плато)
        result = _ramp_values(1.0, 10, start_pct=0.20, n_monthly=12)
        assert result[0] == pytest.approx(0.20)
        assert result[1] == pytest.approx(0.28)
        assert result[9] == pytest.approx(0.92)
        assert result[10] == pytest.approx(1.0)
        assert result[11] == pytest.approx(1.0)

    def test_ramp_longer_than_horizon(self):
        # ramp_months > n_monthly: target не достигнут в monthly периодах
        result = _ramp_values(1.0, 100, start_pct=0.20, n_monthly=12)
        # Все значения < 1.0 (рамп-ап продолжается)
        assert all(v < 1.0 for v in result)
        assert result[0] == pytest.approx(0.20)


# ============================================================
# Shelf price series with inflation
# ============================================================


class TestShelfPriceSeries:
    @pytest.fixture
    async def periods(self, db_session: AsyncSession) -> list[Period]:
        return list(
            (
                await db_session.scalars(select(Period).order_by(Period.period_number))
            ).all()
        )

    async def test_no_profile_returns_constant(self, periods):
        result = _shelf_price_series(100.0, periods, None)
        assert len(result) == 43
        assert all(v == 100.0 for v in result)

    async def test_april_october_7_percent_profile(
        self, db_session: AsyncSession, periods
    ):
        """Profile 'Апрель/Октябрь +7%': цена растёт на 7% в апр и окт.

        Семантика: monthly_deltas[3] = 0.07 (April, index 3 = month 4),
        monthly_deltas[9] = 0.07 (October, index 9 = month 10).
        """
        profile = await db_session.scalar(
            select(RefInflation).where(
                RefInflation.profile_name == "Апрель/Октябрь +7%"
            )
        )
        assert profile is not None

        result = _shelf_price_series(100.0, periods, profile)
        assert len(result) == 43

        # Period 1 (M1, январь 2025) — January, monthly_deltas[0] = 0
        # shelf[M1] = 100 × (1 + 0) = 100.0
        # Уточнение: первые 3 месяца до апреля константа
        m1, m2, m3 = result[0], result[1], result[2]
        assert m1 == pytest.approx(100.0)
        assert m2 == pytest.approx(100.0)
        assert m3 == pytest.approx(100.0)
        # M4 (April) — применяется +7%
        m4 = result[3]
        assert m4 == pytest.approx(100.0 * 1.07)
        # M5..M9 — без изменений
        for i in range(4, 9):
            assert result[i] == pytest.approx(m4)
        # M10 (октябрь) — ещё +7%
        m10 = result[9]
        assert m10 == pytest.approx(m4 * 1.07)

    async def test_yearly_growth_applied_to_y4_y10(
        self, db_session: AsyncSession, periods
    ):
        profile = await db_session.scalar(
            select(RefInflation).where(
                RefInflation.profile_name == "Апрель/Октябрь +7%"
            )
        )
        # yearly_growth для этого профиля — должен быть в seed
        assert profile is not None
        raw = profile.month_coefficients
        yg = raw["yearly_growth"]
        assert len(yg) == 7

        result = _shelf_price_series(100.0, periods, profile)
        # Y4 (period_number 37) — первый годовой
        # shelf[Y4] = shelf[M36] × (1 + yearly_growth[0])
        m36 = result[35]
        y4 = result[36]
        assert y4 == pytest.approx(m36 * (1.0 + yg[0]))


# ============================================================
# Integration: fill_predict_for_psk_channel through create_psk_channel
# ============================================================


async def _seed_minimal_psc(
    db_session: AsyncSession, *, nd_target=0.5, offtake_target=10.0, ramp=12
):
    project = await create_project(
        db_session,
        ProjectCreate(name="Predict test", start_date="2025-01-01"),
        created_by=None,
    )
    await db_session.flush()

    sku = SKU(brand="Gorji", name="Predict SKU", volume_l=Decimal("0.5"))
    db_session.add(sku)
    await db_session.flush()

    psk = ProjectSKU(project_id=project.id, sku_id=sku.id)
    db_session.add(psk)
    await db_session.flush()

    hm = await db_session.scalar(select(Channel).where(Channel.code == "HM"))

    psc = await create_psk_channel(
        db_session,
        psk.id,
        ProjectSKUChannelCreate(
            channel_id=hm.id,
            nd_target=Decimal(str(nd_target)),
            offtake_target=Decimal(str(offtake_target)),
            shelf_price_reg=Decimal("100"),
            nd_ramp_months=ramp,
        ),
    )
    return project, psc


class TestAutoFill:
    async def test_creates_129_period_values(self, db_session: AsyncSession):
        """43 periods × 3 scenarios = 129 PeriodValue с predict-слоем."""
        _, psc = await _seed_minimal_psc(db_session)

        rows = (
            await db_session.scalars(
                select(PeriodValue).where(
                    PeriodValue.psk_channel_id == psc.id,
                    PeriodValue.source_type == SourceType.PREDICT,
                )
            )
        ).all()
        assert len(list(rows)) == 129  # 43 × 3

    async def test_all_three_scenarios_have_predict(
        self, db_session: AsyncSession
    ):
        project, psc = await _seed_minimal_psc(db_session)
        scenarios = (
            await db_session.scalars(
                select(Scenario).where(Scenario.project_id == project.id)
            )
        ).all()
        assert len(scenarios) == 3

        for sc in scenarios:
            count = len(
                list(
                    (
                        await db_session.scalars(
                            select(PeriodValue).where(
                                PeriodValue.psk_channel_id == psc.id,
                                PeriodValue.scenario_id == sc.id,
                                PeriodValue.source_type == SourceType.PREDICT,
                            )
                        )
                    ).all()
                )
            )
            assert count == 43

    async def test_nd_ramp_pattern(self, db_session: AsyncSession):
        """ND[M1] = nd_target × 0.20, ND[M12] = nd_target, ND[Y10] = nd_target."""
        _, psc = await _seed_minimal_psc(
            db_session, nd_target=0.5, ramp=12
        )

        # Берём base сценарий
        base_pvs = (
            await db_session.execute(
                select(PeriodValue, Period)
                .join(Period, Period.id == PeriodValue.period_id)
                .where(
                    PeriodValue.psk_channel_id == psc.id,
                    PeriodValue.source_type == SourceType.PREDICT,
                )
                .order_by(Period.period_number)
            )
        ).all()

        # Уникальные periods (3 сценария дают 3 копии каждого period)
        seen_periods: dict[int, dict] = {}
        for pv, p in base_pvs:
            seen_periods[p.period_number] = pv.values

        # M1: nd_target × 0.20 = 0.10
        assert seen_periods[1]["nd"] == pytest.approx(0.10)
        # M12 (последний месяц рамп-апа): nd_target × 0.20 + 11 × inc
        # inc = (0.5 - 0.10) / 12 = 0.0333
        # M12 = 0.10 + 11 × 0.0333 = 0.467
        assert seen_periods[12]["nd"] == pytest.approx(0.10 + 11 * (0.4 / 12))
        # M13 = плато
        assert seen_periods[13]["nd"] == pytest.approx(0.50)
        # M36 = плато
        assert seen_periods[36]["nd"] == pytest.approx(0.50)
        # Y4..Y10 = плато
        for pn in range(37, 44):
            assert seen_periods[pn]["nd"] == pytest.approx(0.50)

    async def test_offtake_ramp_pattern(self, db_session: AsyncSession):
        """Offtake аналогично ND."""
        _, psc = await _seed_minimal_psc(
            db_session, offtake_target=10.0, ramp=6
        )

        rows = (
            await db_session.execute(
                select(PeriodValue, Period)
                .join(Period, Period.id == PeriodValue.period_id)
                .where(
                    PeriodValue.psk_channel_id == psc.id,
                    PeriodValue.source_type == SourceType.PREDICT,
                )
                .order_by(Period.period_number)
            )
        ).all()
        seen: dict[int, dict] = {}
        for pv, p in rows:
            seen[p.period_number] = pv.values

        # M1: 10 × 0.20 = 2.0
        assert seen[1]["offtake"] == pytest.approx(2.0)
        # M6 (последний рамп): 2.0 + 5 × (8/6) = 2 + 6.67 = 8.67
        assert seen[6]["offtake"] == pytest.approx(2.0 + 5 * (8.0 / 6))
        # M7 = плато
        assert seen[7]["offtake"] == pytest.approx(10.0)

    async def test_idempotent_recreate(self, db_session: AsyncSession):
        """Повторный fill_predict удаляет старые predict и создаёт новые."""
        _, psc = await _seed_minimal_psc(db_session)

        # Считаем строки до повторного вызова
        before = len(
            list(
                (
                    await db_session.scalars(
                        select(PeriodValue).where(
                            PeriodValue.psk_channel_id == psc.id,
                            PeriodValue.source_type == SourceType.PREDICT,
                        )
                    )
                ).all()
            )
        )
        assert before == 129

        # Повторный вызов — должен заменить, не дублировать
        await fill_predict_for_psk_channel(db_session, psc)

        after = len(
            list(
                (
                    await db_session.scalars(
                        select(PeriodValue).where(
                            PeriodValue.psk_channel_id == psc.id,
                            PeriodValue.source_type == SourceType.PREDICT,
                        )
                    )
                ).all()
            )
        )
        assert after == 129  # не 258 — старые удалены

    async def test_finetuned_layer_preserved(self, db_session: AsyncSession):
        """Повторный fill_predict не трогает finetuned слой."""
        _, psc = await _seed_minimal_psc(db_session)
        base = await db_session.scalar(
            select(Scenario).where(Scenario.type == ScenarioType.BASE)
        )

        # Добавляем finetuned для одного периода
        m1 = await db_session.scalar(
            select(Period).where(Period.period_number == 1)
        )
        db_session.add(
            PeriodValue(
                psk_channel_id=psc.id,
                scenario_id=base.id,
                period_id=m1.id,
                source_type=SourceType.FINETUNED,
                version_id=1,
                values={"nd": 0.999, "offtake": 99.0, "shelf_price": 999},
                is_overridden=True,
            )
        )
        await db_session.flush()

        # Пересоздаём predict
        await fill_predict_for_psk_channel(db_session, psc)

        # Finetuned всё ещё там
        finetuned_count = len(
            list(
                (
                    await db_session.scalars(
                        select(PeriodValue).where(
                            PeriodValue.psk_channel_id == psc.id,
                            PeriodValue.source_type == SourceType.FINETUNED,
                        )
                    )
                ).all()
            )
        )
        assert finetuned_count == 1
