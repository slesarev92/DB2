"""Unit + smoke тесты для шагов 1-5 расчётного ядра.

Каждый шаг проверяется изолированно на маленьких синтетических
входных данных с ожидаемыми значениями посчитанными вручную.
Цель — поймать регрессии в формулах при будущих изменениях.

Acceptance-тест против эталонных чисел GORJI+ вынесен в
`test_gorji_reference.py` (чтобы разделить быстрые unit-проверки
и золотой тест).
"""
from __future__ import annotations

import math

import pytest

from app.engine.context import PipelineContext, PipelineInput
from app.engine.steps import (
    s01_volume,
    s02_price,
    s03_cogs,
    s04_gross_profit,
    s05_contribution,
)


def make_input(**overrides) -> PipelineInput:
    """Фабрика минимального валидного PipelineInput для unit-тестов.

    По умолчанию — один период, нейтральные значения, без инфляции,
    без сезонности. Переопределяй нужные поля через kwargs.

    `bom_unit_cost` и `logistics_cost_per_kg` принимают либо float (для
    удобства тестов — будет раскрыт в tuple длины period_count), либо
    tuple напрямую.
    """
    n = overrides.pop("period_count", 1)

    # Удобная конвертация: если bom_unit_cost передан как float, делаем
    # tuple длины n. Если уже tuple — оставляем как есть.
    bom_override = overrides.pop("bom_unit_cost", None)
    if bom_override is None:
        bom_unit_cost: tuple[float, ...] = (10.0,) * n
    elif isinstance(bom_override, (int, float)):
        bom_unit_cost = (float(bom_override),) * n
    else:
        bom_unit_cost = tuple(bom_override)

    # Аналогично для logistics_cost_per_kg (D-18: per-period в pipeline).
    log_override = overrides.pop("logistics_cost_per_kg", None)
    if log_override is None:
        log_per_kg: tuple[float, ...] = (0.0,) * n
    elif isinstance(log_override, (int, float)):
        log_per_kg = (float(log_override),) * n
    else:
        log_per_kg = tuple(log_override)

    # D-20: channel_margin/promo_discount/promo_share per-period.
    def _to_tuple(name: str, default: float) -> tuple[float, ...]:
        v = overrides.pop(name, None)
        if v is None:
            return (default,) * n
        if isinstance(v, (int, float)):
            return (float(v),) * n
        return tuple(v)

    cm_tuple = _to_tuple("channel_margin", 0.30)
    pd_tuple = _to_tuple("promo_discount", 0.0)
    ps_tuple = _to_tuple("promo_share", 0.0)
    prod_rate_tuple = _to_tuple("production_cost_rate", 0.0)

    # Q1: backwards-compat — старые тесты передают production_mode скаляром.
    # Конвертируем в production_mode_by_period если передан string.
    if "production_mode" in overrides:
        mode_value = overrides.pop("production_mode")
        overrides.setdefault(
            "production_mode_by_period", tuple([mode_value] * n)
        )

    defaults: dict = {
        "project_sku_channel_id": 1,
        "scenario_id": 1,
        "period_count": n,
        "period_is_monthly": (True,) * n,
        "period_month_num": (1,) * n,
        "period_model_year": (1,) * n,
        "nd": (0.5,) * n,
        "offtake": (10.0,) * n,
        "shelf_price_reg": (100.0,) * n,
        "seasonality": (1.0,) * n,
        "universe_outlets": 1000,
        "channel_margin": cm_tuple,
        "promo_discount": pd_tuple,
        "promo_share": ps_tuple,
        "vat_rate": 0.20,
        "bom_unit_cost": bom_unit_cost,
        "production_cost_rate": prod_rate_tuple,
        "copacking_per_unit": 0.0,
        # Q1 (2026-05-15): production_mode per-period (default "own").
        # Тесты могут переопределить через overrides production_mode_by_period
        # tuple/list или одно значение для всех периодов.
        "production_mode_by_period": tuple(
            ["own"] * n
        ),
        "logistics_cost_per_kg": log_per_kg,
        "sku_volume_l": 0.5,
        "ca_m_rate": 0.0,
        "marketing_rate": 0.0,
        "wc_rate": 0.12,
        "tax_rate": 0.20,
        "wacc": 0.19,
        "product_density": 1.0,
        "project_opex": (),
        "capex": (),
    }
    defaults.update(overrides)
    return PipelineInput(**defaults)


def ctx_for(inp: PipelineInput) -> PipelineContext:
    return PipelineContext(input=inp)


