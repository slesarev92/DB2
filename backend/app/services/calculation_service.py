"""Calculation Service — построение PipelineInput из БД и сохранение результатов.

Точка интеграции между расчётным ядром (`engine/`) и persistence-слоем
(SQLAlchemy). Pipeline никогда не трогает БД сам — этот сервис делает
все запросы, формирует in-memory PipelineInput'ы, передаёт в pipeline,
получает агрегатный PipelineContext с KPI, сохраняет ScenarioResult'ы.

Используется Celery-таской `tasks/calculate_project.py`.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.engine.context import PipelineInput
from app.engine.pipeline import run_project_pipeline
from app.models import (
    BOMItem,
    Channel,
    Period,
    PeriodValue,
    PeriodType,
    Project,
    ProjectFinancialPlan,
    ProjectSKU,
    ProjectSKUChannel,
    Scenario,
    ScenarioResult,
    SourceType,
)
from app.models.base import PeriodScope


# ============================================================
# Custom exceptions
# ============================================================


class ProjectNotFoundError(Exception):
    """project_id не существует или soft-deleted."""


class NoLinesError(Exception):
    """В проекте нет ProjectSKU/ProjectSKUChannel — pipeline нечего считать."""


class IncompletePeriodValuesError(Exception):
    """Для (psk_channel × scenario) не хватает PeriodValue для покрытия 43 периодов."""


# ============================================================
# Period catalog cache (in-memory) — periods неизменны после seed
# ============================================================


async def _load_period_catalog(
    session: AsyncSession,
) -> tuple[list[Period], dict[int, Period]]:
    """Все 43 строки справочника periods, отсортированные по period_number.

    Возвращает (sorted list, dict by period_id) — оба нужны при формировании input.
    """
    rows = (
        await session.scalars(select(Period).order_by(Period.period_number))
    ).all()
    return list(rows), {p.id: p for p in rows}


async def _load_project_financial_plan(
    session: AsyncSession,
    project_id: int,
    sorted_periods: list[Period],
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Загружает project-level CAPEX/OPEX из таблицы project_financial_plans.

    Возвращает кортеж (capex_tuple, opex_tuple) длины len(sorted_periods).
    Если для какого-то period_id записи нет — соответствующий элемент = 0.0.
    Если в таблице вообще нет записей для проекта — возвращает пустые
    кортежи (`run_project_pipeline` трактует это как "без project-level
    оттоков", FCF = OCF).
    """
    rows = (
        await session.scalars(
            select(ProjectFinancialPlan).where(
                ProjectFinancialPlan.project_id == project_id
            )
        )
    ).all()
    if not rows:
        return (), ()

    by_period: dict[int, ProjectFinancialPlan] = {r.period_id: r for r in rows}

    capex_arr: list[float] = []
    opex_arr: list[float] = []
    for period in sorted_periods:
        plan = by_period.get(period.id)
        capex_arr.append(float(plan.capex) if plan else 0.0)
        opex_arr.append(float(plan.opex) if plan else 0.0)

    return tuple(capex_arr), tuple(opex_arr)


# ============================================================
# Effective period values (priority actual > finetuned > predict)
# ============================================================


async def _fetch_effective_values(
    session: AsyncSession,
    psk_channel_id: int,
    scenario_id: int,
) -> dict[int, dict]:
    """Возвращает {period_id: values_dict} с применённым приоритетом слоёв.

    Дублирует логику из period_value_service._resolve_priority, но
    оптимизировано для использования в pipeline (не возвращает Pydantic
    схемы). Берёт latest version для каждого слоя, потом применяет
    приоритет actual > finetuned > predict.
    """
    rows = (
        await session.execute(
            select(PeriodValue).where(
                PeriodValue.psk_channel_id == psk_channel_id,
                PeriodValue.scenario_id == scenario_id,
            )
        )
    ).scalars().all()

    # period_id → {source_type → latest_pv}
    by_period: dict[int, dict[SourceType, PeriodValue]] = {}
    for pv in rows:
        layer = by_period.setdefault(pv.period_id, {})
        existing = layer.get(pv.source_type)
        if existing is None or pv.version_id > existing.version_id:
            layer[pv.source_type] = pv

    effective: dict[int, dict] = {}
    for period_id, layers in by_period.items():
        if SourceType.ACTUAL in layers:
            effective[period_id] = layers[SourceType.ACTUAL].values
        elif SourceType.FINETUNED in layers:
            effective[period_id] = layers[SourceType.FINETUNED].values
        elif SourceType.PREDICT in layers:
            effective[period_id] = layers[SourceType.PREDICT].values
    return effective


