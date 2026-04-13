"""Sensitivity Service — анализ чувствительности NPV/CM к параметрам.

Цель (задача 4.4 / E-09):
Для базового сценария проекта прогнать pipeline с модифицированными
параметрами и получить матрицу:

    rows = уровни изменения {-20%, -10%, 0%, +10%, +20%}
    cols = параметры {ND, offtake, shelf_price, COGS}

Каждая ячейка = NPV Y1-Y10 + Contribution Margin ratio для проекта
с этим параметром умноженным на (1 + delta).

Реализация:
- Один build_line_inputs из БД (heavy step с DB queries)
- 4 параметра × 5 уровней = 20 in-memory pipeline runs (легко, ~50ms)
- Возвращаем структуру для UI

Pipeline pure functions работают на dataclass'ах, мы создаём
модифицированные копии PipelineInput через `dataclasses.replace`.
"""
from __future__ import annotations

from dataclasses import replace

from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.context import PipelineInput
from app.engine.pipeline import run_project_pipeline
from app.services.calculation_service import (
    _load_period_catalog,
    _load_project_financial_plan,
    build_line_inputs,
)


# Стандартные уровни (как в ТЗ E-09)
SENSITIVITY_DELTAS: tuple[float, ...] = (-0.20, -0.10, 0.0, 0.10, 0.20)

# Параметры — ключи для UI
PARAM_ND = "nd"
PARAM_OFFTAKE = "offtake"
PARAM_SHELF = "shelf_price"
PARAM_COGS = "cogs"

SENSITIVITY_PARAMS: tuple[str, ...] = (
    PARAM_ND,
    PARAM_OFFTAKE,
    PARAM_SHELF,
    PARAM_COGS,
)


def _scale_tuple(values: tuple[float, ...], factor: float) -> tuple[float, ...]:
    """Умножает каждый элемент tuple на factor."""
    return tuple(v * factor for v in values)


def _modify_input(
    inp: PipelineInput,
    parameter: str,
    delta: float,
) -> PipelineInput:
    """Возвращает копию PipelineInput с одним параметром изменённым на (1+delta).

    Все 4 параметра — per-period tuples в нашем PipelineInput. Используем
    `dataclasses.replace` для иммутабельной модификации (frozen dataclass).
    """
    factor = 1.0 + delta
    if parameter == PARAM_ND:
        return replace(inp, nd=_scale_tuple(inp.nd, factor))
    if parameter == PARAM_OFFTAKE:
        return replace(inp, offtake=_scale_tuple(inp.offtake, factor))
    if parameter == PARAM_SHELF:
        return replace(
            inp, shelf_price_reg=_scale_tuple(inp.shelf_price_reg, factor)
        )
    if parameter == PARAM_COGS:
        # COGS = bom_unit_cost (material + package per period). Production
        # cost rate не модифицируется — это % от ex_factory, не absolute.
        return replace(
            inp, bom_unit_cost=_scale_tuple(inp.bom_unit_cost, factor)
        )
    raise ValueError(f"Unknown sensitivity parameter: {parameter!r}")


VALID_SCOPES = ("y1y3", "y1y5", "y1y10")


async def compute_sensitivity(
    session: AsyncSession,
    project_id: int,
    scenario_id: int,
    scope: str = "y1y10",
) -> dict:
    """Запускает sensitivity analysis для проекта × сценария.

    Args:
        scope: Горизонт NPV — "y1y3", "y1y5" или "y1y10" (default).

    Returns:
        dict с структурой:
        {
            "scope": "y1y10",
            "base_npv_y1y10": float,
            "base_cm_ratio": float | None,
            "deltas": [-0.20, -0.10, 0.0, 0.10, 0.20],
            "params": ["nd", "offtake", "shelf_price", "cogs"],
            "cells": [
                {
                    "parameter": "nd",
                    "delta": -0.20,
                    "npv_y1y10": -5000000.0,
                    "cm_ratio": 0.18,
                },
                ...  # 4 × 5 = 20 ячеек
            ]
        }
    """
    if scope not in VALID_SCOPES:
        scope = "y1y10"

    line_inputs = await build_line_inputs(session, project_id, scenario_id)
    sorted_periods, _ = await _load_period_catalog(session)
    capex, opex = await _load_project_financial_plan(
        session, project_id, sorted_periods
    )

    # Base прогон (для reference в UI)
    base_agg = run_project_pipeline(
        line_inputs, project_capex=capex, project_opex=opex
    )
    base_npv = base_agg.npv.get(scope)
    base_cm_ratio = base_agg.contribution_margin_ratio

    cells: list[dict] = []
    for parameter in SENSITIVITY_PARAMS:
        for delta in SENSITIVITY_DELTAS:
            if delta == 0.0:
                # Base уровень — повторяет base_agg, не нужен отдельный run
                npv = base_npv
                cm_ratio = base_cm_ratio
            else:
                # Модифицируем все line_inputs одинаково
                modified_inputs = [
                    _modify_input(inp, parameter, delta)
                    for inp in line_inputs
                ]
                agg = run_project_pipeline(
                    modified_inputs,
                    project_capex=capex,
                    project_opex=opex,
                )
                npv = agg.npv.get(scope)
                cm_ratio = agg.contribution_margin_ratio

            cells.append(
                {
                    "parameter": parameter,
                    "delta": delta,
                    "npv_y1y10": npv,
                    "cm_ratio": cm_ratio,
                }
            )

    return {
        "scope": scope,
        "base_npv_y1y10": base_npv,
        "base_cm_ratio": base_cm_ratio,
        "deltas": list(SENSITIVITY_DELTAS),
        "params": list(SENSITIVITY_PARAMS),
        "cells": cells,
    }