# ============================================================
# s01 — Volume
# ============================================================


class TestVolume:
    def test_basic(self):
        # universe=1000, nd=0.5 → active=500
        # offtake=10 × seasonality=1 → volume=5000 units
        # sku_volume_l=0.5 → volume_liters=2500
        inp = make_input()
        ctx = s01_volume.step(ctx_for(inp))
        assert ctx.active_outlets == [500.0]
        assert ctx.volume_units == [5000.0]
        assert ctx.volume_liters == [2500.0]

    def test_zero_nd_means_zero_volume(self):
        inp = make_input(nd=(0.0,))
        ctx = s01_volume.step(ctx_for(inp))
        assert ctx.active_outlets == [0.0]
        assert ctx.volume_units == [0.0]

    def test_seasonality_multiplies_monthly_volume(self):
        # Сезонность 1.2 → volume_units умножается на 1.2
        inp = make_input(seasonality=(1.2,))
        ctx = s01_volume.step(ctx_for(inp))
        assert ctx.volume_units == [pytest.approx(6000.0)]

    def test_multi_period(self):
        inp = make_input(
            period_count=3,
            period_is_monthly=(True, True, True),
            period_month_num=(1, 2, 3),
            period_model_year=(1, 1, 1),
            nd=(0.2, 0.5, 0.8),
            offtake=(10.0, 10.0, 10.0),
            shelf_price_reg=(100.0, 100.0, 100.0),
            seasonality=(1.0, 1.0, 1.0),
        )
        ctx = s01_volume.step(ctx_for(inp))
        assert ctx.active_outlets == [200.0, 500.0, 800.0]
        assert ctx.volume_units == [2000.0, 5000.0, 8000.0]


# ============================================================
# s02 — Price waterfall (ADR-CE-03: VAT через /(1+vat), не ×(1-vat))
# ============================================================


class TestPrice:
    def test_adr_ce_03_vat_divide_not_multiply(self):
        """ADR-CE-03: ex_factory(shelf=100, vat=20%, margin=30%) = 58.33, не 56.00.

        100 / 1.20 × 0.70 = 83.333... × 0.70 = 58.333...
        ТЗ-формула 100 × 0.80 × 0.70 = 56.00 — отклонение 4.17%.
        """
        inp = make_input(
            shelf_price_reg=(100.0,),
            vat_rate=0.20,
            channel_margin=0.30,
            promo_discount=0.0,
            promo_share=0.0,
        )
        ctx = ctx_for(inp)
        s01_volume.step(ctx)
        s02_price.step(ctx)

        expected_ex_factory = 100.0 / 1.20 * 0.70
        assert ctx.ex_factory_price[0] == pytest.approx(expected_ex_factory)
        # Явная проверка: не ТЗ-формула
        assert ctx.ex_factory_price[0] != pytest.approx(100.0 * 0.80 * 0.70)

    def test_promo_weighted_price(self):
        # shelf=100, promo_discount=20%, promo_share=25%
        # shelf_promo = 100 × 0.8 = 80
        # weighted = 100 × 0.75 + 80 × 0.25 = 75 + 20 = 95
        inp = make_input(
            shelf_price_reg=(100.0,),
            promo_discount=0.20,
            promo_share=0.25,
        )
        ctx = ctx_for(inp)
        s01_volume.step(ctx)
        s02_price.step(ctx)

        assert ctx.shelf_price_promo[0] == pytest.approx(80.0)
        assert ctx.shelf_price_weighted[0] == pytest.approx(95.0)

    def test_net_revenue_from_volume_and_price(self):
        # volume=5000 units × ex_factory(58.333) = 291 666.67
        inp = make_input(
            shelf_price_reg=(100.0,),
            vat_rate=0.20,
            channel_margin=0.30,
        )
        ctx = ctx_for(inp)
        s01_volume.step(ctx)
        s02_price.step(ctx)

        expected_ex_factory = 100.0 / 1.20 * 0.70
        assert ctx.net_revenue[0] == pytest.approx(5000.0 * expected_ex_factory)

    def test_s02_requires_s01(self):
        inp = make_input()
        ctx = ctx_for(inp)
        # s01 не прогнан → volume_units пустой
        with pytest.raises(RuntimeError, match="s02_price requires volume_units"):
            s02_price.step(ctx)


# ============================================================
# s03 — COGS
# ============================================================