# ============================================================
# Build PipelineInput для одной (PSK × PSC × Scenario) линии
# ============================================================


async def _load_seasonality_coefficients(
    session: AsyncSession,
    profile_id: int | None,
) -> dict[int, float]:
    """Возвращает {month_num: coefficient} для профиля сезонности.

    Если profile_id None — возвращает пустой dict (трактуется как 1.0).
    Структура JSONB month_coefficients задана в seed_reference_data:
    список из 12 чисел в порядке месяцев январь..декабрь.
    """
    if profile_id is None:
        return {}
    from app.models import RefSeasonality

    profile = await session.get(RefSeasonality, profile_id)
    if profile is None:
        return {}

    raw = profile.month_coefficients or {}
    # Поддерживаемые форматы:
    # 1. list из 12 чисел (легаси)
    # 2. dict {"months": [12 чисел]} — формат seed_reference_data WTR/CSD/...
    # 3. dict {"1": coef, "2": coef, ...} — flat dict с числовыми ключами
    if isinstance(raw, list):
        return {i + 1: float(raw[i]) for i in range(min(12, len(raw)))}
    if isinstance(raw, dict):
        # Nested format: {"months": [...]}
        if "months" in raw and isinstance(raw["months"], list):
            months_list = raw["months"]
            return {i + 1: float(months_list[i]) for i in range(min(12, len(months_list)))}
        # Flat numeric-keyed format
        try:
            return {int(k): float(v) for k, v in raw.items()}
        except (ValueError, TypeError):
            return {}
    return {}


