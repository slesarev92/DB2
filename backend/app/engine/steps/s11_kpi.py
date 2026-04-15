"""Шаг 11 — KPI: NPV, IRR, ROI, Payback (для трёх скоупов: Y1Y3, Y1Y5, Y1Y10).

Каждый KPI рассчитывается для трёх горизонтов:
- y1y3:  первые 3 года
- y1y5:  первые 6 (!) лет — Excel-quirk, см. ниже
- y1y10: все 10 лет

**ВАЖНО — Excel quirk в скоупе Y1-Y5:**
Excel формула NPV (DATA col 3 row 48): `=SUM(B44:G44)` — суммирует
6 столбцов (B,C,D,E,F,G), не 5. Аналогично ROI и IRR используют
6-элементные диапазоны для скоупа Y1-Y5. Это похоже на typo в Excel
(должно было быть `B44:F44`), но Excel = источник истины (ADR-CE-01),
поэтому реализуем как есть. Зафиксировано в TZ_VS_EXCEL_DISCREPANCIES.md
как D-12.

Для скоупов Y1-Y3 и Y1-Y10 границы согласуются с label'ом (3 и 10 лет).

Формулы (Excel: DATA rows 48-52):

NPV (row 48):
    NPV[scope] = Σ ANNUAL_DCF[0:end[scope]]

ROI (row 49, Excel-формула, см. D-06):
    ROI[scope] = (−SUM(FCF[0:end]) / (SUMIF(FCF[0:end], "<0") − 1)) / end
Эта формула — аннуализированная "среднегодовая доходность на единицу
инвестированного капитала". `−1` в знаменателе предотвращает деление
на ноль если все FCF положительные.

IRR (row 50): собственный Newton-Raphson + bisection (см. backend/app/engine/irr.py).

Payback simple (row 51):
    count = число лет где cumulative_fcf[i] < 0
    payback = count если count ≤ scope_years иначе None ("НЕ ОКУПАЕТСЯ")

Payback discounted (row 52): аналогично, но cumulative_dcf.

Contribution Margin overall ratio:
    CM_ratio = SUM(annual_contribution) / SUM(annual_net_revenue)
Один на весь проект (одинаков для всех скоупов в текущей реализации
потому что используется в Go/No-Go только).
"""
from app.engine.context import PipelineContext
from app.engine.irr import irr as irr_solver

# Скоуп → (end_index_exclusive, threshold_years_for_payback).
# end_index определяет slice annual_*[0:end].
# threshold_years — для payback: если число "негативных" лет > threshold → None.
SCOPE_BOUNDS: dict[str, tuple[int, int]] = {
    "y1y3":  (3,  3),
    "y1y5":  (5,  5),    # D-12 fix: исправлено с 6 на 5 (было Excel-тайпо, одобрено заказчиком 2026-04-13)
    "y1y10": (10, 10),
}


def _scope_npv(annual_dcf: list[float], end: int) -> float:
    return sum(annual_dcf[:end])


def _scope_roi(annual_fcf: list[float], end: int) -> float:
    """Excel-формула ROI (D-06): (−SUM/(SUMIF<0 − 1)) / COUNT.

    Знак результата зависит от соотношения общего FCF и негативной части.
    """
    sl = annual_fcf[:end]
    n = len(sl)
    if n == 0:
        return 0.0
    s = sum(sl)
    neg = sum(x for x in sl if x < 0)
    denom = neg - 1.0  # «−1» защита от деления на 0 (Excel quirk)
    if denom == 0:
        return 0.0
    return (-s / denom) / n


def _scope_payback(
    cumulative: list[float],
    fcf: list[float],
    end: int,
    threshold_years: int,
) -> float | None:
    """Payback с линейной интерполяцией (4.4 — engine audit).

    Возвращает дробное число лет до момента когда cumulative FCF/DCF
    пересекает ноль. Логика:
    - Найти первый год с cumulative[i] >= 0 (переход из минуса в ноль).
    - fraction = |cumulative[i-1]| / fcf[i]  (доля года потраченная после
      начала годового периода до момента выхода в ноль).
    - payback_years = i + fraction  где i — 0-based индекс пересечения,
      соответствующий "i полных лет после Y0, плюс fraction дополнительного
      года внутри Y(i+1)".
    - Scope threshold: если payback_years > threshold_years → None.

    Возвращает float (было int до 4.4). D-23 в TZ_VS_EXCEL_DISCREPANCIES.md:
    Excel считает целое число лет (count строк где cumulative<0); наша
    реализация даёт точнее для принятия Gate-решений (3.7 vs 4 года).

    Для simple payback используется cumulative_fcf, для discounted —
    cumulative_dcf; логика идентична.
    """
    if not cumulative or not fcf:
        return None

    # Найти первый год выхода в плюс
    crossing = None
    for i in range(len(cumulative)):
        if cumulative[i] >= 0:
            crossing = i
            break
    if crossing is None:
        return None  # не окупается за весь горизонт

    # Y1 сразу положительный — нет prior cumulative, payback < 1 года
    # (проект с FCF[0] > 0 имеет "almost instant" payback). Возвращаем
    # fraction как |prior|/fcf[0], но prior = 0 → 0. Для единообразия
    # UX показываем 1.0 как минимум (не окупается быстрее чем за год).
    if crossing == 0:
        return 1.0

    prev_cum = cumulative[crossing - 1]  # последнее отрицательное значение
    year_fcf = fcf[crossing]  # FCF года окупаемости
    if year_fcf <= 0:
        # Cumulative повысился с -X до -Y при negative FCF — мат. невозможно
        # при корректном вычислении cumulative. Fallback на integer count.
        return float(crossing + 1)

    fraction = abs(prev_cum) / year_fcf
    # `crossing` — 0-based индекс, значит crossing полных лет прошло
    # ДО этого года, плюс fraction текущего года.
    payback_years = crossing + fraction

    if payback_years > threshold_years:
        return None
    return payback_years


def step(ctx: PipelineContext) -> PipelineContext:
    if not ctx.annual_free_cash_flow or not ctx.annual_discounted_cash_flow:
        raise RuntimeError("s11_kpi requires annualized FCF/DCF from s10")

    afcf = ctx.annual_free_cash_flow
    adcf = ctx.annual_discounted_cash_flow

    npv_out: dict[str, float] = {}
    irr_out: dict[str, float | None] = {}
    roi_out: dict[str, float] = {}
    pb_simple: dict[str, int | None] = {}
    pb_disc: dict[str, int | None] = {}

    for scope, (end, thr) in SCOPE_BOUNDS.items():
        npv_out[scope] = _scope_npv(adcf, end)
        irr_out[scope] = irr_solver(afcf[:end])
        roi_out[scope] = _scope_roi(afcf, end)
        pb_simple[scope] = _scope_payback(ctx.cumulative_fcf, afcf, end, thr)
        pb_disc[scope] = _scope_payback(ctx.cumulative_dcf, afcf, end, thr)

    # Contribution Margin overall ratio (один на проект).
    total_nr = sum(ctx.annual_net_revenue)
    total_cm = sum(ctx.annual_contribution)
    cm_ratio: float | None = None
    if total_nr != 0:
        cm_ratio = total_cm / total_nr

    ctx.npv = npv_out
    ctx.irr = irr_out
    ctx.roi = roi_out
    ctx.payback_simple = pb_simple
    ctx.payback_discounted = pb_disc
    ctx.contribution_margin_ratio = cm_ratio
    return ctx
