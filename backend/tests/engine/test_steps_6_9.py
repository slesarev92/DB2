"""Unit + smoke тесты для шагов 6-9 расчётного ядра.

Шаги:
- s06_ebitda: EBITDA = CM − NR × CA_M_RATE − NR × MARKETING_RATE
- s07_working_capital: WC[t] = NR[t] × wc_rate; ΔWC[t] = WC[t-1] − WC[t]
- s08_tax: TAX[t] = −(CM × tax_rate) если CM≥0, иначе 0
- s09_cash_flow: OCF = CM + ΔWC + TAX; ICF = −CAPEX; FCF = OCF + ICF

Acceptance против GORJI Excel для EBITDA — в test_gorji_reference.py
(добавлено вместе с тестами 2.2). Здесь — формульные unit-тесты на
синтетических данных с особым вниманием к граничным случаям:
- ΔWC[0] = −WC[0] (нет предыдущего периода)
- TAX = 0 при отрицательной Contribution (нет налогового щита)
- Знак налога отрицательный (отток)
"""
from __future__ import annotations

import pytest

from app.engine.context import PipelineContext, PipelineInput
from app.engine.steps import (
    s01_volume,
    s02_price,
    s03_cogs,
    s04_gross_profit,
    s05_contribution,
    s06_ebitda,
    s07_working_capital,
    s08_tax,
    s09_cash_flow,
)
from tests.engine.test_steps_1_5 import ctx_for, make_input


def run_through_s05(inp: PipelineInput) -> PipelineContext:
    ctx = ctx_for(inp)
    s01_volume.step(ctx)
    s02_price.step(ctx)
    s03_cogs.step(ctx)
    s04_gross_profit.step(ctx)
    s05_contribution.step(ctx)
    return ctx


# ============================================================
# s06 — EBITDA
# ============================================================


class TestEbitda:
    def test_ebitda_subtracts_ca_m_and_marketing(self):
        # NR × ca_m + NR × mkt вычитается из CM
        inp = make_input(
            ca_m_rate=0.10,
            marketing_rate=0.05,
        )
        ctx = run_through_s05(inp)
        s06_ebitda.step(ctx)

        nr = ctx.net_revenue[0]
        cm = ctx.contribution[0]
        expected_ca_m = nr * 0.10
        expected_mkt = nr * 0.05
        expected_eb = cm - expected_ca_m - expected_mkt

        assert ctx.ca_m_cost[0] == pytest.approx(expected_ca_m)
        assert ctx.marketing_cost[0] == pytest.approx(expected_mkt)
        assert ctx.ebitda[0] == pytest.approx(expected_eb)

    def test_zero_rates_means_ebitda_equals_contribution(self):
        inp = make_input(ca_m_rate=0.0, marketing_rate=0.0)
        ctx = run_through_s05(inp)
        s06_ebitda.step(ctx)
        assert ctx.ebitda[0] == pytest.approx(ctx.contribution[0])

    def test_s06_requires_s05(self):
        inp = make_input()
        ctx = ctx_for(inp)
        # s05 не прогнан → contribution пустой
        with pytest.raises(RuntimeError, match="s06_ebitda requires"):
            s06_ebitda.step(ctx)


# ============================================================
# s07 — Working Capital (D-01 / ADR-CE-02)
# ============================================================