class TestCogs:
    def test_material_only(self):
        # bom_unit_cost=10 × volume=5000 → material=50000
        # production_cost_rate=0, copacking=0 → всё остальное 0
        inp = make_input(
            bom_unit_cost=10.0,
            production_cost_rate=0.0,
            copacking_per_unit=0.0,
        )
        ctx = ctx_for(inp)
        s01_volume.step(ctx)
        s02_price.step(ctx)
        s03_cogs.step(ctx)

        assert ctx.cogs_material[0] == pytest.approx(50000.0)
        assert ctx.cogs_production[0] == 0.0
        assert ctx.cogs_copacking[0] == 0.0
        assert ctx.cogs_total[0] == pytest.approx(50000.0)

    def test_production_rate_applied_to_ex_factory(self):
        """D-04: production_cost_rate — доля от ex_factory_price."""
        # ex_factory = 100/1.2×0.7 = 58.333...
        # production = 58.333 × 0.15 × 5000 = 43750
        inp = make_input(
            bom_unit_cost=0.0,
            production_cost_rate=0.15,
            copacking_per_unit=0.0,
        )
        ctx = ctx_for(inp)
        s01_volume.step(ctx)
        s02_price.step(ctx)
        s03_cogs.step(ctx)

        expected = (100.0 / 1.20 * 0.70) * 0.15 * 5000.0
        assert ctx.cogs_production[0] == pytest.approx(expected)
        assert ctx.cogs_material[0] == 0.0

    def test_own_mode_production_no_copacking(self):
        """production_mode='own': production cost active, copacking=0."""
        inp = make_input(
            bom_unit_cost=5.0,
            production_cost_rate=0.10,
            copacking_per_unit=2.0,  # ignored when mode=own
            production_mode="own",
        )
        ctx = ctx_for(inp)
        s01_volume.step(ctx)
        s02_price.step(ctx)
        s03_cogs.step(ctx)

        mat = 5.0 * 5000.0
        prod = (100.0 / 1.20 * 0.70) * 0.10 * 5000.0
        assert ctx.cogs_material[0] == pytest.approx(mat)
        assert ctx.cogs_production[0] == pytest.approx(prod)
        assert ctx.cogs_copacking[0] == 0.0
        assert ctx.cogs_total[0] == pytest.approx(mat + prod)

    def test_copacking_mode_no_production(self):
        """production_mode='copacking': copacking active, production=0."""
        inp = make_input(
            bom_unit_cost=5.0,
            production_cost_rate=0.10,  # ignored when mode=copacking
            copacking_per_unit=2.0,
            production_mode="copacking",
        )
        ctx = ctx_for(inp)
        s01_volume.step(ctx)
        s02_price.step(ctx)
        s03_cogs.step(ctx)

        mat = 5.0 * 5000.0
        cop = 2.0 * 5000.0
        assert ctx.cogs_material[0] == pytest.approx(mat)
        assert ctx.cogs_production[0] == 0.0
        assert ctx.cogs_copacking[0] == pytest.approx(cop)
        assert ctx.cogs_total[0] == pytest.approx(mat + cop)

    def test_zero_volume_gives_zero_cogs(self):
        inp = make_input(
            nd=(0.0,),
            bom_unit_cost=10.0,
            production_cost_rate=0.15,
        )
        ctx = ctx_for(inp)
        s01_volume.step(ctx)
        s02_price.step(ctx)
        s03_cogs.step(ctx)

        assert ctx.cogs_total[0] == 0.0


# ============================================================
# s04 — Gross Profit (Excel: GP = NR − COGS, без логистики)
# ============================================================


class TestGrossProfit:
    def test_gp_is_nr_minus_cogs(self):
        """Excel DATA row 23: GP = NR − COGS. Логистика тут НЕ вычитается."""
        inp = make_input(
            bom_unit_cost=5.0,
            production_cost_rate=0.0,
            logistics_cost_per_kg=999.0,  # большое значение — должно игнорироваться на этом шаге
        )
        ctx = ctx_for(inp)
        s01_volume.step(ctx)
        s02_price.step(ctx)
        s03_cogs.step(ctx)
        s04_gross_profit.step(ctx)

        nr = ctx.net_revenue[0]
        cogs = ctx.cogs_total[0]
        assert ctx.gross_profit[0] == pytest.approx(nr - cogs)
        # Явно: логистика НЕ повлияла на GP
        expected_without_logistics = nr - cogs
        assert ctx.gross_profit[0] == pytest.approx(expected_without_logistics)


# ============================================================
# s05 — Contribution (GP − Logistics − Project_OPEX)
# ============================================================


