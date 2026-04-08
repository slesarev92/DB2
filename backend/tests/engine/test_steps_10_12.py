"""Unit + smoke + GORJI acceptance тесты для шагов 10-12.

s10: аннуализация + DCF + cumulative + Terminal Value
s11: NPV / IRR / ROI / Payback (3 скоупа) + CM ratio
s12: Go/No-Go (3 скоупа)

Acceptance против GORJI KPI sheet — основное здесь. Excel содержит
агрегаты по всему проекту в DATA rows 38-57 (NR, CM, FCF, DCF и т.д.),
которые мы можем подать в pipeline через прямую подстановку и сверить
с эталонными KPI.
"""
from __future__ import annotations

import pytest

from app.engine.context import PipelineContext, PipelineInput
from app.engine.steps import (
    s10_discount,
    s11_kpi,
    s12_gonogo,
)
from tests.engine.test_steps_1_5 import ctx_for, make_input


# ============================================================
# GORJI агрегаты Y0..Y9 из DATA sheet (10 элементов)
# Извлечено из PASSPORT_MODEL_GORJI_2025-09-05.xlsx, лист DATA, строки 18/27/43.
# ============================================================

GORJI_ANNUAL_NR = [
    257429.2954260194,
    38916021.28393693,
    105037831.006141,
    154757999.12997502,
    179092654.09783313,
    206580025.6383053,
    237656935.90251887,
    272736759.77649206,
    312276502.68838614,
    348348693.4202128,
]

GORJI_ANNUAL_CM = [
    108151.34599619916,
    -103998.54263893934,
    23206801.17562693,
    39154289.0388902,
    45700562.83436501,
    53059271.348391615,
    61390127.76947057,
    70805411.97698544,
    81429260.79629627,
    91098561.25044528,
]

GORJI_ANNUAL_FCF = [
    -6546718.438654163,
    -10183029.581260249,
     4971323.773837056,
    19414536.056252077,
    27400692.921349034,
    32597353.806356624,
    38503715.36199582,
    45211635.21374282,
    52814368.209492534,
    60586701.27051398,
]

# Из DATA row 44 — для сверки результата s10
GORJI_ANNUAL_DCF = [
    -6546718.438654163,
    -8557167.715344748,
     3510573.9522894262,
    11520892.720658453,
    13663869.326800345,
    13659900.606569195,
    13558787.98399234,
    13378933.193334563,
    13133376.597879723,
    12660610.697475815,
]

GORJI_WACC = 0.19
GORJI_NPV = {
    "y1y3":  -11593312.201709485,    # SUM(B44:D44) — 3 элемента
    "y1y5":   27251350.45231851,     # SUM(B44:G44) — 6 элементов (Excel quirk D-12)
    "y1y10":  79983058.92500097,     # SUM(B44:K44) — 10 элементов
}
GORJI_IRR = {
    "y1y3":  -0.6097262251770428,
    "y1y5":   0.641219209682006,
    "y1y10":  0.786343390702773,
}
GORJI_ROI = {
    "y1y3":  -0.23428174230389642,
    "y1y5":   0.6739905707028004,
    "y1y10":  1.5826332975973127,
}
# Excel: simple payback все 3 скоупа = 3
GORJI_PAYBACK_SIMPLE = {"y1y3": 3, "y1y5": 3, "y1y10": 3}
# Excel: discounted payback Y1-Y3 = "НЕ ОКУПАЕТСЯ" (4 > 3), Y1-Y5/Y10 = 4
GORJI_PAYBACK_DISC = {"y1y3": None, "y1y5": 4, "y1y10": 4}


def _build_gorji_ctx() -> PipelineContext:
    """Подсовывает агрегаты GORJI прямо в контекст, минуя s01..s09.

    В s10 нужны NR, CM, FCF (per-period). Подаём 10 годовых периодов
    как model_year=1..10 и подменяем выходы s02/s05/s09 нашими агрегатами.
    """
    n = 10
    inp = make_input(
        period_count=n,
        period_is_monthly=tuple([False] * n),
        period_month_num=tuple([None] * n),
        period_model_year=tuple(range(1, 11)),
        nd=tuple([0.5] * n),
        offtake=tuple([10.0] * n),
        shelf_price_reg=tuple([100.0] * n),
        seasonality=tuple([1.0] * n),
        wc_rate=0.12,
        tax_rate=0.20,
        wacc=GORJI_WACC,
    )
    ctx = ctx_for(inp)
    ctx.net_revenue = list(GORJI_ANNUAL_NR)
    ctx.contribution = list(GORJI_ANNUAL_CM)
    ctx.free_cash_flow = list(GORJI_ANNUAL_FCF)
    return ctx


