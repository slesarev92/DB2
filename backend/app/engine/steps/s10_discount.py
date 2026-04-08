"""Шаг 10 — Аннуализация + Discounted Cash Flow + Terminal Value.

В отличие от шагов 1-9, которые работают на per-period gранулярности
(43 периода: M1..M36 + Y4..Y10), шаги 10-12 работают на годовой
гранулярности — 10 значений по model_year 1..10.

Аннуализация (новое в 2.3):
- M1..M36 → суммируются по 12 месяцев в каждый годовой бакет (Y1, Y2, Y3)
- Y4..Y10 → каждый период становится одним годовым бакетом
- В итоге: ровно 10 элементов в annual_* массивах

Аннуализируются: FCF, NR, CM (последние два — для contribution_margin
ratio на уровне всего проекта, нужно в s11/s12).

Discount (Excel: DATA row 44):
    DCF[year_idx] = ANNUAL_FCF[year_idx] / (1 + WACC)^year_idx
где year_idx = 0..9 (наш model_year 1..10 соответствует Excel year_label 0..9).

Cumulative для payback (Excel: DATA rows 56-57):
    cumulative_fcf[i] = Σ ANNUAL_FCF[0..i]
    cumulative_dcf[i] = Σ ANNUAL_DCF[0..i]

Terminal Value (Гордон, Excel: DATA row 47):
    g = FCF_last / FCF_prev          # подразумеваемый темп роста
    TV = FCF_last × g / (WACC − (1 − g))

D-07: TV — отдельный справочный показатель, **НЕ входит в NPV**. Считаем
только для полного 10-летнего горизонта (Y1-Y10). Защита от деления на 0
и от отрицательных FCF (g неопределён).
"""
from app.engine.context import PipelineContext


def step(ctx: PipelineContext) -> PipelineContext:
    inp = ctx.input
    n = inp.period_count

    if not ctx.free_cash_flow or not ctx.net_revenue or not ctx.contribution:
        raise RuntimeError(
            "s10_discount requires fcf (s09), net_revenue (s02), contribution (s05)"
        )

    # Аннуализация по model_year. Используем dict для буфера, потом сортируем.
    annual_fcf_buf: dict[int, float] = {}
    annual_nr_buf: dict[int, float] = {}
    annual_cm_buf: dict[int, float] = {}

    for t in range(n):
        year = inp.period_model_year[t]
        annual_fcf_buf[year] = annual_fcf_buf.get(year, 0.0) + ctx.free_cash_flow[t]
        annual_nr_buf[year] = annual_nr_buf.get(year, 0.0) + ctx.net_revenue[t]
        annual_cm_buf[year] = annual_cm_buf.get(year, 0.0) + ctx.contribution[t]

    # Сортируем по году. model_year обычно 1..10 — если меньше, не страшно.
    years_sorted = sorted(annual_fcf_buf.keys())
    annual_fcf = [annual_fcf_buf[y] for y in years_sorted]
    annual_nr = [annual_nr_buf[y] for y in years_sorted]
    annual_cm = [annual_cm_buf[y] for y in years_sorted]

    # Дисконтирование. WACC из Project, year_idx = 0, 1, ..., len-1.
    # year_idx = 0 для самого раннего модельного года (model_year=1).
    wacc = inp.wacc
    one_plus_wacc = 1.0 + wacc

    annual_dcf: list[float] = []
    factor = 1.0
    for fcf in annual_fcf:
        annual_dcf.append(fcf / factor)
        factor *= one_plus_wacc

    # Cumulative
    cum_fcf: list[float] = []
    cum_dcf: list[float] = []
    s_fcf = 0.0
    s_dcf = 0.0
    for fcf, dcf in zip(annual_fcf, annual_dcf):
        s_fcf += fcf
        s_dcf += dcf
        cum_fcf.append(s_fcf)
        cum_dcf.append(s_dcf)

    # Terminal Value (Гордон) для полного горизонта.
    # Защита: нужно как минимум 2 года и FCF_prev != 0.
    tv: float | None = None
    if len(annual_fcf) >= 2:
        fcf_last = annual_fcf[-1]
        fcf_prev = annual_fcf[-2]
        if fcf_prev != 0:
            try:
                g = fcf_last / fcf_prev
                denom = wacc - (1.0 - g)
                if denom != 0:
                    tv = (fcf_last * g) / denom
            except (ZeroDivisionError, OverflowError):
                tv = None

    ctx.annual_free_cash_flow = annual_fcf
    ctx.annual_discounted_cash_flow = annual_dcf
    ctx.cumulative_fcf = cum_fcf
    ctx.cumulative_dcf = cum_dcf
    ctx.annual_net_revenue = annual_nr
    ctx.annual_contribution = annual_cm
    ctx.terminal_value = tv
    return ctx
