"""Агрегация per-line PipelineContext'ов в один project-level контекст.

После прогона s01..s09 для каждой линии (ProjectSKU × Channel) получаем
list[PipelineContext]. Чтобы рассчитать project-level KPI (NPV/IRR/ROI/etc),
нужно сложить per-period значения по всем линиям и затем прогнать s10..s12
на агрегате.

Все per-period массивы (volume, NR, COGS, GP, CM, FCF и т.д.) — линейны
по линиям, поэтому aggregate = element-wise sum. Period_count, period_*
структура и project-level параметры (wacc, wc_rate, tax_rate) одинаковы
для всех линий в одном проекте × сценарии — берём из первой линии.

CAPEX и PROJECT_OPEX в текущей схеме хранятся в Project (на уровне проекта,
не линии). При построении PipelineInput для конкретной линии мы передаём
их как пустые tuples. Здесь, в агрегаторе, можно подставить реальные
project-level массивы — но в задаче 2.4 мы пока оставляем их пустыми
(будут добавлены в Phase 3 когда появится UI для редактирования
project_capex / project_opex).
"""
from __future__ import annotations

from app.engine.context import PipelineContext, PipelineInput


def aggregate_lines(
    line_contexts: list[PipelineContext],
    *,
    project_capex: tuple[float, ...] = (),
    project_opex: tuple[float, ...] = (),
) -> PipelineContext:
    """Складывает per-line PipelineContext'ы в один агрегатный.

    Args:
        line_contexts: список контекстов после прогона s01..s09 каждой линии.
        project_capex: project-level CAPEX, заменит пустой capex линий
            при формировании агрегатного input. Если пустой — нули.
        project_opex: то же для project_opex.

    Returns:
        Новый PipelineContext где `input` — агрегатный (метаданные первой
        линии + project-level capex/opex), а per-period массивы (NR, CM,
        FCF и т.д.) — суммы по всем линиям. Готов для подачи в s10..s12.

    Raises:
        ValueError: если list пустой или линии имеют разную длину горизонта.
    """
    if not line_contexts:
        raise ValueError("aggregate_lines requires at least one line context")

    first = line_contexts[0]
    n = first.input.period_count

    # Sanity check: все линии должны иметь одинаковый горизонт
    for i, ctx in enumerate(line_contexts):
        if ctx.input.period_count != n:
            raise ValueError(
                f"Line {i} has period_count={ctx.input.period_count}, "
                f"expected {n} (mismatch with line 0)"
            )

    # Агрегатный input: метаданные временной оси из первой линии,
    # project-level параметры (wacc, wc_rate, tax_rate, vat_rate) тоже
    # из первой (они одинаковы по контракту), все per-line параметры
    # обнуляются (формально не используются в s10..s12, но валидация
    # PipelineInput.__post_init__ требует валидные значения).
    agg_input = PipelineInput(
        project_sku_channel_id=0,         # 0 = aggregate, не реальная линия
        scenario_id=first.input.scenario_id,
        period_count=n,
        period_is_monthly=first.input.period_is_monthly,
        period_month_num=first.input.period_month_num,
        period_model_year=first.input.period_model_year,
        # Per-period inputs больше не нужны после s09 (s10 работает с
        # вычисленными per-period значениями), но валидация требует
        # длины. Заполняем нулями.
        nd=tuple([0.0] * n),
        offtake=tuple([0.0] * n),
        shelf_price_reg=tuple([0.0] * n),
        seasonality=tuple([1.0] * n),
        universe_outlets=0,
        channel_margin=tuple([0.0] * n),
        promo_discount=tuple([0.0] * n),
        promo_share=tuple([0.0] * n),
        vat_rate=first.input.vat_rate,
        bom_unit_cost=tuple([0.0] * n),
        production_cost_rate=tuple([0.0] * n),
        copacking_per_unit=0.0,
        logistics_cost_per_kg=tuple([0.0] * n),
        sku_volume_l=0.0,
        ca_m_rate=0.0,
        marketing_rate=0.0,
        wc_rate=first.input.wc_rate,
        tax_rate=first.input.tax_rate,
        wacc=first.input.wacc,
        product_density=1.0,
        project_opex=project_opex,
        capex=project_capex,
    )

    agg = PipelineContext(input=agg_input)

    # Element-wise sum по линиям. Все per-period массивы у линий одной длины n.
    def _sum_field(field_name: str) -> list[float]:
        out = [0.0] * n
        for ctx in line_contexts:
            arr = getattr(ctx, field_name)
            for t in range(n):
                out[t] += arr[t]
        return out

    agg.active_outlets = _sum_field("active_outlets")
    agg.volume_units = _sum_field("volume_units")
    agg.volume_liters = _sum_field("volume_liters")
    # Price waterfall не агрегируется — это per-unit характеристика.
    # Оставляем пустыми (s10 их не использует).
    agg.shelf_price_promo = []
    agg.shelf_price_weighted = []
    agg.ex_factory_price = []

    agg.net_revenue = _sum_field("net_revenue")
    agg.cogs_material = _sum_field("cogs_material")
    agg.cogs_production = _sum_field("cogs_production")
    agg.cogs_copacking = _sum_field("cogs_copacking")
    agg.cogs_total = _sum_field("cogs_total")
    agg.gross_profit = _sum_field("gross_profit")
    agg.logistics_cost = _sum_field("logistics_cost")
    agg.contribution = _sum_field("contribution")
    agg.ca_m_cost = _sum_field("ca_m_cost")
    agg.marketing_cost = _sum_field("marketing_cost")
    agg.ebitda = _sum_field("ebitda")
    agg.working_capital = _sum_field("working_capital")
    agg.delta_working_capital = _sum_field("delta_working_capital")
    agg.tax = _sum_field("tax")
    agg.operating_cash_flow = _sum_field("operating_cash_flow")
    agg.investing_cash_flow = _sum_field("investing_cash_flow")
    agg.free_cash_flow = _sum_field("free_cash_flow")

    return agg
