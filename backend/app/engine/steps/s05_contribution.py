"""Шаг 5 — Contribution.

Формула (Excel: DATA row 26, см. D-05 + D-09):
    LOGISTICS_COST[t] = LOGISTICS_COST_PER_KG
                        × VOLUME_LITERS[t]
                        × PRODUCT_DENSITY
    CONTRIBUTION[t]   = GROSS_PROFIT[t] − LOGISTICS_COST[t] − PROJECT_OPEX[t]

Примечания:
- D-09: логистика в Excel в ₽/кг, мы храним так же.
  `LOGISTICS_COST = ₽/кг × литры × плотность`. Для напитков плотность ≈ 1.0,
  при расчёте воды логистика ≈ ₽/литр × литры.
- PROJECT_OPEX — дискретные периодические затраты проекта (Excel DATA row 26).
  В MVP источник данных ещё не реализован: если `input.project_opex`
  пустой (dataclass default), трактуем как нули.
- Это **Contribution** в терминологии Excel, не GP. Отличие от ТЗ
  зафиксировано в D-05 и закрыто в пользу Excel.
"""
from app.engine.context import PipelineContext


def step(ctx: PipelineContext) -> PipelineContext:
    inp = ctx.input
    n = inp.period_count

    if not ctx.gross_profit or not ctx.volume_liters:
        raise RuntimeError(
            "s05_contribution requires gross_profit (s04) and volume_liters (s01)"
        )

    logistics: list[float] = [0.0] * n
    contribution: list[float] = [0.0] * n

    density = inp.product_density
    # project_opex может быть пустым (≈ нули по всему горизонту).
    opex = inp.project_opex if inp.project_opex else (0.0,) * n
    # C #14: per-period override logistics. Если массив непустой —
    # используем его (calculation_service строит tuple с override-on-top
    # of-PeriodValue-on-top-of-scalar). Пусто (unit-тесты) → fallback
    # на legacy поле logistics_cost_per_kg (per-period tuple).
    log_arr = inp.logistics_cost_per_kg_arr or inp.logistics_cost_per_kg

    for t in range(n):
        kg = ctx.volume_liters[t] * density
        # D-18: per-period logistics_cost_per_kg (Excel DASH row 40 имеет
        # custom Apr/Oct +N% inflation). C #14: log_arr может содержать
        # override JSON (длина n) или legacy per-period tuple.
        l_cost = log_arr[t] * kg
        logistics[t] = l_cost
        contribution[t] = ctx.gross_profit[t] - l_cost - opex[t]

    ctx.logistics_cost = logistics
    ctx.contribution = contribution
    return ctx
