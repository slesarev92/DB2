"""Шаг 3 — COGS (Cost of Goods Sold).

Формула (Excel: DASH row 38 + DATA row 23, см. также D-04):
    COGS_MATERIAL[t]   = BOM_UNIT_COST × VOLUME_UNITS[t]
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

    bom_unit = inp.bom_unit_cost
    rate = inp.production_cost_rate
    copack_unit = inp.copacking_per_unit

    for t in range(n):
        vol = ctx.volume_units[t]
        m = bom_unit * vol
        p = ctx.ex_factory_price[t] * rate * vol
        c = copack_unit * vol

        material[t] = m
        production[t] = p
        copacking[t] = c
        total[t] = m + p + c

    ctx.cogs_material = material
    ctx.cogs_production = production
    ctx.cogs_copacking = copacking
    ctx.cogs_total = total
    return ctx