class TestWorkingCapital:
    def test_wc_is_nr_times_wc_rate(self):
        inp = make_input(wc_rate=0.12)
        ctx = run_through_s05(inp)
        s07_working_capital.step(ctx)
        assert ctx.working_capital[0] == pytest.approx(ctx.net_revenue[0] * 0.12)

    def test_delta_wc_at_t0_is_negative_wc(self):
        """Граничный случай: ΔWC[0] = 0 − WC[0] = −WC[0].

        Это критично — если забыть, OCF в первом периоде будет завышен.
        Эталон Excel DATA Y0: ΔWC = −30891.51, WC = 30891.51 → ΔWC = −WC. ✓
        """
        inp = make_input(wc_rate=0.12)
        ctx = run_through_s05(inp)
        s07_working_capital.step(ctx)
        assert ctx.delta_working_capital[0] == pytest.approx(-ctx.working_capital[0])

    def test_delta_wc_multi_period(self):
        # 3 периода с растущей выручкой → ΔWC всегда отрицательный
        # (WC растёт, ΔWC = WC[t-1] − WC[t] < 0)
        inp = make_input(
            period_count=3,
            period_is_monthly=(True, True, True),
            period_month_num=(1, 2, 3),
            period_model_year=(1, 1, 1),
            nd=(0.2, 0.5, 0.8),  # растёт → NR растёт → WC растёт
            offtake=(10.0, 10.0, 10.0),
            shelf_price_reg=(100.0, 100.0, 100.0),
            seasonality=(1.0, 1.0, 1.0),
            wc_rate=0.12,
        )
        ctx = run_through_s05(inp)
        s07_working_capital.step(ctx)

        wc = ctx.working_capital
        dwc = ctx.delta_working_capital

        # ΔWC[0] = −WC[0]
        assert dwc[0] == pytest.approx(-wc[0])
        # ΔWC[1] = WC[0] − WC[1]
        assert dwc[1] == pytest.approx(wc[0] - wc[1])
        # ΔWC[2] = WC[1] − WC[2]
        assert dwc[2] == pytest.approx(wc[1] - wc[2])
        # Все отрицательные (WC растёт)
        assert all(d < 0 for d in dwc)

    def test_excel_data_y0_y1_aggregate_match(self):
        """Численная сверка с Excel DATA rows 38-39 для Y0/Y1.

        Не запускаем pipeline — проверяем что наша формула WC + ΔWC
        даст те же числа что и Excel при подаче агрегированной выручки
        проекта GORJI на вход.
        """
        # Excel DATA: NR(Y0)=257429.30, NR(Y1)=38916021.28, wc_rate=0.12
        nr_y0 = 257429.2954260194
        nr_y1 = 38916021.28393693

        # Симулируем 2-период PipelineInput. Net revenue нельзя задать
        # напрямую — это output s02. Поэтому конструируем небольшой
        # синтетический сценарий, где net_revenue[0] и [1] будут равны
        # этим значениям.
        # Простой способ: shelf_reg такой что после VAT/margin = NR / volume.
        # Лень считать — лучше напрямую запатчим контекст.
        inp = make_input(
            period_count=2,
            period_is_monthly=(True, True),
            period_month_num=(1, 2),
            period_model_year=(1, 1),
            nd=(0.5, 0.5),
            offtake=(10.0, 10.0),
            shelf_price_reg=(100.0, 100.0),
            seasonality=(1.0, 1.0),
            wc_rate=0.12,
        )
        ctx = ctx_for(inp)
        # Шорткат: подменяем выходы s01/s02 руками — нам нужно только s07
        ctx.volume_units = [1.0, 1.0]
        ctx.volume_liters = [0.5, 0.5]
        ctx.net_revenue = [nr_y0, nr_y1]
        s07_working_capital.step(ctx)

        # Excel-эталон
        assert ctx.working_capital[0] == pytest.approx(30891.515451122326, rel=1e-9)
        assert ctx.working_capital[1] == pytest.approx(4669922.554072431, rel=1e-9)
        assert ctx.delta_working_capital[0] == pytest.approx(-30891.515451122326, rel=1e-9)
        assert ctx.delta_working_capital[1] == pytest.approx(
            -4639031.038621309, rel=1e-9
        )


# ============================================================
# s08 — Tax (D-03 / ADR-CE-04)
# ============================================================


