"""Unit-тесты pipeline orchestrator (engine/pipeline.py).

run_line_pipeline: s01..s09 для одной линии — должна заполнять все
поля включая FCF.

run_project_pipeline: per-line + aggregate + s10..s12 — должна выдавать
готовые KPI словари по 3 скоупам.
"""
from __future__ import annotations

import pytest

from app.engine.pipeline import run_line_pipeline, run_project_pipeline
from tests.engine.test_steps_1_5 import make_input


class TestRunLine:
    def test_single_period_line(self):
        inp = make_input()
        ctx = run_line_pipeline(inp)
        # Все поля до s09 заполнены
        assert ctx.volume_units
        assert ctx.net_revenue
        assert ctx.contribution
        assert ctx.ebitda
        assert ctx.working_capital
        assert ctx.tax
        assert ctx.operating_cash_flow
        assert ctx.investing_cash_flow
        assert ctx.free_cash_flow
        # s10..s12 НЕ запускались на per-line
        assert not ctx.annual_free_cash_flow
        assert not ctx.npv

    def test_multi_period_line(self):
        inp = make_input(
            period_count=12,
            period_is_monthly=tuple([True] * 12),
            period_month_num=tuple(range(1, 13)),
            period_model_year=tuple([1] * 12),
            nd=tuple([0.5] * 12),
            offtake=tuple([10.0] * 12),
            shelf_price_reg=tuple([100.0] * 12),
            seasonality=tuple([1.0] * 12),
            ca_m_rate=0.10,
            marketing_rate=0.05,
        )
        ctx = run_line_pipeline(inp)
        assert len(ctx.free_cash_flow) == 12
        # ΔWC[0] = -WC[0] (граничный случай)
        assert ctx.delta_working_capital[0] == pytest.approx(-ctx.working_capital[0])


class TestRunProject:
    def test_empty_inputs_raises(self):
        with pytest.raises(ValueError, match="at least one"):
            run_project_pipeline([])

    def test_single_line_project(self):
        """Один SKU × один канал → KPI считаются."""
        inp = make_input(
            period_count=12,
            period_is_monthly=tuple([True] * 12),
            period_month_num=tuple(range(1, 13)),
            period_model_year=tuple([1] * 12),  # все 12 месяцев = year 1
            nd=tuple([0.5] * 12),
            offtake=tuple([10.0] * 12),
            shelf_price_reg=tuple([100.0] * 12),
            seasonality=tuple([1.0] * 12),
            ca_m_rate=0.10,
            marketing_rate=0.05,
        )
        agg = run_project_pipeline([inp])

        # KPI словари по 3 скоупам заполнены
        assert "y1y3" in agg.npv
        assert "y1y5" in agg.npv
        assert "y1y10" in agg.npv
        assert "y1y3" in agg.go_no_go
        # Аннуализация: 12 месяцев → 1 годовой бакет
        assert len(agg.annual_free_cash_flow) == 1

    def test_two_lines_aggregated(self):
        """Два SKU → агрегат удваивает выручку и FCF."""
        inp = make_input(
            period_count=12,
            period_is_monthly=tuple([True] * 12),
            period_month_num=tuple(range(1, 13)),
            period_model_year=tuple([1] * 12),
            nd=tuple([0.5] * 12),
            offtake=tuple([10.0] * 12),
            shelf_price_reg=tuple([100.0] * 12),
            seasonality=tuple([1.0] * 12),
            ca_m_rate=0.10,
            marketing_rate=0.05,
        )
        agg_one = run_project_pipeline([inp])
        agg_two = run_project_pipeline([inp, inp])

        # Annual FCF удвоился
        assert agg_two.annual_free_cash_flow[0] == pytest.approx(
            2 * agg_one.annual_free_cash_flow[0]
        )
        # CM ratio одинаковая (отношение, не зависит от масштаба)
        assert agg_two.contribution_margin_ratio == pytest.approx(
            agg_one.contribution_margin_ratio
        )

    def test_project_capex_reduces_fcf(self):
        """project_capex применяется на уровне агрегата."""
        # 10-периодный случай чтобы вышло на годовой горизонт
        inp = make_input(
            period_count=10,
            period_is_monthly=tuple([False] * 10),
            period_month_num=tuple([None] * 10),
            period_model_year=tuple(range(1, 11)),
            nd=tuple([0.5] * 10),
            offtake=tuple([10.0] * 10),
            shelf_price_reg=tuple([100.0] * 10),
            seasonality=tuple([1.0] * 10),
        )
        no_capex = run_project_pipeline([inp])
        with_capex = run_project_pipeline(
            [inp],
            project_capex=tuple([1000.0] * 10),
        )

        # FCF уменьшен на capex
        for t in range(10):
            assert with_capex.free_cash_flow[t] == pytest.approx(
                no_capex.free_cash_flow[t] - 1000.0
            )
        # NPV with capex меньше
        assert with_capex.npv["y1y10"] < no_capex.npv["y1y10"]
