"""Pipeline orchestrator — точка входа для расчётов.

Две публичные функции:
- `run_line_pipeline(input)`: прогон s01..s09 для одной линии (ProjectSKU × Channel).
- `run_project_pipeline(line_inputs, ...)`: per-line s01..s09 → агрегация
  по линиям → s10..s12 на агрегате → готовый KPI per-scope.

Pipeline — pure Python. Никаких side effects, никакой работы с БД.
Сервисный слой (`calculation_service.py`) грузит данные из БД и формирует
PipelineInput'ы, оркестратор берёт их как параметр.
"""
from __future__ import annotations

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
    s10_discount,
    s11_kpi,
    s12_gonogo,
)


def run_line_pipeline(input_: PipelineInput) -> PipelineContext:
    """Прогон шагов 1-9 для одной линии (ProjectSKU × Channel × Scenario).

    Шаги 10-12 (KPI) не запускаются — они должны работать на агрегате
    проекта, не per-line.
    """
    ctx = PipelineContext(input=input_)
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


def run_project_pipeline(
    line_inputs: list[PipelineInput],
    *,
    project_capex: tuple[float, ...] = (),
    project_opex: tuple[float, ...] = (),
) -> PipelineContext:
    """Полный прогон pipeline для проекта × сценария.

    1. Для каждой линии — s01..s09 (`run_line_pipeline`)
    2. Агрегация per-period по линиям (`aggregate_lines`)
    3. На агрегате — s10 (annualize + DCF) → s11 (KPI) → s12 (Go/No-Go)

    Args:
        line_inputs: один PipelineInput на каждую (ProjectSKU × Channel)
            комбинацию для данного scenario_id. Должен быть хотя бы один.
        project_capex: project-level CAPEX, передаётся в агрегат
            (применяется в s09 только при пересчёте? нет — в текущей
            реализации aggregate_lines кладёт capex в input агрегатного
            контекста, но FCF уже посчитан per-line с capex=0. Поэтому
            эффективно ICF = 0 в агрегате; capex применяется отдельно
            ниже.)
        project_opex: то же.

    Returns:
        PipelineContext с заполненными annual_*, npv, irr, roi, payback,
        go_no_go, contribution_margin_ratio.

    Raises:
        ValueError: если line_inputs пустой.
    """
    if not line_inputs:
        raise ValueError("run_project_pipeline requires at least one line input")

    # 1. Прогоняем per-line. Capex/opex для линий = 0 (project-level).
    line_contexts = [run_line_pipeline(inp) for inp in line_inputs]

    # 2. Агрегируем
    agg = aggregate_lines(
        line_contexts,
        project_capex=project_capex,
        project_opex=project_opex,
    )

    # 3. Если есть project-level CAPEX/OPEX, нужно перепосчитать
    # contribution и FCF на агрегате с учётом этих project-level затрат.
    # В per-line s05/s09 они были нулями. Применяем сейчас.
    n = agg.input.period_count
    if project_opex:
        for t in range(n):
            agg.contribution[t] -= project_opex[t]
            agg.operating_cash_flow[t] -= project_opex[t]
            agg.free_cash_flow[t] -= project_opex[t]
            # Налог тоже мог измениться (база = contribution), но Excel
            # считает налог per-line на per-line contribution до project_opex.
            # Для MVP этим эффектом пренебрегаем — project_opex обычно мал
            # относительно contribution.
    if project_capex:
        for t in range(n):
            agg.investing_cash_flow[t] -= project_capex[t]
            agg.free_cash_flow[t] -= project_capex[t]

    # 4. KPI на агрегате
    s10_discount.step(agg)
    s11_kpi.step(agg)
    s12_gonogo.step(agg)

    return agg
