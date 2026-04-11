"""Генератор PDF-экспорта паспорта проекта (задача 5.3, F-10).

Flow:
  1. Загружает те же данные что ppt_exporter (проект + SKU + BOM +
     scenarios + results + base pipeline aggregate + package images).
  2. Маппит в словари для Jinja2 контекста (упрощает template).
  3. Jinja2 рендерит `project_passport.html` → HTML строка.
  4. WeasyPrint конвертирует HTML + CSS → PDF bytes.

Template: `backend/app/export/templates/project_passport.html`. CSS
встроен в <style>, без внешних ассетов — всё self-contained.

Package images embedding: HTML через `<img src="file://{abs_path}">`.
WeasyPrint читает локальные файлы только если они разрешены через
`url_fetcher`. По умолчанию file:// работает в Docker-окружении (Linux),
на Windows без Docker — не гарантируется (см. WeasyPrint docs).

Контракт совпадает с excel/ppt_exporter:
- `generate_project_pdf(session, project_id) → bytes`
- Поднимает `ProjectNotFoundForExport` если проект не найден.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from weasyprint import HTML

from app.engine.pipeline import run_project_pipeline
from app.export.excel_exporter import (
    ProjectNotFoundForExport,
    _load_project_full,
    _load_psk_channels,
    _load_scenario_results,
    _load_skus_with_bom,
)
from app.export.ppt_exporter import _load_package_images
from app.models import (
    BOMItem,
    MediaAsset,
    Project,
    ProjectFinancialPlan,
    ProjectSKU,
    ProjectSKUChannel,
    RefInflation,
    Scenario,
    ScenarioResult,
    ScenarioType,
)
from app.models.base import PeriodScope
from app.services.calculation_service import (
    _load_period_catalog,
    _load_project_financial_plan,
    build_line_inputs,
)


# ============================================================
# Jinja2 environment (module-level singleton)
# ============================================================

_TEMPLATES_DIR = Path(__file__).parent / "templates"

_jinja_env = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


# ============================================================
# Формат-хелперы (те же что в ppt_exporter, но изолированы —
# Jinja2 дёргает их через globals)
# ============================================================


def _fmt_money(value: float | int | None, decimals: int = 0) -> str:
    if value is None:
        return "—"
    try:
        f = float(value)
    except (TypeError, ValueError):
        return "—"
    if decimals == 0:
        return f"{f:,.0f}".replace(",", " ")
    return f"{f:,.{decimals}f}".replace(",", " ")


def _fmt_pct(value: float | int | None, decimals: int = 1) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value) * 100:.{decimals}f}%"
    except (TypeError, ValueError):
        return "—"


GATE_LABELS = {
    "G0": "G0 — Идея",
    "G1": "G1 — Концепция",
    "G2": "G2 — Design",
    "G3": "G3 — Development",
    "G4": "G4 — Launch Ready",
    "G5": "G5 — In Market",
}

SCENARIO_LABELS = {
    ScenarioType.BASE: "Base",
    ScenarioType.CONSERVATIVE: "Conservative",
    ScenarioType.AGGRESSIVE: "Aggressive",
}

FUNCTION_STATUS_LABELS = {
    "green": "Готово",
    "yellow": "В работе",
    "red": "Риск",
}

VALIDATION_SUBTESTS = [
    ("concept_test", "Concept test"),
    ("naming", "Naming"),
    ("design", "Design"),
    ("product", "Product"),
    ("price", "Price"),
]


def _gate_label(code: str | None) -> str:
    if not code:
        return "—"
    return GATE_LABELS.get(code, code)


# ============================================================
# Context builders
# ============================================================


def _build_sku_rows(
    skus_with_bom: list[tuple[ProjectSKU, list[BOMItem]]],
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for psk, bom_items in skus_with_bom:
        bom_cost = sum(
            float(b.quantity_per_unit)
            * float(b.price_per_unit)
            * (1 + float(b.loss_pct))
            for b in bom_items
        )
        out.append({
            "name": f"{psk.sku.brand} — {psk.sku.name}",
            "format": psk.sku.format or "—",
            "volume": (
                f"{float(psk.sku.volume_l):.2f} л"
                if psk.sku.volume_l is not None
                else "—"
            ),
            "prod_rate": _fmt_pct(float(psk.production_cost_rate)),
            "bom_cost": _fmt_money(bom_cost, decimals=2),
        })
    return out


def _build_kpi_rows(
    scenarios: list[Scenario],
    results_by_scenario: dict[int, list[ScenarioResult]],
) -> list[dict[str, str]]:
    scenario_order = {
        ScenarioType.BASE: 0,
        ScenarioType.CONSERVATIVE: 1,
        ScenarioType.AGGRESSIVE: 2,
    }
    sorted_scenarios = sorted(
        scenarios, key=lambda s: scenario_order.get(s.type, 99)
    )

    rows: list[dict[str, str]] = []
    for sc in sorted_scenarios:
        results = results_by_scenario.get(sc.id, [])
        y1y10 = next(
            (r for r in results if r.period_scope == PeriodScope.Y1Y10), None
        )
        if y1y10 is None:
            rows.append({
                "scenario": SCENARIO_LABELS.get(sc.type, sc.type.value),
                "npv": "—",
                "irr": "—",
                "roi": "—",
                "payback": "—",
                "go_no_go": "—",
            })
        else:
            rows.append({
                "scenario": SCENARIO_LABELS.get(sc.type, sc.type.value),
                "npv": _fmt_money(
                    float(y1y10.npv) if y1y10.npv is not None else None
                ),
                "irr": _fmt_pct(
                    float(y1y10.irr) if y1y10.irr is not None else None
                ),
                "roi": _fmt_pct(
                    float(y1y10.roi) if y1y10.roi is not None else None
                ),
                "payback": (
                    f"{float(y1y10.payback_simple):.1f}"
                    if y1y10.payback_simple is not None
                    else "—"
                ),
                "go_no_go": (
                    "✓"
                    if y1y10.go_no_go
                    else ("✗" if y1y10.go_no_go is False else "—")
                ),
            })
    return rows


def _build_per_unit_kpi_rows(
    scenarios: list[Scenario],
    results_by_scenario: dict[int, list[ScenarioResult]],
) -> list[dict[str, str]]:
    """Phase 8.3: per-unit метрики Base сценария по 3 scope'ам."""
    base = next((s for s in scenarios if s.type == ScenarioType.BASE), None)
    if base is None:
        return []
    base_results = results_by_scenario.get(base.id, [])
    if not base_results:
        return []

    scope_order = [PeriodScope.Y1Y3, PeriodScope.Y1Y5, PeriodScope.Y1Y10]
    metrics = [
        ("Выручка / шт, ₽", "nr_per_unit"),
        ("GP / шт, ₽", "gp_per_unit"),
        ("CM / шт, ₽", "cm_per_unit"),
        ("EBITDA / шт, ₽", "ebitda_per_unit"),
    ]
    rows: list[dict[str, str]] = []
    for label, attr in metrics:
        row: dict[str, str] = {"metric": label}
        for scope in scope_order:
            r = next((x for x in base_results if x.period_scope == scope), None)
            val = getattr(r, attr, None) if r else None
            row[scope.value] = (
                _fmt_money(float(val), 2) if val is not None else "—"
            )
        rows.append(row)
    return rows


