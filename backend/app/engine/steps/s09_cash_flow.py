"""Шаг 9 — Cash Flow (OCF, ICF, FCF).

Формулы (Excel: DATA rows 41-43):
    OCF[t] = CONTRIBUTION[t] + ΔWC[t] + TAX[t]
    ICF[t] = −CAPEX[t]
    FCF[t] = OCF[t] + ICF[t]

`tax[t]` уже отрицательный (см. s08), поэтому здесь складывается
напрямую — не вычитается. То же с ΔWC: при росте выручки WC растёт,
ΔWC отрицательный, OCF уменьшается.

`capex` на per-line уровне обычно 0 — это project-level затраты,
которые добавляются оркестратором (задача 2.4). Если `input.capex`
пустой (default), трактуется как нули по всему горизонту.

Эталон Excel DATA Y0/Y1 (агрегат GORJI):
    CM(Y0)  =  108151.35    ΔWC(Y0) = −30891.51    tax(Y0) = −21630.27
    OCF(Y0) =  108151.35 − 30891.51 − 21630.27 = 55629.57 ✓
    capex(Y0) = 6602348      ICF(Y0) = −6602348
    FCF(Y0) = 55629.57 − 6602348 = −6546718.43 ✓

    CM(Y1)  = −103998.54     ΔWC(Y1) = −4639031.04    tax(Y1) = 0
    OCF(Y1) = −103998.54 − 4639031.04 + 0 = −4743029.58 ✓
    capex(Y1) = 5440000      ICF(Y1) = −5440000
    FCF(Y1) = −4743029.58 − 5440000 = −10183029.58 ✓
"""
from app.engine.context import PipelineContext


def step(ctx: PipelineContext) -> PipelineContext:
    inp = ctx.input
    n = inp.period_count

    if not ctx.contribution or not ctx.delta_working_capital or not ctx.tax:
        raise RuntimeError(
            "s09_cash_flow requires contribution (s05), delta_wc (s07), tax (s08)"
        )

    # capex может быть пустым → трактуем как нули
    capex = inp.capex if inp.capex else (0.0,) * n

    ocf: list[float] = [0.0] * n
    icf: list[float] = [0.0] * n
    fcf: list[float] = [0.0] * n

    for t in range(n):
        ocf[t] = ctx.contribution[t] + ctx.delta_working_capital[t] + ctx.tax[t]
        icf[t] = -capex[t]
        fcf[t] = ocf[t] + icf[t]

    ctx.operating_cash_flow = ocf
    ctx.investing_cash_flow = icf
    ctx.free_cash_flow = fcf
    return ctx
