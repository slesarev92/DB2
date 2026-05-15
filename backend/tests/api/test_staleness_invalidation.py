"""F-01/F-02 staleness invalidation regression tests.

Проверяет что PATCH/POST/DELETE endpoint'ы, меняющие pipeline input,
помечают ScenarioResult.is_stale=True и что recalculate сбрасывает
флаг обратно в False.

Тесты используют минимальный seeded project (1 SKU, 1 PSC, 129
PeriodValue, 3 сценария) и триггерят recalculate через Celery eager
mode для создания свежих ScenarioResult.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BOMItem,
    Channel,
    Project,
    ProjectSKU,
    ProjectSKUChannel,
    SKU,
    Scenario,
    ScenarioResult,
    ScenarioType,
    User,
)


# ============================================================
# Celery eager mode (reuse pattern from test_calculation.py)
# ============================================================


@pytest.fixture(autouse=True)
def celery_eager_mode():
    """Переводит Celery в eager mode (task.delay() = sync call)."""
    from app.worker import celery_app

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    celery_app.conf.task_store_eager_result = True
    yield
    celery_app.conf.task_always_eager = False
    celery_app.conf.task_eager_propagates = False
    celery_app.conf.task_store_eager_result = False


# ============================================================
# Helper — project with recalculated results (is_stale=False baseline)
# ============================================================


async def _seed_and_calculate(
    db_session: AsyncSession, test_user: User
) -> tuple[int, int, int]:
    """Создаёт project + recalculate → свежие ScenarioResult с is_stale=False.

    Returns: (project_id, psk_id, psk_channel_id).
    """
    from app.schemas.project import ProjectCreate
    from app.schemas.project_sku_channel import ProjectSKUChannelCreate
    from app.services.project_service import create_project
    from app.services.project_sku_channel_service import create_psk_channel
    from app.services.calculation_service import calculate_all_scenarios

    project = await create_project(
        db_session,
        ProjectCreate(name="Stale test project", start_date="2025-01-01"),
        created_by=test_user.id,
    )
    await db_session.flush()

    sku = SKU(brand="Gorji", name="Stale test SKU", volume_l=Decimal("0.5"))
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

    hm = await db_session.scalar(select(Channel).where(Channel.code == "HM"))
    assert hm is not None

    psc = await create_psk_channel(
        db_session,
        psk.id,
        ProjectSKUChannelCreate(
            channel_id=hm.id,
            nd_target=Decimal("0.001"),
            offtake_target=Decimal("1.0"),
            channel_margin=Decimal("0.4"),
            promo_discount=Decimal("0.3"),
            promo_share=Decimal("1.0"),
            shelf_price_reg=Decimal("10.0"),
            logistics_cost_per_kg=Decimal("8.0"),
            # Q6 (2026-05-15): CA&M/Marketing per-channel.
            ca_m_rate=Decimal("0.16"),
            marketing_rate=Decimal("0.02"),
            nd_ramp_months=12,
        ),
    )
    await db_session.flush()

    # Реальный расчёт — создаём ScenarioResult с is_stale=False.
    await calculate_all_scenarios(db_session, project.id)
    await db_session.flush()

    return project.id, psk.id, psc.id


async def _count_stale(db_session: AsyncSession, project_id: int) -> tuple[int, int]:
    """Returns (stale_count, total_count) for project's scenario_results."""
    rows = (
        await db_session.execute(
            select(ScenarioResult.is_stale)
            .join(Scenario, Scenario.id == ScenarioResult.scenario_id)
            .where(Scenario.project_id == project_id)
        )
    ).scalars().all()
    return sum(1 for r in rows if r), len(rows)


# ============================================================
# Baseline: fresh recalculate → is_stale=False
# ============================================================


async def test_freshly_calculated_project_is_not_stale(
    db_session: AsyncSession, test_user: User
) -> None:
    """После calculate_all_scenarios все ScenarioResult.is_stale=False."""
    project_id, _, _ = await _seed_and_calculate(db_session, test_user)

    stale, total = await _count_stale(db_session, project_id)
    assert total == 9, f"Expected 9 results (3 scenarios × 3 scopes), got {total}"
    assert stale == 0, f"Fresh project should have 0 stale, got {stale}"


