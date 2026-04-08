"""Acceptance-тест: pipeline steps 1-5 ↔ GORJI+ Excel эталон.

Эталонные значения извлечены вручную из `PASSPORT_MODEL_GORJI_2025-09-05.xlsx`,
лист DASH, блок SKU_1 (Gorji Цитрус Газ Пэт 0,5 × канал HM), первые 6
месяцев (M1-M6 = колонки D-I, Jan-Jun 2024). Все числа — сырые float'ы
из openpyxl, без потери точности.

Команда извлечения (одноразово, не в CI):
    docker cp PASSPORT_MODEL_GORJI_2025-09-05.xlsx \\
        dbpassport-dev-backend-1:/tmp/gorji.xlsx
    docker compose exec backend pip install openpyxl
    docker compose exec backend python -c "
        from openpyxl import load_workbook
        wb = load_workbook('/tmp/gorji.xlsx', data_only=True)
        ws = wb['DASH']
        # rows: 22 active_outlets, 10 seasonality, 25 nd, 26 offtake,
        #       30 shelf_reg, 36 material, 37 package, 38 prod_rate,
        #       39 copacker, 40 logistic_kg, 44 gp_per_unit, 46 cm_per_unit
        # static: row 20 col C = volume_l, row 22 col C = vat_rate,
        #         row 27/28/29 col D = channel_margin/promo_discount/promo_share
        # cols D..I = M1..M6"

Этот тест — финальный критерий готовности задачи 2.1 из IMPLEMENTATION_PLAN.md.
Pipeline должен воспроизвести per-unit значения GP и CM из DASH с точностью
лучше 0.01% (relative tolerance).
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
)


# ============================================================
# Эталонные значения из DASH SKU_1 × HM, M1..M6
# ============================================================

# Статические параметры (col C или первый col D из блока)
GORJI_VOLUME_L = 0.5
GORJI_VAT_RATE = 0.2
GORJI_CHANNEL_MARGIN = 0.4
GORJI_PROMO_DISCOUNT = 0.3
GORJI_PROMO_SHARE = 1.0
GORJI_UNIVERSE_HM = 822  # из seed_reference_data.py, совпадает с 31.5648/0.0384

# Helper-формулы: material[t] + package[t] = bom_unit_cost[t] (lumped)
# Inflation profile "Апрель/Октябрь +7%" применён к M4+ (material/package/logistic).
# Shelf price в M1-M6 константа 74.99 — shelf-инфляция в Y1 не применена в Excel.

GORJI_ACTIVE_OUTLETS = [
    31.5648,
    34.43432727272728,
    37.303854545454556,
    40.173381818181824,
    43.0429090909091,
    45.912436363636374,
]
GORJI_SEASONALITY = [
    0.8760100745109026,
    0.79676991071966,
    0.9281733472906769,
    0.9929403563860619,
    1.1370689774678082,
    1.239147448068164,
]
GORJI_ND = [
    0.038400000000000004,
    0.0418909090909091,
    0.04538181818181819,
    0.04887272727272728,
    0.052363636363636376,
    0.05585454545454547,
]
GORJI_OFFTAKE = [
    4.2,
    4.581818181818182,
    4.963636363636364,
    5.345454545454546,
    5.7272727272727275,
    6.109090909090909,
]
GORJI_SHELF_REG = [74.99] * 6
GORJI_MATERIAL = [
    3.6994151040000007,
    3.6994151040000007,
    3.6994151040000007,
    3.958374161280001,   # +7% Apr inflation
    3.958374161280001,
    3.958374161280001,
]
GORJI_PACKAGE = [
    6.076794681818181,
    6.076794681818181,
    6.076794681818181,
    6.502170309545454,   # +7% Apr inflation
    6.502170309545454,
    6.502170309545454,
]
# production cost rate — константа в SKU_1, не меняется с инфляцией
GORJI_PROD_RATE = 0.07776279508668613
GORJI_LOGISTIC_KG = [
    8.0,
    8.0,
    8.0,
    8.56,   # +7% Apr inflation
    8.56,
    8.56,
]

# Project-level rates (Excel DASH SKU_1 rows 41/42)
GORJI_CA_M_RATE = 0.16131139706953254
GORJI_MARKETING_RATE = 0.020322841010825807
# Project-level financial parameters (defaults в Project model)
GORJI_WC_RATE = 0.12
GORJI_TAX_RATE = 0.20

# Ожидаемый EBITDA per unit (DASH row 48 col D-I)
EXPECTED_EBITDA_PER_UNIT = [
    5.662025983162983,   # M1
    5.662025983162983,   # M2
    5.662025983162983,   # M3
    4.69769129815571,    # M4 (после апрельской инфляции)
    4.69769129815571,    # M5
    4.69769129815571,    # M6
]

# Ожидаемые per-unit результаты (DASH rows 44 и 46):
EXPECTED_GP_PER_UNIT = [
    14.429289012939108,
    14.429289012939108,
    14.429289012939108,
    13.744954327931834,
    13.744954327931834,
    13.744954327931834,
]
EXPECTED_CM_PER_UNIT = [
    10.429289012939108,
    10.429289012939108,
    10.429289012939108,
    9.464954327931835,
    9.464954327931835,
    9.464954327931835,
]

# Промежуточные эталоны для более точной диагностики если что-то сломается:
# shipping_w = 52.493 (shelf_w / (1+vat) × (1−margin) = 52.493/1.2×0.6 = 26.2465)
EXPECTED_SHELF_W = 52.492999999999995          # из DASH row 32 col D
EXPECTED_SHIPPING_W = 26.246499999999997       # из DASH row 35 col D


# Допуск 0.01% (1e-4) из IMPLEMENTATION_PLAN.md, но фактически
# мы ожидаем совпадение до ~10 значащих цифр — float-арифметика
# с идентичными входами должна совпадать с Excel.
REL_TOL = 1e-4
ABS_TOL = 1e-9


def _build_gorji_input() -> PipelineInput:
    """Один SKU × один канал × 6 периодов с эталонными inputs."""
    n = 6
    # bom_unit_cost = material + package, но он меняется по периодам
    # (инфляция M4). Текущая модель PipelineInput хранит bom_unit_cost
    # как один float (константа). Для этого теста возьмём средний случай:
    # проверим отдельно M1-M3 (без инфляции) и M4-M6 (после инфляции)
    # двумя запусками.
    raise NotImplementedError("См. _build_input_for_range ниже")


def _build_input_for_range(
    start: int,
    end: int,
) -> tuple[PipelineInput, list[float], list[float]]:
    """Строит PipelineInput для периодов [start, end) — где bom_unit_cost
    и logistics_per_kg постоянны.

    Returns: (input, expected_gp_per_unit, expected_cm_per_unit)
    """
    # Внутри M1-M3 все статические значения одинаковы; в M4-M6 — тоже.
    # Берём первое значение из диапазона как константу для всего диапазона.
    bom_unit_cost = GORJI_MATERIAL[start] + GORJI_PACKAGE[start]
    logistic_kg = GORJI_LOGISTIC_KG[start]
    n = end - start

    inp = PipelineInput(
        project_sku_channel_id=1,
        scenario_id=1,
        period_count=n,
        period_is_monthly=tuple([True] * n),
        period_month_num=tuple(range(start + 1, end + 1)),
        period_model_year=tuple([1] * n),
        nd=tuple(GORJI_ND[start:end]),
        offtake=tuple(GORJI_OFFTAKE[start:end]),
        shelf_price_reg=tuple(GORJI_SHELF_REG[start:end]),
        seasonality=tuple(GORJI_SEASONALITY[start:end]),
        universe_outlets=GORJI_UNIVERSE_HM,
        channel_margin=GORJI_CHANNEL_MARGIN,
        promo_discount=GORJI_PROMO_DISCOUNT,
        promo_share=GORJI_PROMO_SHARE,
        vat_rate=GORJI_VAT_RATE,
        bom_unit_cost=bom_unit_cost,
        production_cost_rate=GORJI_PROD_RATE,
        copacking_per_unit=0.0,
        logistics_cost_per_kg=logistic_kg,
        sku_volume_l=GORJI_VOLUME_L,
        ca_m_rate=GORJI_CA_M_RATE,
        marketing_rate=GORJI_MARKETING_RATE,
        wc_rate=GORJI_WC_RATE,
        tax_rate=GORJI_TAX_RATE,
        product_density=1.0,
        project_opex=tuple([0.0] * n),
    )
    return inp, EXPECTED_GP_PER_UNIT[start:end], EXPECTED_CM_PER_UNIT[start:end]


def _run_pipeline(inp: PipelineInput) -> PipelineContext:
    """Прогон s01..s06 (с EBITDA — для acceptance шага 2.2).

    s07-s09 в этот раннер не включены: WC/Tax/CashFlow на per-line уровне
    в Excel-агрегатах не показаны (Excel DATA содержит только проектный
    агрегат). Численная сверка s07-s09 — отдельным test_steps_6_9.py
    через подстановку агрегатов NR/CM напрямую в контекст.
    """
    ctx = PipelineContext(input=inp)
    s01_volume.step(ctx)
    s02_price.step(ctx)
    s03_cogs.step(ctx)
    s04_gross_profit.step(ctx)
    s05_contribution.step(ctx)
    s06_ebitda.step(ctx)
    return ctx


class TestGorjiReference:
    """Сверка pipeline s01..s05 с эталоном GORJI+ SKU_1/HM."""

    def test_active_outlets_matches_dash_row_22(self):
        """active_outlets[t] = universe × nd[t] — совпадает с DASH row 22."""
        inp, _, _ = _build_input_for_range(0, 6)
        ctx = _run_pipeline(inp)
        for t, expected in enumerate(GORJI_ACTIVE_OUTLETS):
            assert ctx.active_outlets[t] == pytest.approx(expected, rel=REL_TOL, abs=ABS_TOL)

    def test_price_waterfall_matches_dash_rows_30_35(self):
        """Shelf promo/weighted + ex_factory — совпадают с DASH row 31, 32, 35."""
        inp, _, _ = _build_input_for_range(0, 1)
        ctx = _run_pipeline(inp)

        # row 31 col D
        assert ctx.shelf_price_promo[0] == pytest.approx(52.492999999999995, rel=REL_TOL)
        # row 32 col D
        assert ctx.shelf_price_weighted[0] == pytest.approx(EXPECTED_SHELF_W, rel=REL_TOL)
        # row 35 col D
        assert ctx.ex_factory_price[0] == pytest.approx(EXPECTED_SHIPPING_W, rel=REL_TOL)

    def test_gross_profit_per_unit_m1_m3(self):
        """GP/unit в M1-M3 до апрельской инфляции: 14.42929 ₽/unit."""
        inp, exp_gp, _ = _build_input_for_range(0, 3)
        ctx = _run_pipeline(inp)

        for t in range(3):
            gp_per_unit = ctx.gross_profit[t] / ctx.volume_units[t]
            assert gp_per_unit == pytest.approx(
                exp_gp[t], rel=REL_TOL, abs=ABS_TOL
            ), (
                f"M{t + 1}: pipeline gp/unit={gp_per_unit}, "
                f"expected={exp_gp[t]} (DASH row 44 col {chr(68 + t)})"
            )

    def test_gross_profit_per_unit_m4_m6(self):
        """GP/unit в M4-M6 после апрельской инфляции: 13.74495 ₽/unit."""
        inp, exp_gp, _ = _build_input_for_range(3, 6)
        ctx = _run_pipeline(inp)

        for i in range(3):
            gp_per_unit = ctx.gross_profit[i] / ctx.volume_units[i]
            assert gp_per_unit == pytest.approx(
                exp_gp[i], rel=REL_TOL, abs=ABS_TOL
            ), (
                f"M{i + 4}: pipeline gp/unit={gp_per_unit}, "
                f"expected={exp_gp[i]}"
            )

    def test_contribution_per_unit_m1_m3(self):
        """CM/unit в M1-M3: 10.42929 ₽/unit (GP − 4 логистики на unit)."""
        inp, _, exp_cm = _build_input_for_range(0, 3)
        ctx = _run_pipeline(inp)

        for t in range(3):
            cm_per_unit = ctx.contribution[t] / ctx.volume_units[t]
            assert cm_per_unit == pytest.approx(
                exp_cm[t], rel=REL_TOL, abs=ABS_TOL
            )

    def test_contribution_per_unit_m4_m6(self):
        """CM/unit в M4-M6: 9.46495 ₽/unit (GP падает + logistics растёт)."""
        inp, _, exp_cm = _build_input_for_range(3, 6)
        ctx = _run_pipeline(inp)

        for i in range(3):
            cm_per_unit = ctx.contribution[i] / ctx.volume_units[i]
            assert cm_per_unit == pytest.approx(
                exp_cm[i], rel=REL_TOL, abs=ABS_TOL
            )

    def test_ebitda_per_unit_m1_m3(self):
        """EBITDA/unit в M1-M3: 5.66203 ₽/unit (DASH row 48 col D-F).

        Формула: EBITDA = CM − NR×CA_M_RATE − NR×MARKETING_RATE
        Per unit: 10.4293 − 26.2465×0.16131 − 26.2465×0.02032 = 5.6620
        """
        inp, _, _ = _build_input_for_range(0, 3)
        ctx = _run_pipeline(inp)

        for t in range(3):
            ebitda_per_unit = ctx.ebitda[t] / ctx.volume_units[t]
            assert ebitda_per_unit == pytest.approx(
                EXPECTED_EBITDA_PER_UNIT[t], rel=REL_TOL, abs=ABS_TOL
            ), (
                f"M{t + 1}: pipeline ebitda/unit={ebitda_per_unit}, "
                f"expected={EXPECTED_EBITDA_PER_UNIT[t]}"
            )

    def test_ebitda_per_unit_m4_m6(self):
        """EBITDA/unit в M4-M6: 4.69769 ₽/unit (после апрельской инфляции).

        GP падает с 14.43 до 13.74, logistics растёт с 4.0 до 4.28,
        CA&M/Marketing rates фиксированные → EBITDA падает с 5.66 до 4.70.
        """
        inp, _, _ = _build_input_for_range(3, 6)
        ctx = _run_pipeline(inp)

        for i in range(3):
            ebitda_per_unit = ctx.ebitda[i] / ctx.volume_units[i]
            assert ebitda_per_unit == pytest.approx(
                EXPECTED_EBITDA_PER_UNIT[i + 3], rel=REL_TOL, abs=ABS_TOL
            )

    def test_inflation_jump_m3_to_m4(self):
        """Проверяем что Excel-эталон действительно скачет в M4 (а не совпадает).

        Защита от случая когда тест "пройдёт" из-за того что эталон одинаков
        по всем периодам. Мы хотим убедиться что inflation-профиль
        действительно транслируется в разные per-unit значения.
        """
        # M1-M3: GP/unit = 14.429
        # M4-M6: GP/unit = 13.745
        assert EXPECTED_GP_PER_UNIT[2] != EXPECTED_GP_PER_UNIT[3]
        assert abs(EXPECTED_GP_PER_UNIT[2] - EXPECTED_GP_PER_UNIT[3]) > 0.1
        # Materials выросли на 7%
        assert GORJI_MATERIAL[3] / GORJI_MATERIAL[0] == pytest.approx(1.07, rel=1e-3)
        assert GORJI_PACKAGE[3] / GORJI_PACKAGE[0] == pytest.approx(1.07, rel=1e-3)
        assert GORJI_LOGISTIC_KG[3] / GORJI_LOGISTIC_KG[0] == pytest.approx(1.07, rel=1e-3)