def _build_pnl_context(base_aggregate: Any | None) -> dict[str, Any]:
    """Возвращает {pnl_years, pnl_rows} или {pnl_years: [], pnl_rows: []}."""
    if base_aggregate is None or not base_aggregate.annual_free_cash_flow:
        return {"pnl_years": [], "pnl_rows": []}

    years = list(range(1, len(base_aggregate.annual_free_cash_flow) + 1))
    annual_metrics = [
        ("Net Revenue", base_aggregate.annual_net_revenue),
        ("Contribution", base_aggregate.annual_contribution),
        ("FCF", base_aggregate.annual_free_cash_flow),
        ("DCF", base_aggregate.annual_discounted_cash_flow),
        ("Cumulative FCF", base_aggregate.cumulative_fcf),
    ]
    # NB: ключ `cells`, а не `values` — в Jinja2 `.values` резолвится
    # как метод dict и ломает {% for v in row.values %}.
    rows = [
        {
            "label": label,
            "cells": [_fmt_money(v) for v in values],
        }
        for label, values in annual_metrics
    ]
    return {"pnl_years": years, "pnl_rows": rows}


def _build_bom_top(
    skus_with_bom: list[tuple[ProjectSKU, list[BOMItem]]],
) -> list[dict[str, str]]:
    ingredient_costs: dict[str, float] = {}
    for _psk, bom_items in skus_with_bom:
        for b in bom_items:
            cost = (
                float(b.quantity_per_unit)
                * float(b.price_per_unit)
                * (1 + float(b.loss_pct))
            )
            ingredient_costs[b.ingredient_name] = (
                ingredient_costs.get(b.ingredient_name, 0.0) + cost
            )
    top = sorted(ingredient_costs.items(), key=lambda x: x[1], reverse=True)[:10]
    return [{"name": name, "cost": _fmt_money(cost, decimals=2)} for name, cost in top]


