"""Шаг 2 — Price waterfall и Net Revenue.

Формулы (Excel: DASH rows 30-35, см. также ADR-CE-03 / D-02):
    SHELF_PRICE_PROMO[t]    = SHELF_PRICE_REG[t] × (1 − PROMO_DISCOUNT)
    SHELF_PRICE_WEIGHTED[t] = SHELF_PRICE_REG[t] × (1 − PROMO_SHARE)
                              + SHELF_PRICE_PROMO[t] × PROMO_SHARE

    # ADR-CE-03 / D-02: VAT-стрипинг через ДЕЛЕНИЕ на (1+VAT), не умножение.
    EX_FACTORY_PRICE[t] = SHELF_PRICE_WEIGHTED[t] / (1 + VAT_RATE)
                          × (1 − CHANNEL_MARGIN)

    NET_REVENUE[t] = VOLUME_UNITS[t] × EX_FACTORY_PRICE[t]

ВНИМАНИЕ: формула ТЗ `× (1 − VAT_RATE)` — **неверна**. Разница для VAT=20%:
× 0.80 vs / 1.20 = × 0.8333 (ошибка −4.17% по ex_factory). См. ADR-CE-03.

Промо-скидка и promo_share — параметры канала, не зависят от периода.
`shelf_price_reg[t]` уже учитывает инфляцию по месяцам (это работа service
при формировании input, см. D-08 + задача 2.5).
"""
from app.engine.context import PipelineContext


def step(ctx: PipelineContext) -> PipelineContext:
    inp = ctx.input
    n = inp.period_count

    if not ctx.volume_units:
        raise RuntimeError(
            "s02_price requires volume_units from s01 — run s01_volume first"
        )

    vat_divisor = 1.0 + inp.vat_rate
    channel_factor = 1.0 - inp.channel_margin
    promo_factor = 1.0 - inp.promo_discount
    promo_share = inp.promo_share
    inv_promo_share = 1.0 - promo_share

    shelf_price_promo: list[float] = [0.0] * n
    shelf_price_weighted: list[float] = [0.0] * n
    ex_factory_price: list[float] = [0.0] * n
    net_revenue: list[float] = [0.0] * n

    for t in range(n):
        reg = inp.shelf_price_reg[t]
        promo = reg * promo_factor
        weighted = reg * inv_promo_share + promo * promo_share
        ex_factory = (weighted / vat_divisor) * channel_factor

        shelf_price_promo[t] = promo
        shelf_price_weighted[t] = weighted
        ex_factory_price[t] = ex_factory
        net_revenue[t] = ctx.volume_units[t] * ex_factory

    ctx.shelf_price_promo = shelf_price_promo
    ctx.shelf_price_weighted = shelf_price_weighted
    ctx.ex_factory_price = ex_factory_price
    ctx.net_revenue = net_revenue
    return ctx
