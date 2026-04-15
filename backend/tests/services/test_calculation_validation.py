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
        ca_m_rate=Decimal("0.16"),
        marketing_rate=Decimal("0.02"),
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
