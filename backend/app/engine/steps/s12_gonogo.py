"""Шаг 12 — Go/No-Go решение по проекту.

Критерий (Excel: KPI sheet, верифицировано в TZ_VS_EXCEL_DISCREPANCIES):
    GREEN если NPV ≥ 0 AND CM_ratio ≥ 0.25
    RED   иначе

CM_ratio считается на весь проект (sum of CM / sum of NR), не per-year.
NPV проверяется per scope — потому что краткосрочные scopes (Y1-Y3)
обычно убыточны (инвестиционная фаза), а долгосрочные (Y1-Y10) выходят в плюс.

В выходе — словарь по трём скоупам: y1y3, y1y5, y1y10.
"""
from app.engine.context import PipelineContext

# Default порог CM для Go/No-Go. Настраивается per-project через
# PipelineInput.cm_threshold (поле Project.cm_threshold в БД).
CM_THRESHOLD_DEFAULT = 0.25


def step(ctx: PipelineContext) -> PipelineContext:
    if not ctx.npv:
        raise RuntimeError("s12_gonogo requires NPV from s11")

    # Берём порог из PipelineInput (per-project настройка, одобрено заказчиком 2026-04-13).
    cm_threshold = ctx.input.cm_threshold

    cm_ok = (
        ctx.contribution_margin_ratio is not None
        and ctx.contribution_margin_ratio >= cm_threshold
    )

    result: dict[str, bool] = {}
    for scope, npv_value in ctx.npv.items():
        result[scope] = (npv_value >= 0) and cm_ok

    ctx.go_no_go = result
    return ctx
