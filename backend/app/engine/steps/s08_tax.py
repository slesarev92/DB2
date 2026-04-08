"""Шаг 8 — Налог на прибыль.

Формула (Excel: DATA row 40, см. ADR-CE-04 / D-03):
    TAX[t] = −(CONTRIBUTION[t] × TAX_RATE)   если CONTRIBUTION[t] ≥ 0
    TAX[t] = 0                                если CONTRIBUTION[t] < 0

**База налога — Contribution**, не EBITDA и не бухгалтерская прибыль.
Это упрощение, зафиксированное в Excel. Для production-grade расчёта
налога потребуется уточнение (Этап 2 после MVP).

**Знак отрицательный** — это отток денег. В s09 (CashFlow) tax
складывается с Contribution напрямую: `OCF = CM + ΔWC + tax`.

**Нет налогового щита при убытке.** Если контрибуция отрицательна,
налог = 0, а не отрицательный (что давало бы возмещение). Это упрощение
Excel-модели — отражает консервативный подход к убыточным периодам.

Эталон Excel DATA Y0/Y1 (агрегат GORJI):
    Contribution(Y0) = 108151.35 → tax(Y0) = −(108151.35 × 0.20) = −21630.27 ✓
    Contribution(Y1) = −103998.54 → tax(Y1) = 0 (убыток, нет щита) ✓
"""
from app.engine.context import PipelineContext


def step(ctx: PipelineContext) -> PipelineContext:
    inp = ctx.input
    n = inp.period_count

    if not ctx.contribution:
        raise RuntimeError("s08_tax requires contribution from s05")

    tax_rate = inp.tax_rate

    tax: list[float] = [0.0] * n
    for t in range(n):
        cm = ctx.contribution[t]
        if cm >= 0:
            tax[t] = -(cm * tax_rate)
        else:
            tax[t] = 0.0

    ctx.tax = tax
    return ctx