async def _build_line_input(
    session: AsyncSession,
    *,
    project: Project,
    psk: ProjectSKU,
    psc: ProjectSKUChannel,
    scenario: Scenario,
    sorted_periods: list[Period],
    inflation_profile: "RefInflation | None" = None,
) -> PipelineInput:
    """Собирает PipelineInput для одной (psk × psc × scenario) линии."""
    # Effective values по периодам
    effective = await _fetch_effective_values(session, psc.id, scenario.id)

    # BOM unit cost: Σ(quantity × price × (1 + loss_pct)) — БАЗОВОЕ значение
    # (на M1 до инфляции). Per-period серия строится через inflate_series ниже,
    # либо берётся из effective values (D-16: для GORJI Excel custom inflation
    # logic, который не воспроизводим стандартным профилем).
    bom_rows = (
        await session.scalars(
            select(BOMItem).where(BOMItem.project_sku_id == psk.id)
        )
    ).all()
    bom_unit_cost_base = 0.0
    for b in bom_rows:
        bom_unit_cost_base += float(
            b.quantity_per_unit * b.price_per_unit * (Decimal("1") + b.loss_pct)
        )

    # Инфляционная серия BOM по periods. Excel применяет тот же
    # inflation_profile к row 36/37 DASH что и к shelf_price (D-08).
    # Для consistency используем тот же helper из predict_service.
    from app.services.predict_service import inflate_series

    bom_unit_cost_series_default = inflate_series(
        bom_unit_cost_base, sorted_periods, inflation_profile
    )

    # Channel.universe_outlets
    channel_obj = await session.get(Channel, psc.channel_id)
    universe = int(channel_obj.universe_outlets) if channel_obj and channel_obj.universe_outlets else 0

    # Сезонность по профилю PSC
    season_coefs = await _load_seasonality_coefficients(session, psc.seasonality_profile_id)

    # Per-period массивы
    n = len(sorted_periods)
    nd_arr: list[float] = []
    offtake_arr: list[float] = []
    shelf_arr: list[float] = []
    bom_arr: list[float] = []   # D-16: per-period bom_unit_cost
    log_arr: list[float] = []   # D-18: per-period logistics_cost_per_kg
    cm_arr: list[float] = []    # D-20: per-period channel_margin
    pd_arr: list[float] = []    # D-20: per-period promo_discount
    ps_arr: list[float] = []    # D-20: per-period promo_share
    seasonality_arr: list[float] = []
    is_monthly: list[bool] = []
    month_num: list[int | None] = []
    model_year: list[int] = []

    static_log_per_kg = float(psc.logistics_cost_per_kg)
    static_cm = float(psc.channel_margin)
    static_pd = float(psc.promo_discount)
    static_ps = float(psc.promo_share)

    for i, period in enumerate(sorted_periods):
        vals = effective.get(period.id, {})
        nd_arr.append(float(vals.get("nd", 0.0)))
        offtake_arr.append(float(vals.get("offtake", 0.0)))
        # shelf_price может быть в значениях, иначе берём static из PSC
        shelf_arr.append(float(vals.get("shelf_price", float(psc.shelf_price_reg))))

        # D-16: bom_unit_cost из effective values если есть, иначе fallback
        # на inflate_series от BOMItem M1 base (стандартное поведение).
        if "bom_unit_cost" in vals:
            bom_arr.append(float(vals["bom_unit_cost"]))
        else:
            bom_arr.append(float(bom_unit_cost_series_default[i]))

        # D-18: logistics_cost_per_kg из effective values если есть, иначе
        # static из PSC (текущее поведение для projects без per-period).
        log_arr.append(float(vals.get("logistic_per_kg", static_log_per_kg)))

        # D-20: channel_margin / promo_discount / promo_share per-period.
        # Excel GORJI меняет promo_share с 1.0 (M1..M27) до 0.8 (Y4..Y10)
        # — это влияет на ex_factory и NR на 6-8% в зрелые годы.
        cm_arr.append(float(vals.get("channel_margin", static_cm)))
        pd_arr.append(float(vals.get("promo_discount", static_pd)))
        ps_arr.append(float(vals.get("promo_share", static_ps)))

        # Сезонность только для monthly периодов
        if period.type == PeriodType.MONTHLY and period.month_num is not None:
            coef = season_coefs.get(period.month_num, 1.0)
            seasonality_arr.append(coef)
            is_monthly.append(True)
            month_num.append(period.month_num)
        else:
            seasonality_arr.append(1.0)
            is_monthly.append(False)
            month_num.append(None)
        model_year.append(period.model_year)

    # Применение scenario delta к ND и offtake (Conservative/Aggressive)
    # delta_nd = -0.10 → −10% от base
    delta_nd = float(scenario.delta_nd)
    delta_offtake = float(scenario.delta_offtake)
    if delta_nd != 0.0:
        nd_arr = [v * (1.0 + delta_nd) for v in nd_arr]
    if delta_offtake != 0.0:
        offtake_arr = [v * (1.0 + delta_offtake) for v in offtake_arr]

    # Launch lag (D-13): обнуляем nd/offtake для periods до launch month.
    # Excel хранит launch_year/launch_month per (SKU × Channel), не per
    # SKU — TT/E-COM каналы запускаются раньше HM/SM/MM. Поля живут на
    # ProjectSKUChannel, а не на ProjectSKU.
    #
    # Pipeline считает volume = active × offtake × seasonality, поэтому
    # nd=0 ИЛИ offtake=0 → volume=0 → весь downstream автоматически = 0.
    # Не нужно трогать pipeline шаги.
    #
    # absolute_period_number вычисляется так:
    # - Y1 Jan → 1, Y1 Dec → 12, Y2 Jan → 13, Y2 Dec → 24, Y3 Dec → 36
    # - Y4..Y10 (yearly periods) → period_number 37..43
    # Для launch_year >= 4 month игнорируется (yearly periods нет months).
    if psc.launch_year > 3:
        # Yearly launch: M1..M36 + Y4..Y(launch_year-1) обнуляем
        launch_period_number = 36 + (psc.launch_year - 3)
    else:
        launch_period_number = (psc.launch_year - 1) * 12 + psc.launch_month
    # Все periods c period_number < launch_period_number → 0
    # sorted_periods отсортирован по period_number, поэтому индекс
    # совпадает с (period.period_number - 1)
    for i, period in enumerate(sorted_periods):
        if period.period_number < launch_period_number:
            nd_arr[i] = 0.0
            offtake_arr[i] = 0.0

    return PipelineInput(
        project_sku_channel_id=psc.id,
        scenario_id=scenario.id,
        period_count=n,
        period_is_monthly=tuple(is_monthly),
        period_month_num=tuple(month_num),
        period_model_year=tuple(model_year),
        nd=tuple(nd_arr),
        offtake=tuple(offtake_arr),
        shelf_price_reg=tuple(shelf_arr),
        seasonality=tuple(seasonality_arr),
        universe_outlets=universe,
        channel_margin=tuple(cm_arr),
        promo_discount=tuple(pd_arr),
        promo_share=tuple(ps_arr),
        vat_rate=float(project.vat_rate),
        bom_unit_cost=tuple(bom_arr),
        production_cost_rate=float(psk.production_cost_rate),
        copacking_per_unit=0.0,  # MVP: нет поля в схеме
        logistics_cost_per_kg=tuple(log_arr),
        sku_volume_l=float(psk.sku.volume_l) if psk.sku.volume_l else 0.0,
        ca_m_rate=float(psk.ca_m_rate),
        marketing_rate=float(psk.marketing_rate),
        wc_rate=float(project.wc_rate),
        tax_rate=float(project.tax_rate),
        wacc=float(project.wacc),
        product_density=1.0,
        project_opex=(),
        capex=(),
    )