# ============================================================
# s10 — Discount + Terminal Value
# ============================================================


class TestDiscount:
    def test_annualization_passthrough_for_yearly_periods(self):
        """10 годовых периодов → annual_* массивы длины 10 совпадают с input."""
        ctx = _build_gorji_ctx()
        s10_discount.step(ctx)
        assert len(ctx.annual_free_cash_flow) == 10
        assert ctx.annual_free_cash_flow == pytest.approx(GORJI_ANNUAL_FCF)
        assert ctx.annual_net_revenue == pytest.approx(GORJI_ANNUAL_NR)
        assert ctx.annual_contribution == pytest.approx(GORJI_ANNUAL_CM)

    def test_dcf_matches_excel(self):
        """DCF[t] = FCF[t] / (1+WACC)^t — сверка с DATA row 44."""
        ctx = _build_gorji_ctx()
        s10_discount.step(ctx)
        for i, expected in enumerate(GORJI_ANNUAL_DCF):
            assert ctx.annual_discounted_cash_flow[i] == pytest.approx(
                expected, rel=1e-9
            ), f"Y{i}: {ctx.annual_discounted_cash_flow[i]} vs {expected}"

    def test_cumulative_fcf_matches_excel(self):
        """cumulative_fcf[i] = SUM(FCF[0..i]) — DATA row 56."""
        ctx = _build_gorji_ctx()
        s10_discount.step(ctx)
        # Excel cumulative FCF (row 56)
        excel_cum_fcf = [
            -6546718.438654163,
            -16729748.019914411,
            -11758424.246077355,
            7656111.810174722,
            35056804.73152375,
            67654158.53788038,
            106157873.8998762,
            151369509.11361903,
            204183877.32311156,
            264770578.59362555,
        ]
        assert ctx.cumulative_fcf == pytest.approx(excel_cum_fcf, rel=1e-9)

    def test_cumulative_dcf_matches_excel(self):
        """cumulative_dcf[i] = SUM(DCF[0..i]) — DATA row 57."""
        ctx = _build_gorji_ctx()
        s10_discount.step(ctx)
        excel_cum_dcf = [
            -6546718.438654163,
            -15103886.153998911,
            -11593312.201709485,
            -72419.4810510315,
            13591449.845749313,
            27251350.45231851,
            40810138.43631085,
            54189071.629645415,
            67322448.22752514,
            79983058.92500097,
        ]
        assert ctx.cumulative_dcf == pytest.approx(excel_cum_dcf, rel=1e-9)

    def test_monthly_periods_aggregated_into_yearly(self):
        """M1..M12 (model_year=1) → один элемент в annual_* массиве."""
        n = 12
        inp = make_input(
            period_count=n,
            period_is_monthly=tuple([True] * n),
            period_month_num=tuple(range(1, 13)),
            period_model_year=tuple([1] * n),  # все принадлежат году 1
            nd=tuple([0.5] * n),
            offtake=tuple([10.0] * n),
            shelf_price_reg=tuple([100.0] * n),
            seasonality=tuple([1.0] * n),
        )
        ctx = ctx_for(inp)
        # Подсовываем фейковые per-period значения: каждый месяц = 100 ₽
        ctx.net_revenue = [100.0] * n
        ctx.contribution = [50.0] * n
        ctx.free_cash_flow = [10.0] * n
        s10_discount.step(ctx)

        assert len(ctx.annual_free_cash_flow) == 1
        assert ctx.annual_free_cash_flow[0] == pytest.approx(120.0)  # 12 × 10
        assert ctx.annual_net_revenue[0] == pytest.approx(1200.0)
        assert ctx.annual_contribution[0] == pytest.approx(600.0)

    def test_terminal_value_computed_for_full_horizon(self):
        """TV = FCF_last × g / (WACC − (1 − g)) — DATA row 47 col 4."""
        ctx = _build_gorji_ctx()
        s10_discount.step(ctx)
        # Excel: 206140022.44781345 (это TV для Y1-Y10, не Y1-Y3 или Y1-Y5)
        assert ctx.terminal_value == pytest.approx(
            206140022.44781345, rel=1e-9
        )


# ============================================================
# s11 — KPI
# ============================================================


