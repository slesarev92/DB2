"""Тесты AIContextBuilder (Phase 7.2).

Интеграционные — работают с реальным postgres через `db_session`
fixture. Это важно: сборка контекста делает selectinload и проверяет
deleted_at — моки эти детали скрывают, а баги всплывают на настоящем
SQL.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    PeriodScope,
    Project,
    ProjectSKU,
    SKU,
    Scenario,
    ScenarioResult,
    ScenarioType,
)
from app.services.ai_context_builder import (
    AIContextBuilder,
    AIContextBuilderError,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
async def project_with_scenarios(db_session: AsyncSession) -> Project:
    """Проект с 3 сценариями (Base/Cons/Aggr) + их results × 3 scope'а.

    Создаёт реалистичный snapshot для AI-контекста.
    """
    project = Project(
        name="GORJI Test Project",
        start_date=date(2026, 1, 1),
        horizon_years=10,
        wacc=Decimal("0.19"),
        tax_rate=Decimal("0.20"),
        wc_rate=Decimal("0.12"),
        vat_rate=Decimal("0.20"),
        currency="RUB",
        gate_stage="G2",
        project_goal="Вывод нового SKU в категорию premium ICE",
        target_audience="HoReCa + retail premium",
    )
    db_session.add(project)
    await db_session.flush()

    scenarios = []
    for s_type, delta_offtake in [
        (ScenarioType.BASE, Decimal("0")),
        (ScenarioType.CONSERVATIVE, Decimal("-0.15")),
        (ScenarioType.AGGRESSIVE, Decimal("0.20")),
    ]:
        scenario = Scenario(
            project_id=project.id,
            type=s_type,
            delta_nd=Decimal("0"),
            delta_offtake=delta_offtake,
            delta_opex=Decimal("0"),
        )
        db_session.add(scenario)
        scenarios.append(scenario)
    await db_session.flush()

    # По одному ScenarioResult на каждую комбинацию scenario × scope
    for scenario in scenarios:
        for scope, npv_value in [
            (PeriodScope.Y1Y3, Decimal("-5000000")),
            (PeriodScope.Y1Y5, Decimal("15000000")),
            (PeriodScope.Y1Y10, Decimal("80000000")),
        ]:
            result = ScenarioResult(
                scenario_id=scenario.id,
                period_scope=scope,
                npv=npv_value,
                irr=Decimal("0.28"),
                roi=Decimal("1.45"),
                payback_simple=Decimal("3.2"),
                payback_discounted=Decimal("4.1"),
                contribution_margin=Decimal("0.35"),
                ebitda_margin=Decimal("0.22"),
                go_no_go=True,
            )
            db_session.add(result)
    await db_session.flush()

    return project


@pytest.fixture
async def project_with_skus(
    db_session: AsyncSession, project_with_scenarios: Project
) -> Project:
    """Добавляет 4 SKU в проект (3 included + 1 excluded) для top-3 теста."""
    for i, brand in enumerate(["GORJI", "ELEKTRA", "AURA", "EXCLUDED"]):
        sku = SKU(
            brand=brand,
            name=f"{brand} 0.5L Product {i}",
            format="PET",
            volume_l=Decimal("0.5"),
            segment="premium",
        )
        db_session.add(sku)
        await db_session.flush()
        project_sku = ProjectSKU(
            project_id=project_with_scenarios.id,
            sku_id=sku.id,
            include=(brand != "EXCLUDED"),
            production_cost_rate=Decimal("0.35"),
        )
        db_session.add(project_sku)
    await db_session.flush()
    return project_with_scenarios


# ============================================================
# Happy path
# ============================================================


async def test_for_kpi_explanation_happy_path(
    db_session: AsyncSession,
    project_with_skus: Project,
) -> None:
    """Контекст содержит project params + все 3 сценария + top-3 SKU."""
    # Найдём BASE сценарий как focus
    base_scenario = next(
        s
        for s in (
            await db_session.scalars(
                select(Scenario).where(
                    Scenario.project_id == project_with_skus.id
                )
            )
        ).all()
        if s.type == ScenarioType.BASE
    )

    builder = AIContextBuilder(db_session)
    ctx = await builder.for_kpi_explanation(
        project_id=project_with_skus.id,
        scenario_id=base_scenario.id,
        scope=PeriodScope.Y1Y5,
    )

    # Project meta
    assert ctx["project"]["id"] == project_with_skus.id
    assert ctx["project"]["name"] == "GORJI Test Project"
    assert ctx["project"]["horizon_years"] == 10
    assert ctx["project"]["gate_stage"] == "G2"
    assert ctx["project"]["project_goal"].startswith("Вывод")
    # Params — float, не Decimal (JSON-safe)
    assert ctx["project"]["params"]["wacc"] == 0.19
    assert ctx["project"]["params"]["tax_rate"] == 0.20
    assert isinstance(ctx["project"]["params"]["wc_rate"], float)

    # Focus
    assert ctx["focus"]["scenario_id"] == base_scenario.id
    assert ctx["focus"]["scenario_type"] == "base"
    assert ctx["focus"]["scope"] == "y1y5"

    # Все 3 сценария присутствуют, отсортированы Base → Conservative → Aggressive
    assert len(ctx["scenarios"]) == 3
    assert ctx["scenarios"][0]["type"] == "base"
    assert ctx["scenarios"][1]["type"] == "conservative"
    assert ctx["scenarios"][2]["type"] == "aggressive"

    # У каждого сценария — 3 scope results, отсортированы Y1Y3 → Y1Y5 → Y1Y10
    for scenario_ctx in ctx["scenarios"]:
        assert len(scenario_ctx["results"]) == 3
        assert scenario_ctx["results"][0]["scope"] == "y1y3"
        assert scenario_ctx["results"][1]["scope"] == "y1y5"
        assert scenario_ctx["results"][2]["scope"] == "y1y10"
        # NPV — float
        assert isinstance(scenario_ctx["results"][0]["npv"], float)

    # Top-3 SKU (EXCLUDED не попал, include=False)
    assert len(ctx["top_skus"]) == 3
    brands = {s["brand"] for s in ctx["top_skus"]}
    assert brands == {"GORJI", "ELEKTRA", "AURA"}
    assert "EXCLUDED" not in brands


# ============================================================
# Error cases
# ============================================================


async def test_for_kpi_explanation_missing_project(
    db_session: AsyncSession,
) -> None:
    """Несуществующий project_id → AIContextBuilderError."""
    builder = AIContextBuilder(db_session)
    with pytest.raises(AIContextBuilderError, match="не найден"):
        await builder.for_kpi_explanation(
            project_id=999999,
            scenario_id=1,
            scope=PeriodScope.Y1Y5,
        )


async def test_for_kpi_explanation_soft_deleted_project(
    db_session: AsyncSession,
    project_with_scenarios: Project,
) -> None:
    """Soft-deleted project → AIContextBuilderError.

    Паттерн #4 из CLAUDE.md: soft delete через deleted_at, вся бизнес-
    логика фильтрует WHERE deleted_at IS NULL.
    """
    project_with_scenarios.deleted_at = datetime.now(timezone.utc)
    await db_session.flush()

    builder = AIContextBuilder(db_session)
    with pytest.raises(AIContextBuilderError, match="удалён"):
        await builder.for_kpi_explanation(
            project_id=project_with_scenarios.id,
            scenario_id=1,
            scope=PeriodScope.Y1Y5,
        )


async def test_for_kpi_explanation_scenario_wrong_project(
    db_session: AsyncSession,
    project_with_scenarios: Project,
) -> None:
    """Scenario из другого проекта → AIContextBuilderError."""
    # Создаём второй проект со своим сценарием
    other_project = Project(
        name="Other",
        start_date=date(2026, 1, 1),
        horizon_years=10,
    )
    db_session.add(other_project)
    await db_session.flush()
    other_scenario = Scenario(
        project_id=other_project.id,
        type=ScenarioType.BASE,
    )
    db_session.add(other_scenario)
    await db_session.flush()

    builder = AIContextBuilder(db_session)
    with pytest.raises(AIContextBuilderError, match="не принадлежит"):
        await builder.for_kpi_explanation(
            project_id=project_with_scenarios.id,
            scenario_id=other_scenario.id,
            scope=PeriodScope.Y1Y5,
        )


# ============================================================
# Edge case: empty top_skus
# ============================================================


async def test_for_kpi_explanation_no_skus(
    db_session: AsyncSession,
    project_with_scenarios: Project,
) -> None:
    """Проект без SKU → top_skus пустой список, не падение."""
    # project_with_scenarios фикстура не добавляет SKU
    scenario_id = (
        await db_session.scalars(
            select(Scenario).where(
                Scenario.project_id == project_with_scenarios.id
            )
        )
    ).first().id

    builder = AIContextBuilder(db_session)
    ctx = await builder.for_kpi_explanation(
        project_id=project_with_scenarios.id,
        scenario_id=scenario_id,
        scope=PeriodScope.Y1Y3,
    )
    assert ctx["top_skus"] == []


# ============================================================
# Phase 7.6 — for_content_field
# ============================================================


async def test_for_content_field_happy_path(
    db_session: AsyncSession,
    project_with_scenarios: Project,
) -> None:
    """Successful context build for content field generation."""
    # Set some existing content to verify cross-field inclusion
    project_with_scenarios.project_goal = "Вывод нового SKU"
    project_with_scenarios.innovation_type = "line extension"
    await db_session.flush()

    builder = AIContextBuilder(db_session)
    ctx = await builder.for_content_field(
        project_id=project_with_scenarios.id,
        field_name="target_audience",
    )

    assert ctx["target_field"] == "target_audience"
    assert ctx["project"]["name"] == project_with_scenarios.name
    # existing_content содержит project_goal но не target_audience
    assert "project_goal" in ctx["existing_content"]
    assert "target_audience" not in ctx["existing_content"]
    assert ctx["user_hint"] is None


async def test_for_content_field_with_user_hint(
    db_session: AsyncSession,
    project_with_scenarios: Project,
) -> None:
    """user_hint included in context."""
    builder = AIContextBuilder(db_session)
    ctx = await builder.for_content_field(
        project_id=project_with_scenarios.id,
        field_name="project_goal",
        user_hint="Акцент на экологичность",
    )
    assert ctx["user_hint"] == "Акцент на экологичность"


async def test_for_content_field_invalid_field(
    db_session: AsyncSession,
    project_with_scenarios: Project,
) -> None:
    """Invalid field name → AIContextBuilderError."""
    builder = AIContextBuilder(db_session)
    with pytest.raises(AIContextBuilderError, match="не поддерживается"):
        await builder.for_content_field(
            project_id=project_with_scenarios.id,
            field_name="executive_summary",  # not in CONTENT_FIELDS
        )


async def test_for_content_field_deleted_project(
    db_session: AsyncSession,
    project_with_scenarios: Project,
) -> None:
    """Deleted project → AIContextBuilderError."""
    project_with_scenarios.deleted_at = datetime.now(timezone.utc)
    await db_session.flush()

    builder = AIContextBuilder(db_session)
    with pytest.raises(AIContextBuilderError, match="не найден"):
        await builder.for_content_field(
            project_id=project_with_scenarios.id,
            field_name="project_goal",
        )