async def build_line_inputs(
    session: AsyncSession,
    project_id: int,
    scenario_id: int,
) -> list[PipelineInput]:
    """Грузит все (PSK × PSC) комбинации проекта и формирует PipelineInput'ы.

    Async-safe: использует selectinload для всех relationship'ов чтобы
    избежать lazy="raise_on_sql" исключений.
    """
    # Project (без soft-deleted)
    project = await session.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise ProjectNotFoundError(f"Project {project_id} not found")

    # Scenario (должен принадлежать проекту)
    scenario = await session.get(Scenario, scenario_id)
    if scenario is None or scenario.project_id != project_id:
        raise ProjectNotFoundError(
            f"Scenario {scenario_id} does not belong to project {project_id}"
        )

    # Все ProjectSKU проекта с подгруженным SKU
    psk_rows = (
        await session.scalars(
            select(ProjectSKU)
            .where(ProjectSKU.project_id == project_id, ProjectSKU.include == True)  # noqa: E712
            .options(selectinload(ProjectSKU.sku))
        )
    ).all()

    if not psk_rows:
        raise NoLinesError(f"Project {project_id} has no included ProjectSKU rows")

    sorted_periods, _ = await _load_period_catalog(session)

    # Inflation profile проекта (опц.) — нужен для inflate_series в
    # _build_line_input. Загружаем один раз на проект, переиспользуем
    # для всех линий.
    from app.models import RefInflation

    inflation_profile: RefInflation | None = None
    if project.inflation_profile_id is not None:
        inflation_profile = await session.get(
            RefInflation, project.inflation_profile_id
        )

    inputs: list[PipelineInput] = []
    for psk in psk_rows:
        # ProjectSKUChannel'ы для этого PSK
        psc_rows = (
            await session.scalars(
                select(ProjectSKUChannel)
                .where(ProjectSKUChannel.project_sku_id == psk.id)
                .options(selectinload(ProjectSKUChannel.channel))
            )
        ).all()
        for psc in psc_rows:
            inp = await _build_line_input(
                session,
                project=project,
                psk=psk,
                psc=psc,
                scenario=scenario,
                sorted_periods=sorted_periods,
                inflation_profile=inflation_profile,
            )
            inputs.append(inp)

    if not inputs:
        raise NoLinesError(
            f"Project {project_id} has ProjectSKU but no ProjectSKUChannel rows"
        )

    return inputs