class TestKpi:
    def test_npv_three_scopes_match_excel(self):
        ctx = _build_gorji_ctx()
        s10_discount.step(ctx)
        s11_kpi.step(ctx)

        for scope, expected in GORJI_NPV.items():
            assert ctx.npv[scope] == pytest.approx(expected, rel=1e-9), (
                f"NPV {scope}: {ctx.npv[scope]} vs {expected}"
            )

    def test_irr_three_scopes_match_excel(self):
        ctx = _build_gorji_ctx()
        s10_discount.step(ctx)
        s11_kpi.step(ctx)

        for scope, expected in GORJI_IRR.items():
            actual = ctx.irr[scope]
            assert actual is not None
            assert actual == pytest.approx(expected, rel=1e-6), (
                f"IRR {scope}: {actual} vs {expected}"
            )

    def test_roi_three_scopes_match_excel(self):
        ctx = _build_gorji_ctx()
        s10_discount.step(ctx)
        s11_kpi.step(ctx)

        for scope, expected in GORJI_ROI.items():
            assert ctx.roi[scope] == pytest.approx(expected, rel=1e-9), (
                f"ROI {scope}: {ctx.roi[scope]} vs {expected}"
            )

    def test_payback_simple_match_excel(self):
        ctx = _build_gorji_ctx()
        s10_discount.step(ctx)
        s11_kpi.step(ctx)
        assert ctx.payback_simple == GORJI_PAYBACK_SIMPLE

    def test_payback_discounted_match_excel(self):
        ctx = _build_gorji_ctx()
        s10_discount.step(ctx)
        s11_kpi.step(ctx)
        assert ctx.payback_discounted == GORJI_PAYBACK_DISC

    def test_contribution_margin_ratio(self):
        """CM_ratio = SUM(CM) / SUM(NR) для всего горизонта."""
        ctx = _build_gorji_ctx()
        s10_discount.step(ctx)
        s11_kpi.step(ctx)

        expected_ratio = sum(GORJI_ANNUAL_CM) / sum(GORJI_ANNUAL_NR)
        assert ctx.contribution_margin_ratio == pytest.approx(expected_ratio)
        # Для GORJI ≈ 25.1% (на грани go/no-go threshold 25%)
        assert ctx.contribution_margin_ratio > 0.25
        assert ctx.contribution_margin_ratio < 0.26


# ============================================================
# s12 — Go/No-Go
# ============================================================


class TestGoNoGo:
    def test_gorji_y1y10_is_green(self):
        """GORJI Y1-Y10: NPV=80M ≥ 0 AND CM ratio=25.1% ≥ 25% → GREEN."""
        ctx = _build_gorji_ctx()
        s10_discount.step(ctx)
        s11_kpi.step(ctx)
        s12_gonogo.step(ctx)

        assert ctx.go_no_go["y1y10"] is True

    def test_gorji_y1y3_is_red(self):
        """GORJI Y1-Y3: NPV=−11.6M < 0 → RED, независимо от CM."""
        ctx = _build_gorji_ctx()
        s10_discount.step(ctx)
        s11_kpi.step(ctx)
        s12_gonogo.step(ctx)

        assert ctx.go_no_go["y1y3"] is False

    def test_gorji_y1y5_is_green(self):
        """GORJI Y1-Y5: NPV=27.3M ≥ 0 AND CM ratio=25.1% ≥ 25% → GREEN."""
        ctx = _build_gorji_ctx()
        s10_discount.step(ctx)
        s11_kpi.step(ctx)
        s12_gonogo.step(ctx)

        assert ctx.go_no_go["y1y5"] is True

    def test_low_cm_ratio_blocks_go(self):
        """Если CM ratio < 25%, даже положительный NPV → RED."""
        ctx = _build_gorji_ctx()
        s10_discount.step(ctx)
        s11_kpi.step(ctx)
        # Принудительно занижаем CM
        ctx.contribution_margin_ratio = 0.20
        s12_gonogo.step(ctx)
        # Все scopes должны стать RED, потому что CM low
        assert ctx.go_no_go["y1y10"] is False
        assert ctx.go_no_go["y1y5"] is False
        assert ctx.go_no_go["y1y3"] is False

    def test_zero_npv_threshold(self):
        """NPV ровно 0 — должно быть GREEN (≥, не >)."""
        ctx = _build_gorji_ctx()
        s10_discount.step(ctx)
        s11_kpi.step(ctx)
        ctx.npv["y1y10"] = 0.0
        ctx.contribution_margin_ratio = 0.30
        s12_gonogo.step(ctx)
        assert ctx.go_no_go["y1y10"] is True

    def test_zero_cm_threshold(self):
        """CM ровно 25% — должно быть GREEN (≥)."""
        ctx = _build_gorji_ctx()
        s10_discount.step(ctx)
        s11_kpi.step(ctx)
        ctx.contribution_margin_ratio = 0.25
        s12_gonogo.step(ctx)
        assert ctx.go_no_go["y1y10"] is True
