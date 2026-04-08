"""Шаг 4 — Gross Profit.

Формула (Excel: DATA row 23):
    GROSS_PROFIT[t] = NET_REVENUE[t] − COGS_TOTAL[t]

ВАЖНО: Gross Profit в Excel **не** включает вычет логистики. Логистика
вычитается на следующем шаге (s05 Contribution). Это отличается от
плановой формулы (`GP = NR − COGS − LOGISTICS`), см. ADR-CE-01 —
Excel-семантика приоритетна, план скорректирован в этом коммите.
"""
from app.engine.context import PipelineContext


def step(ctx: PipelineContext) -> PipelineContext:
    if not ctx.net_revenue or not ctx.cogs_total:
        raise RuntimeError(
            "s04_gross_profit requires net_revenue (s02) and cogs_total (s03)"
        )

    n = ctx.input.period_count
    gp: list[float] = [0.0] * n
    for t in range(n):
        gp[t] = ctx.net_revenue[t] - ctx.cogs_total[t]

    ctx.gross_profit = gp
    return ctx