# ============================================================
# High-level: посчитать сценарий и сохранить ScenarioResult
# ============================================================


def _decimal_or_none(value: float | None) -> Decimal | None:
    """Конвертирует float → Decimal для записи в Numeric колонки.

    None пробрасывает как None (NULL в БД).
    """
    if value is None:
        return None
    return Decimal(str(value))


_SCOPE_TO_ENUM = {
    "y1y3": PeriodScope.Y1Y3,
    "y1y5": PeriodScope.Y1Y5,
    "y1y10": PeriodScope.Y1Y10,
}


async def calculate_and_save_scenario(
    session: AsyncSession,
    project_id: int,
    scenario_id: int,
) -> list[ScenarioResult]:
    """Полный расчёт одного сценария + сохранение 3 ScenarioResult'ов.

    Алгоритм:
    1. build_line_inputs из БД (per-line PipelineInput'ы)
    2. _load_project_financial_plan (project-level CAPEX/OPEX)
    3. run_project_pipeline (per-line s01..s09 + aggregate + project-level
       capex/opex applied + s10..s12)
    4. Старые ScenarioResult'ы сценария удаляются (полный пересчёт)
    5. Создаются 3 новых ScenarioResult — один на скоуп

    Returns: список из 3 свежих ScenarioResult.
    """
    line_inputs = await build_line_inputs(session, project_id, scenario_id)

    # Project-level CAPEX/OPEX независимы от scenario — общие для всех 3.
    sorted_periods, _ = await _load_period_catalog(session)
    project_capex, project_opex = await _load_project_financial_plan(
        session, project_id, sorted_periods
    )

    agg = run_project_pipeline(
        line_inputs,
        project_capex=project_capex,
        project_opex=project_opex,
    )

    # Удаляем старые результаты сценария
    from sqlalchemy import delete as sql_delete

    await session.execute(
        sql_delete(ScenarioResult).where(ScenarioResult.scenario_id == scenario_id)
    )

    cm_ratio = agg.contribution_margin_ratio
    # EBITDA margin overall: sum(ebitda)/sum(NR). Используем annual_*.
    total_nr = sum(agg.annual_net_revenue) if agg.annual_net_revenue else 0.0
    total_ebitda = sum(agg.ebitda) if agg.ebitda else 0.0
    ebitda_margin = total_ebitda / total_nr if total_nr else None

    results: list[ScenarioResult] = []
    for scope_str, scope_enum in _SCOPE_TO_ENUM.items():
        result = ScenarioResult(
            scenario_id=scenario_id,
            period_scope=scope_enum,
            npv=_decimal_or_none(agg.npv.get(scope_str)),
            irr=_decimal_or_none(agg.irr.get(scope_str)),
            roi=_decimal_or_none(agg.roi.get(scope_str)),
            payback_simple=_decimal_or_none(
                float(agg.payback_simple.get(scope_str))
                if agg.payback_simple.get(scope_str) is not None
                else None
            ),
            payback_discounted=_decimal_or_none(
                float(agg.payback_discounted.get(scope_str))
                if agg.payback_discounted.get(scope_str) is not None
                else None
            ),
            contribution_margin=_decimal_or_none(cm_ratio),
            ebitda_margin=_decimal_or_none(ebitda_margin),
            go_no_go=agg.go_no_go.get(scope_str),
        )
        session.add(result)
        results.append(result)

    await session.flush()
    for r in results:
        await session.refresh(r)
    return results


async def calculate_all_scenarios(
    session: AsyncSession,
    project_id: int,
) -> dict[int, list[ScenarioResult]]:
    """Пересчитывает все сценарии проекта (Base/Conservative/Aggressive).

    Returns: {scenario_id: [3 ScenarioResult]}.
    """
    project = await session.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise ProjectNotFoundError(f"Project {project_id} not found")

    scenarios = (
        await session.scalars(
            select(Scenario).where(Scenario.project_id == project_id)
        )
    ).all()

    out: dict[int, list[ScenarioResult]] = {}
    for sc in scenarios:
        out[sc.id] = await calculate_and_save_scenario(session, project_id, sc.id)
    return out
