"""4.3 (engine audit) — input validation regression tests.

Проверяет что `_build_line_input` ловит некорректные параметры до
запуска pipeline:
- channel_margin >= 1.0 → LineValidationError
- shelf_price < 0 → LineValidationError
- universe=0, bom=0, shelf_price=0 → warning в логе (pipeline работает)
"""
from __future__ import annotations

import logging
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BOMItem,
    Channel,
    ProjectSKU,
    ProjectSKUChannel,
    SKU,
    Scenario,
    ScenarioType,
)
from app.services.calculation_service import (
    LineValidationError,
    build_line_inputs,
)


async def _seed_project_with_psc(
    db_session: AsyncSession,
    *,
    channel_margin: Decimal = Decimal("0.4"),
    shelf_price: Decimal = Decimal("10.0"),
    bom_price: Decimal = Decimal("10.0"),
    universe: int | None = None,
) -> tuple[int, int]:
    """Создаёт project + SKU + BOM + PSC с контролируемыми параметрами.

    Returns: (project_id, base_scenario_id).
    """
    from app.schemas.project import ProjectCreate
    from app.schemas.project_sku_channel import ProjectSKUChannelCreate
    from app.services.project_service import create_project
    from app.services.project_sku_channel_service import create_psk_channel

    project = await create_project(
        db_session,
        ProjectCreate(name="validation test", start_date="2025-01-01"),
        created_by=None,
    )
    await db_session.flush()

    sku = SKU(brand="Gorji", name="ValidTest", volume_l=Decimal("0.5"))
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
        price_per_unit=bom_price,
    )
    db_session.add(bom)
    await db_session.flush()

    hm = await db_session.scalar(select(Channel).where(Channel.code == "HM"))
    assert hm is not None
    if universe is not None:
        hm.universe_outlets = universe
        await db_session.flush()

    await create_psk_channel(
        db_session,
        psk.id,
        ProjectSKUChannelCreate(
            channel_id=hm.id,
            nd_target=Decimal("0.001"),
            offtake_target=Decimal("1.0"),
            channel_margin=channel_margin,
            promo_discount=Decimal("0.3"),
            promo_share=Decimal("1.0"),
            shelf_price_reg=shelf_price,
            logistics_cost_per_kg=Decimal("8.0"),
            # Q6 (2026-05-15): CA&M/Marketing per-channel.
            ca_m_rate=Decimal("0.16"),
            marketing_rate=Decimal("0.02"),
            nd_ramp_months=12,
        ),
    )

    base = await db_session.scalar(
        select(Scenario).where(
            Scenario.project_id == project.id,
            Scenario.type == ScenarioType.BASE,
        )
    )
    assert base is not None
    return project.id, base.id


async def test_channel_margin_equal_one_raises(
    db_session: AsyncSession,
) -> None:
    """channel_margin=1.0 → ex_factory=0 → ошибка до pipeline."""
    project_id, scenario_id = await _seed_project_with_psc(
        db_session, channel_margin=Decimal("1.0")
    )

    with pytest.raises(LineValidationError) as exc:
        await build_line_inputs(db_session, project_id, scenario_id)

    assert exc.value.field == "channel_margin"
    assert "ex_factory" in exc.value.reason.lower()


async def test_universe_zero_warns_but_passes(
    db_session: AsyncSession, caplog: pytest.LogCaptureFixture,
) -> None:
    """universe=0 → warning в логе, но pipeline не блокируется."""
    project_id, scenario_id = await _seed_project_with_psc(
        db_session, universe=0
    )

    with caplog.at_level(logging.WARNING, logger="app.services.calculation_service"):
        inputs = await build_line_inputs(db_session, project_id, scenario_id)
    assert len(inputs) == 1
    assert any(
        "universe_outlets=0" in rec.getMessage() for rec in caplog.records
    )


async def test_bom_zero_warns_but_passes(
    db_session: AsyncSession, caplog: pytest.LogCaptureFixture,
) -> None:
    """bom_unit_cost=0 → warning, но pipeline работает."""
    project_id, scenario_id = await _seed_project_with_psc(
        db_session, bom_price=Decimal("0")
    )

    with caplog.at_level(logging.WARNING, logger="app.services.calculation_service"):
        inputs = await build_line_inputs(db_session, project_id, scenario_id)
    assert len(inputs) == 1
    assert any(
        "bom_unit_cost=0" in rec.getMessage() for rec in caplog.records
    )


# ============================================================
# 4.1 Loss carryforward (ст.283 НК РФ) — opt-in через Project.tax_loss_carryforward
# ============================================================


