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

import logging
from decimal import Decimal

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import CapexItem, OpexItem, Period, ProjectFinancialPlan
from app.schemas.financial_plan import (
    CapexItemSchema,
    FinancialPlanItem,
    OpexItemSchema,
)

logger = logging.getLogger(__name__)


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
    model_year, их значения складываются. opex_items загружаются
    через selectinload и включаются в ответ (B-19).
    """
    # Загружаем все plan записи с данными о периоде + opex_items + capex_items
    rows = (
        await session.execute(
            select(ProjectFinancialPlan, Period)
            .join(Period, Period.id == ProjectFinancialPlan.period_id)
            .where(ProjectFinancialPlan.project_id == project_id)
            .options(
                selectinload(ProjectFinancialPlan.opex_items),
                selectinload(ProjectFinancialPlan.capex_items),
            )
        )
    ).all()

    # Агрегация по model_year. Tuple элементы: capex_sum, opex_sum,
    # opex_items, capex_items.
    agg: dict[
        int,
        tuple[Decimal, Decimal, list[OpexItemSchema], list[CapexItemSchema]],
    ] = {
        year: (Decimal("0"), Decimal("0"), [], []) for year in range(1, 11)
    }
    for plan, period in rows:
        year = period.model_year
        if year in agg:
            capex_sum, opex_sum, opex_items, capex_items = agg[year]
            agg[year] = (
                capex_sum + plan.capex,
                opex_sum + plan.opex,
                opex_items + [
                    OpexItemSchema(
                        category=item.category,
                        name=item.name,
                        amount=item.amount,
                    )
                    for item in plan.opex_items
                ],
                capex_items + [
                    CapexItemSchema(
                        category=item.category,
                        name=item.name,
                        amount=item.amount,
                    )
                    for item in plan.capex_items
                ],
            )

    return [
        FinancialPlanItem(
            year=year,
            capex=capex,
            opex=opex,
            opex_items=opex_items,
            capex_items=capex_items,
        )
        for year, (capex, opex, opex_items, capex_items) in sorted(agg.items())
    ]


async def replace_plan(
    session: AsyncSession,
    project_id: int,
    items: list[FinancialPlanItem],
) -> list[FinancialPlanItem]:
    """Полная замена плана проекта.

    1. DELETE все существующие ProjectFinancialPlan для project_id
       (CASCADE удаляет связанные opex_items)
    2. INSERT новые записи (маппинг year → первый period_id года)
    3. Если opex_items не пустой → opex = sum(items), INSERT OpexItem'ы
    4. Возвращает `list_plan_by_year` после flush

    Items с year которых нет в переданном списке → 0/0 в результате.
    Items с capex=0 и opex=0 всё равно сохраняются — это явное
    указание "ничего не тратим в этом году" и отличается от "не
    заполнено" (которое будет 0 по умолчанию в list_plan_by_year).
    """
    # Диагностический лог payload — поможет ловить D-2 (intermittent
    # save error) и D-3 (CAPEX=0 crash). Безопасно: только числовые
    # поля + структура, без PII.
    logger.info(
        "replace_plan project_id=%s items=%s",
        project_id,
        [
            (
                item.year,
                str(item.capex),
                str(item.opex),
                len(item.opex_items or []),
                len(item.capex_items or []),
            )
            for item in items
        ],
    )

    # 1. DELETE старые (CASCADE → opex_items тоже удаляются)
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

        # Если есть opex_items — opex = sum(amounts)
        effective_opex = item.opex
        if item.opex_items:
            effective_opex = sum(
                (oi.amount for oi in item.opex_items), Decimal("0")
            )
        # Аналогично для CAPEX: если есть capex_items — capex = sum(amounts).
        effective_capex = item.capex
        if item.capex_items:
            effective_capex = sum(
                (ci.amount for ci in item.capex_items), Decimal("0")
            )

        plan = ProjectFinancialPlan(
            project_id=project_id,
            period_id=period_id,
            capex=effective_capex,
            opex=effective_opex,
        )
        session.add(plan)

        # INSERT OpexItem / CapexItem если есть
        if item.opex_items or item.capex_items:
            await session.flush()  # получаем plan.id
            for oi in item.opex_items:
                session.add(
                    OpexItem(
                        financial_plan_id=plan.id,
                        category=oi.category,
                        name=oi.name,
                        amount=oi.amount,
                    )
                )
            for ci in item.capex_items:
                session.add(
                    CapexItem(
                        financial_plan_id=plan.id,
                        category=ci.category,
                        name=ci.name,
                        amount=ci.amount,
                    )
                )

    await session.flush()

    # 4. Возвращаем актуальное состояние
    return await list_plan_by_year(session, project_id)
