"""Шаг 2 — Price waterfall и Net Revenue.

Формулы (Excel: DASH rows 30-35, см. также ADR-CE-03 / D-02):
    SHELF_PRICE_PROMO[t]    = SHELF_PRICE_REG[t] × (1 − PROMO_DISCOUNT[t])
    SHELF_PRICE_WEIGHTED[t] = SHELF_PRICE_REG[t] × (1 − PROMO_SHARE[t])
                              + SHELF_PRICE_PROMO[t] × PROMO_SHARE[t]

    # ADR-CE-03 / D-02: VAT-стрипинг через ДЕЛЕНИЕ на (1+VAT), не умножение.
    EX_FACTORY_PRICE[t] = SHELF_PRICE_WEIGHTED[t] / (1 + VAT_RATE)
                          × (1 − CHANNEL_MARGIN[t])

    NET_REVENUE[t] = VOLUME_UNITS[t] × EX_FACTORY_PRICE[t]

ВНИМАНИЕ: формула ТЗ `× (1 − VAT_RATE)` — **неверна**. Разница для VAT=20%:
× 0.80 vs / 1.20 = × 0.8333 (ошибка −4.17% по ex_factory). См. ADR-CE-03.

D-20: channel_margin / promo_discount / promo_share — **per-period**, не
константы канала. GORJI снижает promo_share с 1.0 (M1..M27) до 0.8 (Y4..Y10),
что важно для match Excel в зрелые годы. Если все periods одинаковы —
service передаёт tuple([base]*n).

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

    shelf_price_promo: list[float] = [0.0] * n
    shelf_price_weighted: list[float] = [0.0] * n
    ex_factory_price: list[float] = [0.0] * n
    net_revenue: list[float] = [0.0] * n

    for t in range(n):
        reg = inp.shelf_price_reg[t]
        # D-20: per-period channel_margin / promo_discount / promo_share
        cm_t = inp.channel_margin[t]
        pd_t = inp.promo_discount[t]
        ps_t = inp.promo_share[t]

        promo = reg * (1.0 - pd_t)
        weighted = reg * (1.0 - ps_t) + promo * ps_t
        ex_factory = (weighted / vat_divisor) * (1.0 - cm_t)

        shelf_price_promo[t] = promo
        shelf_price_weighted[t] = weighted
        ex_factory_price[t] = ex_factory
        net_revenue[t] = ctx.volume_units[t] * ex_factory

    ctx.shelf_price_promo = shelf_price_promo
    ctx.shelf_price_weighted = shelf_price_weighted
    ctx.ex_factory_price = ex_factory_price
    ctx.net_revenue = net_revenue
    return ctx
