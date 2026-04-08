"""Шаг 6 — EBITDA.

Формула (Excel: DATA rows 29-31, см. также D-05):
    CA_M_COST[t]      = NET_REVENUE[t] × CA_M_RATE
    MARKETING_COST[t] = NET_REVENUE[t] × MARKETING_RATE
    EBITDA[t]         = CONTRIBUTION[t] − CA_M_COST[t] − MARKETING_COST[t]

CA&M (КАиУР) и Marketing — % от выручки на уровне ProjectSKU. По D-05
именно эти статьи Excel вычитает на уровне EBITDA, а не на уровне
Contribution (как ТЗ предлагал). Excel = источник истины.

Эталон GORJI SKU_1/HM (DASH row 48 col D):
    EBITDA per unit (M1-M3) = 5.662 ₽
    EBITDA per unit (M4-M6) = 4.6977 ₽ (после апрельской инфляции — GP падает,
                                         logistics растёт, ставки CA&M/Mkt
                                         фиксированные)
"""
from app.engine.context import PipelineContext


def step(ctx: PipelineContext) -> PipelineContext:
    inp = ctx.input
    n = inp.period_count

    if not ctx.contribution or not ctx.net_revenue:
        raise RuntimeError(
            "s06_ebitda requires contribution (s05) and net_revenue (s02)"
        )

    ca_m_rate = inp.ca_m_rate
    mkt_rate = inp.marketing_rate

    ca_m: list[float] = [0.0] * n
    mkt: list[float] = [0.0] * n
    ebitda: list[float] = [0.0] * n

    for t in range(n):
        nr = ctx.net_revenue[t]
        c = nr * ca_m_rate
        m = nr * mkt_rate
        ca_m[t] = c
        mkt[t] = m
        ebitda[t] = ctx.contribution[t] - c - m

    ctx.ca_m_cost = ca_m
    ctx.marketing_cost = mkt
    ctx.ebitda = ebitda
    return ctx