def _build_fin_plan_rows(
    financial_plan: list[ProjectFinancialPlan],
    period_by_id: dict[int, Any],
) -> list[dict[str, str]]:
    fp_by_year: dict[int, tuple[float, float]] = {}
    for fp in financial_plan:
        period = period_by_id.get(fp.period_id)
        if period is None:
            continue
        year = period.model_year
        prev_capex, prev_opex = fp_by_year.get(year, (0.0, 0.0))
        fp_by_year[year] = (
            prev_capex + float(fp.capex),
            prev_opex + float(fp.opex),
        )

    rows: list[dict[str, str]] = []
    for year in range(1, 11):
        entry = fp_by_year.get(year)
        if entry is None:
            rows.append({"year": f"Y{year}", "capex": "—", "opex": "—"})
        else:
            capex_total, opex_total = entry
            rows.append({
                "year": f"Y{year}",
                "capex": _fmt_money(capex_total),
                "opex": _fmt_money(opex_total),
            })
    return rows


def _build_risks_list(project: Project) -> list[str]:
    risks_raw = project.risks or []
    out: list[str] = []
    for r in risks_raw:
        if isinstance(r, str):
            out.append(r)
        elif isinstance(r, dict) and "text" in r:
            out.append(str(r["text"]))
        else:
            out.append(str(r))
    return out


def _build_function_rows(project: Project) -> list[dict[str, str]]:
    func_raw = project.function_readiness or {}
    rows: list[dict[str, str]] = []
    if not isinstance(func_raw, dict):
        return rows
    for dept, entry in func_raw.items():
        if not isinstance(entry, dict):
            continue
        status_key = str(entry.get("status", "")).lower()
        if status_key not in ("green", "yellow", "red"):
            status_key = "none"
        rows.append({
            "dept": str(dept),
            "status_key": status_key,
            "status_label": FUNCTION_STATUS_LABELS.get(status_key, "—"),
            "notes": str(entry.get("notes", "") or ""),
        })
    return rows


def _build_roadmap_rows(project: Project) -> list[dict[str, str]]:
    roadmap_raw = project.roadmap_tasks or []
    rows: list[dict[str, str]] = []
    if not isinstance(roadmap_raw, list):
        return rows
    for task in roadmap_raw:
        if not isinstance(task, dict):
            continue
        rows.append({
            "name": str(task.get("name", "") or "—"),
            "start": str(task.get("start_date", "") or "—"),
            "end": str(task.get("end_date", "") or "—"),
            "status": str(task.get("status", "") or "—"),
            "owner": str(task.get("owner", "") or "—"),
        })
    return rows


def _build_approver_rows(project: Project) -> list[dict[str, str]]:
    approvers_raw = project.approvers or []
    rows: list[dict[str, str]] = []
    if not isinstance(approvers_raw, list):
        return rows
    for a in approvers_raw:
        if not isinstance(a, dict):
            continue
        # backward compat (ELEKTRA сид использует "approver", UI — "name")
        name = a.get("name") or a.get("approver") or "—"
        rows.append({
            "metric": str(a.get("metric", "") or "—"),
            "name": str(name) or "—",
            "source": str(a.get("source", "") or "—"),
        })
    return rows


