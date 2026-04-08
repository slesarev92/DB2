"""Шаги расчётного pipeline.

Каждый шаг — чистая функция `step(ctx: PipelineContext) -> PipelineContext`.
Порядок вызова фиксирован (см. `pipeline.py`, задача 2.4):
    s01_volume → s02_price → s03_cogs → s04_gross_profit → s05_contribution
    → s06_ebitda → s07_working_capital → s08_tax → s09_cash_flow
    → s10_discount → s11_kpi → s12_gonogo

Каждая формула — с явной ссылкой на Excel источник и/или ADR-CE-xx.
"""
from app.engine.steps import (  # noqa: F401
    s01_volume,
    s02_price,
    s03_cogs,
    s04_gross_profit,
    s05_contribution,
    s06_ebitda,
    s07_working_capital,
    s08_tax,
    s09_cash_flow,
    s10_discount,
    s11_kpi,
    s12_gonogo,
)
