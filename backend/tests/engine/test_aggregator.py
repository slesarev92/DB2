"""Unit-тесты aggregator (engine/aggregator.py).

Aggregator складывает per-line per-period значения в проектный агрегат.
Все формулы линейны, поэтому тесты — простые проверки element-wise sum.
"""
from __future__ import annotations

import pytest

from app.engine.aggregator import aggregate_lines
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


def _run_through_s09(inp: PipelineInput) -> PipelineContext:
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
    return ctx


class TestAggregator:
    def test_empty_list_raises(self):
        with pytest.raises(ValueError, match="at least one"):
            aggregate_lines([])

    def test_single_line_passthrough(self):
        """Один контекст → агрегат с теми же значениями."""
        inp = make_input()
        ctx = _run_through_s09(inp)
        agg = aggregate_lines([ctx])

        assert agg.volume_units == ctx.volume_units
        assert agg.net_revenue == ctx.net_revenue
        assert agg.contribution == ctx.contribution
        assert agg.free_cash_flow == ctx.free_cash_flow

    def test_two_identical_lines_doubles_values(self):
        """Две одинаковые линии → агрегат вдвое больше."""
        inp = make_input(
            ca_m_rate=0.10,
            marketing_rate=0.05,
        )
        ctx1 = _run_through_s09(inp)
        ctx2 = _run_through_s09(inp)
        agg = aggregate_lines([ctx1, ctx2])

        for t in range(len(ctx1.net_revenue)):
            assert agg.net_revenue[t] == pytest.approx(2 * ctx1.net_revenue[t])
            assert agg.contribution[t] == pytest.approx(2 * ctx1.contribution[t])
            assert agg.free_cash_flow[t] == pytest.approx(2 * ctx1.free_cash_flow[t])
            assert agg.cogs_total[t] == pytest.approx(2 * ctx1.cogs_total[t])
            assert agg.ebitda[t] == pytest.approx(2 * ctx1.ebitda[t])

    def test_period_count_mismatch_raises(self):
        """Линии разной длины → ValueError."""
        inp1 = make_input(period_count=1)
        inp2 = make_input(
            period_count=3,
            period_is_monthly=(True, True, True),
            period_month_num=(1, 2, 3),
            period_model_year=(1, 1, 1),
            nd=(0.5, 0.5, 0.5),
            offtake=(10.0, 10.0, 10.0),
            shelf_price_reg=(100.0, 100.0, 100.0),
            seasonality=(1.0, 1.0, 1.0),
        )
        ctx1 = _run_through_s09(inp1)
        ctx2 = _run_through_s09(inp2)
        with pytest.raises(ValueError, match="period_count"):
            aggregate_lines([ctx1, ctx2])

    def test_aggregate_metadata_from_first_line(self):
        """Агрегатный input наследует period_model_year, wacc, etc от первой линии."""
        inp = make_input(wacc=0.15)
        ctx = _run_through_s09(inp)
        agg = aggregate_lines([ctx])

        assert agg.input.wacc == 0.15
        assert agg.input.period_count == 1
        assert agg.input.scenario_id == 1
        assert agg.input.project_sku_channel_id == 0  # 0 = aggregate marker

    def test_project_capex_passed_to_input(self):
        inp = make_input()
        ctx = _run_through_s09(inp)
        agg = aggregate_lines([ctx], project_capex=(1000.0,))
        assert agg.input.capex == (1000.0,)
