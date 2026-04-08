"""Service слой для ProjectFinancialPlan.

Два метода:
- `list_plan_by_year(session, project_id)` — возвращает всегда 10 строк
  Y1..Y10 (заполняя отсутствующие нулями) для удобства UI.
- `replace_plan(session, project_id, items)` — полная замена плана
  проекта. DELETE все существующие записи + INSERT новые по списку.

Маппинг year → period_id:
- Для **первого периода каждого model_year** берём запись из
  справочника `periods`. Для Y1 это M1 (period_number=1), Y2 — M13,
  Y3 — M25. Для Y4-Y10 — непосредственно Y4..Y10 period (period_number
  37..43). Pipeline аннуализирует по model_year в s10, поэтому
  конкретный period_id внутри года не важен для KPI.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Period, ProjectFinancialPlan
from app.schemas.financial_plan import FinancialPlanItem


async def _get_first_period_by_year(
    session: AsyncSession,
) -> dict[int, int]:
    """Возвращает {model_year → period_id первого периода года}.

    Для model_year 1-3 (monthly) — первый monthly период года (M1/M13/M25).
    Для model_year 4-10 (yearly) — тот единственный yearly period.
    """
    periods = (
        await session.scalars(select(Period).order_by(Period.period_number))
    ).all()
    by_year: dict[int, int] = {}
    for p in periods:
        if p.model_year not in by_year:
            by_year[p.model_year] = p.id
    return by_year


async def list_plan_by_year(
    session: AsyncSession,
    project_id: int,
) -> list[FinancialPlanItem]:
    """Всегда 10 строк Y1..Y10. Отсутствующие заполняются нулями.

    Суммирует capex/opex по всем записям `project_financial_plans`
    данного года — если несколько period_id принадлежат одному
    model_year, их значения складываются.
    """
    # Загружаем все plan записи с данными о периоде
    rows = (
        await session.execute(
            select(ProjectFinancialPlan, Period)
            .join(Period, Period.id == ProjectFinancialPlan.period_id)
            .where(ProjectFinancialPlan.project_id == project_id)
        )
    ).all()

    # Агрегация по model_year
    agg: dict[int, tuple[Decimal, Decimal]] = {
        year: (Decimal("0"), Decimal("0")) for year in range(1, 11)
    }
    for plan, period in rows:
        year = period.model_year
        if year in agg:
            capex_sum, opex_sum = agg[year]
            agg[year] = (capex_sum + plan.capex, opex_sum + plan.opex)

    return [
        FinancialPlanItem(year=year, capex=capex, opex=opex)
        for year, (capex, opex) in sorted(agg.items())
    ]


async def replace_plan(
    session: AsyncSession,
    project_id: int,
    items: list[FinancialPlanItem],
) -> list[FinancialPlanItem]:
    """Полная замена плана проекта.

    1. DELETE все существующие ProjectFinancialPlan для project_id
    2. INSERT новые записи (маппинг year → первый period_id года)
    3. Возвращает `list_plan_by_year` после flush

    Items с year которых нет в переданном списке → 0/0 в результате.
    Items с capex=0 и opex=0 всё равно сохраняются — это явное
    указание "ничего не тратим в этом году" и отличается от "не
    заполнено" (которое будет 0 по умолчанию в list_plan_by_year).
    """
    # 1. DELETE старые
    await session.execute(
        sql_delete(ProjectFinancialPlan).where(
            ProjectFinancialPlan.project_id == project_id
        )
    )

    # 2. Маппинг year → period_id
    year_to_period = await _get_first_period_by_year(session)

    # 3. INSERT новые
    for item in items:
        period_id = year_to_period.get(item.year)
        if period_id is None:
            continue  # невалидный year — игнорируем (валидация в схеме)
        session.add(
            ProjectFinancialPlan(
                project_id=project_id,
                period_id=period_id,
                capex=item.capex,
                opex=item.opex,
            )
        )

    await session.flush()

    # 4. Возвращаем актуальное состояние
    return await list_plan_by_year(session, project_id)