class TestTax:
    def test_positive_contribution_taxed_negatively(self):
        """tax = −(CM × rate). Знак отрицательный — отток."""
        inp = make_input(tax_rate=0.20)
        ctx = run_through_s05(inp)
        # Принудительно ставим положительный CM для теста
        ctx.contribution = [1000.0]
        s08_tax.step(ctx)
        assert ctx.tax[0] == pytest.approx(-200.0)

    def test_negative_contribution_no_tax_shield(self):
        """При CM < 0 → tax = 0 (а не положительный возврат).

        Excel-модель не учитывает налоговый щит. Это упрощение,
        зафиксировано в ADR-CE-04 (Y1 GORJI: CM=-103998 → tax=0).
        """
        inp = make_input(tax_rate=0.20)
        ctx = run_through_s05(inp)
        ctx.contribution = [-50000.0]
        s08_tax.step(ctx)
        assert ctx.tax[0] == 0.0

    def test_zero_contribution_zero_tax(self):
        inp = make_input(tax_rate=0.20)
        ctx = run_through_s05(inp)
        ctx.contribution = [0.0]
        s08_tax.step(ctx)
        assert ctx.tax[0] == 0.0

    def test_excel_data_y0_y1_match(self):
        """Excel DATA row 40: tax(Y0)=-21630.27, tax(Y1)=0."""
        cm_y0 = 108151.34599619916
        cm_y1 = -103998.54263893934

        inp = make_input(
            period_count=2,
            period_is_monthly=(True, True),
            period_month_num=(1, 2),
            period_model_year=(1, 1),
            nd=(0.5, 0.5),
            offtake=(10.0, 10.0),
            shelf_price_reg=(100.0, 100.0),
            seasonality=(1.0, 1.0),
            tax_rate=0.20,
        )
        ctx = ctx_for(inp)
        ctx.contribution = [cm_y0, cm_y1]
        s08_tax.step(ctx)

        assert ctx.tax[0] == pytest.approx(-21630.269199239832, rel=1e-9)
        assert ctx.tax[1] == 0.0


# ============================================================
# s09 — Cash Flow (OCF, ICF, FCF)
# ============================================================


class TestCashFlow:
    def test_ocf_combines_cm_dwc_tax(self):
        inp = make_input(
            wc_rate=0.12,
            tax_rate=0.20,
        )
        ctx = run_through_s05(inp)
        s07_working_capital.step(ctx)
        s08_tax.step(ctx)
        s09_cash_flow.step(ctx)

        expected_ocf = (
            ctx.contribution[0]
            + ctx.delta_working_capital[0]
            + ctx.tax[0]
        )
        assert ctx.operating_cash_flow[0] == pytest.approx(expected_ocf)

    def test_icf_is_negative_capex(self):
        inp = make_input(capex=(1000.0,))
        ctx = run_through_s05(inp)
        s07_working_capital.step(ctx)
        s08_tax.step(ctx)
        s09_cash_flow.step(ctx)

        assert ctx.investing_cash_flow[0] == pytest.approx(-1000.0)

    def test_empty_capex_means_zero_icf(self):
        inp = make_input(capex=())
        ctx = run_through_s05(inp)
        s07_working_capital.step(ctx)
        s08_tax.step(ctx)
        s09_cash_flow.step(ctx)

        assert ctx.investing_cash_flow[0] == 0.0

    def test_fcf_equals_ocf_plus_icf(self):
        inp = make_input(capex=(500.0,))
        ctx = run_through_s05(inp)
        s07_working_capital.step(ctx)
        s08_tax.step(ctx)
        s09_cash_flow.step(ctx)

        expected_fcf = ctx.operating_cash_flow[0] + ctx.investing_cash_flow[0]
        assert ctx.free_cash_flow[0] == pytest.approx(expected_fcf)

    def test_excel_data_y0_y1_aggregate(self):
        """Полная сверка цепочки s07-s08-s09 с Excel DATA rows 41-43.

        GORJI Y0/Y1 агрегаты — наш per-line pipeline даёт те же числа
        при подаче агрегированных входов (поскольку формулы линейны).
        """
        nr_y0 = 257429.2954260194
        nr_y1 = 38916021.28393693
        cm_y0 = 108151.34599619916
        cm_y1 = -103998.54263893934
        capex_y0 = 6602348
        capex_y1 = 5440000

        inp = make_input(
            period_count=2,
            period_is_monthly=(True, True),
            period_month_num=(1, 2),
            period_model_year=(1, 1),
            nd=(0.5, 0.5),
            offtake=(10.0, 10.0),
            shelf_price_reg=(100.0, 100.0),
            seasonality=(1.0, 1.0),
            wc_rate=0.12,
            tax_rate=0.20,
            capex=(float(capex_y0), float(capex_y1)),
        )
        ctx = ctx_for(inp)
        # Подменяем NR и CM напрямую (агрегаты GORJI)
        ctx.volume_units = [1.0, 1.0]
        ctx.volume_liters = [0.5, 0.5]
        ctx.net_revenue = [nr_y0, nr_y1]
        ctx.contribution = [cm_y0, cm_y1]

        s07_working_capital.step(ctx)
        s08_tax.step(ctx)
        s09_cash_flow.step(ctx)

        # Эталоны Excel DATA rows 41-43
        assert ctx.operating_cash_flow[0] == pytest.approx(55629.561345837006, rel=1e-9)
        assert ctx.operating_cash_flow[1] == pytest.approx(-4743029.581260249, rel=1e-9)
        assert ctx.investing_cash_flow[0] == pytest.approx(-6602348.0)
        assert ctx.investing_cash_flow[1] == pytest.approx(-5440000.0)
        assert ctx.free_cash_flow[0] == pytest.approx(-6546718.438654163, rel=1e-9)
        assert ctx.free_cash_flow[1] == pytest.approx(-10183029.581260249, rel=1e-9)


