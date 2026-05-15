"""Шаг 3 — COGS (Cost of Goods Sold).

Формула (Excel: DASH row 38 + DATA row 23, см. также D-04):
    COGS_MATERIAL[t]   = BOM_UNIT_COST[t] × VOLUME_UNITS[t]
    COGS_PRODUCTION[t] = EX_FACTORY_PRICE[t] × PRODUCTION_COST_RATE × VOLUME_UNITS[t]
    COGS_COPACKING[t]  = COPACKING_PER_UNIT × VOLUME_UNITS[t]
    COGS_TOTAL[t]      = MATERIAL + PRODUCTION + COPACKING

Примечания:
- D-04: production_cost_rate задаётся как **% от ex_factory price** (не ₽/шт).
  Это гарантирует, что производственная себестоимость растёт с инфляцией
  пропорционально цене, как в Excel-модели.
- COGS **не** включает логистику. В Excel логистика вычитается на уровне
  Contribution (s05), не на уровне GP (s04). Это отличие от плановой
  формулировки s04 — исправлено в пользу Excel семантики (ADR-CE-01).
- BOM в текущей модели лампованный — `bom_unit_cost` это Σ по всем
  BOMItem (material+package вместе). Copacking в MVP всегда 0
  (нет поля в схеме, согласовано с пользователем).
- `bom_unit_cost` — **per-period tuple**, а не константа: Excel применяет
  инфляционный профиль (Апрель/Октябрь +N%) к материалам и упаковке
  по тем же правилам что и к shelf_price. См. `predict_service.inflate_series`
  и `calculation_service._build_line_input` для генерации ряда.
"""
from app.engine.context import PipelineContext


def step(ctx: PipelineContext) -> PipelineContext:
    inp = ctx.input
    n = inp.period_count

    if not ctx.volume_units or not ctx.ex_factory_price:
        raise RuntimeError(
            "s03_cogs requires volume_units (s01) and ex_factory_price (s02)"
        )

    material: list[float] = [0.0] * n
    production: list[float] = [0.0] * n
    copacking: list[float] = [0.0] * n
    total: list[float] = [0.0] * n

    # Q1 (2026-05-15): production_mode per-period. Длина по контракту = n;
    # calculation_service строит tuple длины period_count из годового
    # override + fallback на ProjectSKU.production_mode.
    mode_by_period = inp.production_mode_by_period
    if len(mode_by_period) != n:
        raise RuntimeError(
            f"production_mode_by_period length mismatch: got {len(mode_by_period)}, "
            f"expected {n}"
        )
    copack_unit = inp.copacking_per_unit

    for t in range(n):
        vol = ctx.volume_units[t]
        m = inp.bom_unit_cost[t] * vol
        is_copacking_t = mode_by_period[t] == "copacking"

        if is_copacking_t:
            # Копакинг: production = 0, copacking = rate × volume
            p = 0.0
            c = copack_unit * vol
        else:
            # Собственное производство: copacking = 0, production = ex_factory × rate × vol
            # D-19: per-period production_cost_rate (Excel переключает rate
            # по периодам — copacking window для own production downtime).
            p = ctx.ex_factory_price[t] * inp.production_cost_rate[t] * vol
            c = 0.0

        material[t] = m
        production[t] = p
        copacking[t] = c
        total[t] = m + p + c

    ctx.cogs_material = material
    ctx.cogs_production = production
    ctx.cogs_copacking = copacking
    ctx.cogs_total = total
    return ctx