def _build_package_images_context(
    skus_with_bom: list[tuple[ProjectSKU, list[BOMItem]]],
    package_images: dict[int, Path],
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for psk, _bom in skus_with_bom:
        if psk.package_image_id is None:
            continue
        img_path = package_images.get(psk.package_image_id)
        if img_path is None:
            continue
        # WeasyPrint читает file:// локальные пути. Передаём absolute.
        out.append({
            "path": str(img_path.resolve()),
            "caption": f"{psk.sku.brand} — {psk.sku.name}",
        })
    return out


# ============================================================
# Public entry point
# ============================================================


async def generate_project_pdf(
    session: AsyncSession,
    project_id: int,
) -> bytes:
    """Генерирует PDF для проекта через WeasyPrint, возвращает bytes.

    Raises:
        ProjectNotFoundForExport: если проект не найден.
    """
    project = await _load_project_full(session, project_id)
    if project is None:
        raise ProjectNotFoundForExport(f"Project {project_id} not found")

    # Данные проекта (аналогично ppt_exporter)
    inflation_profile: RefInflation | None = None
    if project.inflation_profile_id is not None:
        inflation_profile = await session.get(
            RefInflation, project.inflation_profile_id
        )

    skus_with_bom = await _load_skus_with_bom(session, project_id)
    psk_channels = await _load_psk_channels(session, project_id)
    package_images = await _load_package_images(session, skus_with_bom)

    fp_rows = (
        await session.scalars(
            select(ProjectFinancialPlan).where(
                ProjectFinancialPlan.project_id == project_id
            )
        )
    ).all()

    # Phase 8.8: OPEX по категориям маркетинга
    from app.models import OpexItem
    opex_by_category: dict[str, float] = {}
    if fp_rows:
        fp_ids = [fp.id for fp in fp_rows]
        opex_items = (
            await session.scalars(
                select(OpexItem).where(OpexItem.financial_plan_id.in_(fp_ids))
            )
        ).all()
        for oi in opex_items:
            cat = oi.category or "other"
            opex_by_category[cat] = opex_by_category.get(cat, 0.0) + float(oi.amount)

    sorted_periods, period_by_id = await _load_period_catalog(session)

    scenarios = (
        await session.scalars(
            select(Scenario).where(Scenario.project_id == project_id)
        )
    ).all()
    results_by_scenario = await _load_scenario_results(session, project_id)

    base_scenario = next(
        (s for s in scenarios if s.type == ScenarioType.BASE), None
    )
    base_aggregate: Any | None = None
    if base_scenario is not None and skus_with_bom and psk_channels:
        try:
            line_inputs = await build_line_inputs(
                session, project_id, base_scenario.id
            )
            capex, opex = await _load_project_financial_plan(
                session, project_id, sorted_periods
            )
            base_aggregate = run_project_pipeline(
                line_inputs, project_capex=capex, project_opex=opex
            )
        except Exception:  # noqa: BLE001
            base_aggregate = None

    # Sensitivity (Phase 8.4)
    sensitivity_data: dict | None = None
    if base_scenario is not None:
        try:
            from app.services.sensitivity_service import compute_sensitivity
            sensitivity_data = await compute_sensitivity(
                session, project_id, base_scenario.id
            )
        except Exception:  # noqa: BLE001
            sensitivity_data = None

    # Pricing + Value Chain (Phase 8.1 / 8.2)
    pricing_data: Any | None = None
    value_chain_data: Any | None = None
    try:
        from app.services.pricing_service import (
            build_pricing_summary,
            build_value_chain,
        )
        pricing_data = await build_pricing_summary(session, project)
        value_chain_data = await build_value_chain(session, project)
    except Exception:  # noqa: BLE001
        pass

    # Jinja2 context
    pnl_ctx = _build_pnl_context(base_aggregate)
    context: dict[str, Any] = {
        "project": project,
        "inflation_profile_name": (
            inflation_profile.profile_name if inflation_profile else "—"
        ),
        "validation_subtests": VALIDATION_SUBTESTS,
        "sku_rows": _build_sku_rows(skus_with_bom),
        "package_images": _build_package_images_context(
            skus_with_bom, package_images
        ),
        "kpi_rows": _build_kpi_rows(list(scenarios), results_by_scenario),
        "per_unit_kpi": _build_per_unit_kpi_rows(
            list(scenarios), results_by_scenario
        ),
        "pnl_years": pnl_ctx["pnl_years"],
        "pnl_rows": pnl_ctx["pnl_rows"],
        "bom_top": _build_bom_top(skus_with_bom),
        "fin_plan_rows": _build_fin_plan_rows(list(fp_rows), period_by_id),
        "risks_list": _build_risks_list(project),
        "function_rows": _build_function_rows(project),
        "roadmap_rows": _build_roadmap_rows(project),
        "approver_rows": _build_approver_rows(project),
        "gate_label": _gate_label,
        "fmt_money": _fmt_money,
        "fmt_pct": _fmt_pct,
        "sensitivity": sensitivity_data,
        "pricing": pricing_data,
        "value_chain": value_chain_data,
        "opex_by_category": dict(
            sorted(opex_by_category.items(), key=lambda x: x[1], reverse=True)
        ),
        "opex_category_labels": {
            "digital": "Digital", "ecom": "E-com", "ooh": "OOH", "pr": "PR",
            "smm": "SMM", "design": "Design", "research": "Research",
            "posm": "ПОСМ", "creative": "Creative", "special": "Special",
            "merch": "Merch", "tv": "TV", "listings": "Листинги", "other": "Другое",
        },
    }

    # Render HTML
    template = _jinja_env.get_template("project_passport.html")
    html_str = template.render(**context)

    # Render PDF via WeasyPrint. base_url нужен чтобы разрешить
    # относительные пути (для package images через file://).
    pdf_bytes = HTML(string=html_str, base_url=str(_TEMPLATES_DIR)).write_pdf()
    assert pdf_bytes is not None  # typing: write_pdf может вернуть None только если target задан
    return pdf_bytes