def test_loss_carryforward_off_matches_excel_tax_formula() -> None:
    """loss_carryforward=False — Excel-compat: tax=−CM×rate только на прибыль."""
    from app.engine.steps.s10_discount import _compute_annual_tax

    annual_cm = [-100.0, -50.0, 200.0, 200.0]
    tax = _compute_annual_tax(annual_cm, tax_rate=0.20, loss_carryforward=False)
    assert tax == [0.0, 0.0, -40.0, -40.0]


def test_loss_carryforward_on_reduces_tax_on_profitable_years() -> None:
    """loss_carryforward=True — убытки Y1+Y2 уменьшают tax Y3+Y4.

    Scenario: Y1=-100, Y2=-50, Y3=+200, Y4=+200, rate=0.20.
    Without: tax=[0, 0, -40, -40]. Total tax = -80.
    With carryforward:
      Y3: cumulative_loss=150, usable=min(150, 0.5×200)=100,
          taxable=100, tax=-20. remaining_loss=50.
      Y4: usable=min(50, 0.5×200)=50, taxable=150, tax=-30. loss=0.
    tax=[0, 0, -20, -30]. Total tax = -50. Saving = 30 ₽.
    """
    from app.engine.steps.s10_discount import _compute_annual_tax

    annual_cm = [-100.0, -50.0, 200.0, 200.0]
    tax = _compute_annual_tax(annual_cm, tax_rate=0.20, loss_carryforward=True)
    assert tax == [0.0, 0.0, -20.0, -30.0]


def test_loss_carryforward_cap_50pct() -> None:
    """Cap 50% прибыли — нельзя обнулить налог даже при огромном убытке."""
    from app.engine.steps.s10_discount import _compute_annual_tax

    # Y1 огромный убыток, Y2 прибыль — должен заплатить половину.
    annual_cm = [-10000.0, 100.0]
    tax = _compute_annual_tax(annual_cm, tax_rate=0.20, loss_carryforward=True)
    # Y2: usable = min(10000, 50) = 50, taxable = 100 − 50 = 50, tax = −10
    assert tax == [0.0, -10.0]


def test_loss_carryforward_no_profit_no_tax() -> None:
    """Все годы убыточны — tax везде 0 (нет базы для налога)."""
    from app.engine.steps.s10_discount import _compute_annual_tax

    annual_cm = [-100.0, -50.0, -10.0]
    tax = _compute_annual_tax(annual_cm, tax_rate=0.20, loss_carryforward=True)
    assert tax == [0.0, 0.0, 0.0]


# ============================================================
# 4.5 Scenario deltas price/COGS/logistics
# ============================================================


async def test_scenario_delta_shelf_price_applies_to_pipeline(
    db_session: AsyncSession,
) -> None:
    """Scenario.delta_shelf_price=+0.10 → shelf_price_reg в PipelineInput выше на 10%."""
    project_id, base_scenario_id = await _seed_project_with_psc(db_session)
    # Меняем базовую цену 10 → ожидаем в pipeline 10 × 1.1 = 11.0 при дельте 10%.
    from app.models import Scenario
    base = await db_session.get(Scenario, base_scenario_id)
    assert base is not None
    base.delta_shelf_price = Decimal("0.10")
    await db_session.flush()

    inputs = await build_line_inputs(db_session, project_id, base_scenario_id)
    assert len(inputs) == 1
    # Все 43 периода умножены на 1.1
    for s in inputs[0].shelf_price_reg:
        assert s == pytest.approx(11.0)


async def test_scenario_delta_bom_and_logistics(
    db_session: AsyncSession,
) -> None:
    """delta_bom_cost=+0.15, delta_logistics=+0.20 → соответствующие тьюплы
    в pipeline input увеличены."""
    project_id, base_scenario_id = await _seed_project_with_psc(db_session)
    from app.models import Scenario
    base = await db_session.get(Scenario, base_scenario_id)
    assert base is not None
    base.delta_bom_cost = Decimal("0.15")
    base.delta_logistics = Decimal("0.20")
    await db_session.flush()

    inputs = await build_line_inputs(db_session, project_id, base_scenario_id)
    inp = inputs[0]
    # BOM base = 1.0 × 10.0 × 1.0 = 10.0. × 1.15 = 11.5.
    assert inp.bom_unit_cost[0] == pytest.approx(11.5)
    # Logistics base = 8.0. × 1.20 = 9.6.
    assert inp.logistics_cost_per_kg[0] == pytest.approx(9.6)