class TestContribution:
    def test_contribution_subtracts_logistics_and_opex(self):
        # volume_liters = 5000 × 0.5 = 2500 кг
        # logistics = 4 × 2500 = 10000
        # project_opex = 100 в нулевом периоде
        inp = make_input(
            bom_unit_cost=5.0,
            production_cost_rate=0.0,
            logistics_cost_per_kg=4.0,
            sku_volume_l=0.5,
            project_opex=(100.0,),
        )
        ctx = ctx_for(inp)
        s01_volume.step(ctx)
        s02_price.step(ctx)
        s03_cogs.step(ctx)
        s04_gross_profit.step(ctx)
        s05_contribution.step(ctx)

        assert ctx.logistics_cost[0] == pytest.approx(10000.0)
        expected_cm = ctx.gross_profit[0] - 10000.0 - 100.0
        assert ctx.contribution[0] == pytest.approx(expected_cm)

    def test_empty_project_opex_treated_as_zero(self):
        inp = make_input(
            logistics_cost_per_kg=4.0,
            project_opex=(),  # пусто — должно интерпретироваться как нули
        )
        ctx = ctx_for(inp)
        s01_volume.step(ctx)
        s02_price.step(ctx)
        s03_cogs.step(ctx)
        s04_gross_profit.step(ctx)
        s05_contribution.step(ctx)

        expected = ctx.gross_profit[0] - ctx.logistics_cost[0]  # − 0
        assert ctx.contribution[0] == pytest.approx(expected)

    def test_zero_density_means_zero_logistics(self):
        inp = make_input(
            logistics_cost_per_kg=4.0,
            sku_volume_l=0.5,
            product_density=0.0,
        )
        ctx = ctx_for(inp)
        s01_volume.step(ctx)
        s02_price.step(ctx)
        s03_cogs.step(ctx)
        s04_gross_profit.step(ctx)
        s05_contribution.step(ctx)

        assert ctx.logistics_cost[0] == 0.0
        assert ctx.contribution[0] == pytest.approx(ctx.gross_profit[0])


# ============================================================
# Smoke: весь pipeline 1..5 на многопериодном кейсе
# ============================================================


class TestPipelineSmoke:
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
            project_opex=(0.0, 0.0, 0.0),
        )
        ctx = ctx_for(inp)
        s01_volume.step(ctx)
        s02_price.step(ctx)
        s03_cogs.step(ctx)
        s04_gross_profit.step(ctx)
        s05_contribution.step(ctx)

        # Все массивы заполнены и корректной длины
        assert len(ctx.volume_units) == 3
        assert len(ctx.net_revenue) == 3
        assert len(ctx.cogs_total) == 3
        assert len(ctx.gross_profit) == 3
        assert len(ctx.contribution) == 3

        # Монотонный рост volume (nd растёт)
        assert ctx.volume_units[0] < ctx.volume_units[1] < ctx.volume_units[2]
        # GP = NR − COGS на каждом периоде
        for t in range(3):
            assert ctx.gross_profit[t] == pytest.approx(
                ctx.net_revenue[t] - ctx.cogs_total[t]
            )
        # CM = GP − Logistics − Opex (Opex=0)
        for t in range(3):
            assert ctx.contribution[t] == pytest.approx(
                ctx.gross_profit[t] - ctx.logistics_cost[t]
            )

    def test_input_length_validation(self):
        with pytest.raises(ValueError, match="nd has length"):
            PipelineInput(
                project_sku_channel_id=1,
                scenario_id=1,
                period_count=3,
                period_is_monthly=(True, True, True),
                period_month_num=(1, 2, 3),
                period_model_year=(1, 1, 1),
                nd=(0.5, 0.5),  # длина 2, ожидается 3 — ValueError
                offtake=(10.0, 10.0, 10.0),
                shelf_price_reg=(100.0, 100.0, 100.0),
                seasonality=(1.0, 1.0, 1.0),
                universe_outlets=1000,
                channel_margin=(0.30, 0.30, 0.30),
                promo_discount=(0.0, 0.0, 0.0),
                promo_share=(0.0, 0.0, 0.0),
                vat_rate=0.20,
                bom_unit_cost=(10.0, 10.0, 10.0),
                production_cost_rate=(0.0, 0.0, 0.0),
                copacking_per_unit=0.0,
                logistics_cost_per_kg=(0.0, 0.0, 0.0),
                sku_volume_l=0.5,
                ca_m_rate=0.0,
                marketing_rate=0.0,
                wc_rate=0.12,
                tax_rate=0.20,
                wacc=0.19,
            )
