"""Шаг 7 — Working Capital и ΔWC.

Формула (Excel: DATA rows 38-39, см. ADR-CE-02 / D-01):
    WC[t]       = NET_REVENUE[t] × WC_RATE
    ΔWC[t]      = WC[t-1] − WC[t]            (для t > 0)
    ΔWC[0]      = 0 − WC[0] = −WC[0]         (граничный случай)

`WC_RATE` — параметр уровня Project (default = 0.12, см. D-01).

**Почему ТЗ-формула неверна (для контекста):** ТЗ предлагает
`OCF = CM × (1 − 0.12) − tax`, что трактует 12% как постоянное удержание
от Contribution каждый период. Это ошибочно по двум причинам:
1. Working capital привязан к **выручке**, а не к Contribution.
2. В OCF влияет **изменение** WC (ΔWC), а не уровень. Когда выручка
   стабилизируется, ΔWC → 0 и WC перестаёт оттягивать деньги.

См. ADR-CE-02 для численных примеров.

Эталон Excel DATA Y0/Y1 (для агрегата проекта GORJI):
    NR(Y0) = 257429, WC(Y0) = 257429 × 0.12 = 30891.51 ✓
    ΔWC(Y0) = 0 − 30891.51 = −30891.51 ✓ (граничный случай t=0)
    NR(Y1) = 38916021, WC(Y1) = 38916021 × 0.12 = 4669922.55 ✓
    ΔWC(Y1) = 30891.51 − 4669922.55 = −4639031.04 ✓
"""
from app.engine.context import PipelineContext


def step(ctx: PipelineContext) -> PipelineContext:
    inp = ctx.input
    n = inp.period_count

    if not ctx.net_revenue:
        raise RuntimeError("s07_working_capital requires net_revenue from s02")

    wc_rate = inp.wc_rate

    wc: list[float] = [0.0] * n
    delta_wc: list[float] = [0.0] * n

    for t in range(n):
        wc[t] = ctx.net_revenue[t] * wc_rate

    # ΔWC[0] = 0 − WC[0] (граничный случай — нет предыдущего периода)
    # ΔWC[t] = WC[t-1] − WC[t] для t > 0
    if n > 0:
        delta_wc[0] = -wc[0]
        for t in range(1, n):
            delta_wc[t] = wc[t - 1] - wc[t]

    ctx.working_capital = wc
    ctx.delta_working_capital = delta_wc
    return ctx