# ============================================================
# Smoke: цепочка s01..s09 на многопериодном кейсе
# ============================================================


class TestPipelineSmoke6_9:
    def test_full_run_3_periods(self):
        inp = make_input(
            period_count=3,
            period_is_monthly=(True, True, True),
            period_month_num=(1, 2, 3),
            period_model_year=(1, 1, 1),
            nd=(0.2, 0.5, 0.8),
            offtake=(10.0, 10.0, 10.0),
            shelf_price_reg=(100.0, 100.0, 100.0),
            seasonality=(1.0, 1.0, 1.0),
            bom_unit_cost=5.0,
            production_cost_rate=0.10,
            logistics_cost_per_kg=4.0,
            sku_volume_l=0.5,
            ca_m_rate=0.10,
            marketing_rate=0.05,
            wc_rate=0.12,
            tax_rate=0.20,
            capex=(1000.0, 0.0, 0.0),
        )
        ctx = ctx_for(inp)
        s01_volume.step(ctx)
        s02_price.step(ctx)
        s03_cogs.step(ctx)
        s04_gross_profit.step(ctx)
        s05_contribution.step(ctx)
        s06_ebitda.step(ctx)
        s07_working_capital.step(ctx)
        s08_tax.step(ctx)
        s09_cash_flow.step(ctx)

        # Все массивы заполнены и корректной длины
        for arr in [
            ctx.ebitda,
            ctx.working_capital,
            ctx.delta_working_capital,
            ctx.tax,
            ctx.operating_cash_flow,
            ctx.investing_cash_flow,
            ctx.free_cash_flow,
        ]:
            assert len(arr) == 3

        # ΔWC[0] = −WC[0]
        assert ctx.delta_working_capital[0] == pytest.approx(-ctx.working_capital[0])
        # ICF[0] = −1000 (capex), ICF[1]=ICF[2]=0
        assert ctx.investing_cash_flow == [-1000.0, 0.0, 0.0]
        # FCF = OCF + ICF на каждом периоде
        for t in range(3):
            assert ctx.free_cash_flow[t] == pytest.approx(
                ctx.operating_cash_flow[t] + ctx.investing_cash_flow[t]
            )