# ============================================================
# PATCH project → is_stale=True
# ============================================================


async def test_patch_project_marks_stale(
    db_session: AsyncSession, test_user: User, auth_client: AsyncClient
) -> None:
    """PATCH /api/projects/{id} с меняющимся wacc → все results stale."""
    project_id, _, _ = await _seed_and_calculate(db_session, test_user)
    await db_session.commit()

    resp = await auth_client.patch(
        f"/api/projects/{project_id}",
        json={"wacc": "0.20"},
    )
    assert resp.status_code == 200, resp.text

    stale, total = await _count_stale(db_session, project_id)
    assert total == 9
    assert stale == 9, f"All results should be stale after PATCH project, got {stale}"


# ============================================================
# PATCH psk_channel → is_stale=True
# ============================================================


async def test_patch_psc_marks_stale(
    db_session: AsyncSession, test_user: User, auth_client: AsyncClient
) -> None:
    """PATCH /api/psk-channels/{id} (изменение nd_target) → все results stale."""
    project_id, _, psc_id = await _seed_and_calculate(db_session, test_user)
    await db_session.commit()

    resp = await auth_client.patch(
        f"/api/psk-channels/{psc_id}",
        json={"nd_target": "0.002"},
    )
    assert resp.status_code == 200, resp.text

    stale, total = await _count_stale(db_session, project_id)
    assert stale == total == 9


# ============================================================
# PATCH period value → is_stale=True
# ============================================================


async def test_patch_period_value_marks_stale(
    db_session: AsyncSession, test_user: User, auth_client: AsyncClient
) -> None:
    """PATCH period value (fine-tune) → все results проекта stale."""
    project_id, _, psc_id = await _seed_and_calculate(db_session, test_user)
    await db_session.commit()

    # base scenario_id + первый period_id
    base_scenario_id = await db_session.scalar(
        select(Scenario.id).where(
            Scenario.project_id == project_id,
            Scenario.type == ScenarioType.BASE,
        )
    )
    from app.models import Period
    first_period_id = await db_session.scalar(
        select(Period.id).order_by(Period.period_number).limit(1)
    )

    resp = await auth_client.patch(
        f"/api/project-sku-channels/{psc_id}/values/{first_period_id}"
        f"?scenario_id={base_scenario_id}",
        json={"values": {"nd": "0.00015", "offtake": "0.25", "shelf_price": "11"}},
    )
    assert resp.status_code == 200, resp.text

    stale, total = await _count_stale(db_session, project_id)
    assert stale == total == 9


# ============================================================
# Recalculate → is_stale=False
# ============================================================


async def test_recalculate_clears_is_stale(
    db_session: AsyncSession, test_user: User, auth_client: AsyncClient
) -> None:
    """Цикл: PATCH project (stale=True) → calculate_all_scenarios → stale=False.

    Обходим Celery eager mode (там asyncio.run() клинит в pytest loop) —
    вызываем calculation_service напрямую, что имитирует то же что делает
    celery task в проде.
    """
    from app.services.calculation_service import calculate_all_scenarios

    project_id, _, _ = await _seed_and_calculate(db_session, test_user)
    await db_session.commit()

    # Шаг 1: инвалидация через PATCH
    resp = await auth_client.patch(
        f"/api/projects/{project_id}",
        json={"wacc": "0.21"},
    )
    assert resp.status_code == 200
    stale, _ = await _count_stale(db_session, project_id)
    assert stale == 9

    # Шаг 2: расчёт (sync, без Celery) — старые ScenarioResult удаляются,
    # новые создаются со server_default=false.
    await calculate_all_scenarios(db_session, project_id)
    await db_session.flush()

    stale, total = await _count_stale(db_session, project_id)
    assert total == 9, f"Expected 9 results after recalc, got {total}"
    assert stale == 0, f"Recalculate should clear stale, got {stale}"
