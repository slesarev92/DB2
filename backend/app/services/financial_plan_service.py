"""Service слой для ProjectFinancialPlan.

B.9b (2026-05-15): per-period вместо per-year. list_plan_by_period
возвращает 43 элемента (1 на каждый период справочника). replace_plan
сохраняет по period_number.

Маппинг period_number → period_id через справочник `periods`:
period_number 1..36 = monthly Y1-Y3 (M1..M36, model_year 1..3),
period_number 37..43 = yearly Y4..Y10 (model_year 4..10).
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


async def _get_period_id_by_number(
    session: AsyncSession,
) -> dict[int, int]:
    """Возвращает {period_number → period_id} для всех 43 периодов справочника."""
    rows = (
        await session.scalars(select(Period).order_by(Period.period_number))
    ).all()
    return {p.period_number: p.id for p in rows}


async def list_plan_by_period(
    session: AsyncSession,
    project_id: int,
) -> list[FinancialPlanItem]:
    """Всегда 43 строки (period_number 1..43). Отсутствующие — нули.

    Загружает все ProjectFinancialPlan записи проекта + Period (для
    маппинга на period_number) + opex_items/capex_items через selectinload.
    """
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

    by_period: dict[int, tuple[ProjectFinancialPlan, Period]] = {
        period.period_number: (plan, period) for plan, period in rows
    }

    result: list[FinancialPlanItem] = []
    for pn in range(1, 44):
        if pn in by_period:
            plan, _ = by_period[pn]
            result.append(
                FinancialPlanItem(
                    period_number=pn,
                    capex=plan.capex,
                    opex=plan.opex,
                    opex_items=[
                        OpexItemSchema(
                            category=item.category,
                            name=item.name,
                            amount=item.amount,
                        )
                        for item in plan.opex_items
                    ],
                    capex_items=[
                        CapexItemSchema(
                            category=item.category,
                            name=item.name,
                            amount=item.amount,
                        )
                        for item in plan.capex_items
                    ],
                )
            )
        else:
            result.append(
                FinancialPlanItem(
                    period_number=pn,
                    capex=Decimal("0"),
                    opex=Decimal("0"),
                    opex_items=[],
                    capex_items=[],
                )
            )
    return result


async def replace_plan(
    session: AsyncSession,
    project_id: int,
    items: list[FinancialPlanItem],
) -> list[FinancialPlanItem]:
    """Полная замена плана проекта.

    1. DELETE все ProjectFinancialPlan для project_id
       (CASCADE удаляет opex_items и capex_items).
    2. INSERT новые записи по period_number → period_id.
    3. INSERT OpexItem и CapexItem (если есть).
    4. Возвращает `list_plan_by_period` (43 элемента).

    period_number'ы которых нет в items → 0/0 в результате.
    """
    logger.info(
        "replace_plan project_id=%s items=%s",
        project_id,
        [
            (
                item.period_number,
                str(item.capex),
                str(item.opex),
                len(item.opex_items or []),
                len(item.capex_items or []),
            )
            for item in items
        ],
    )

    await session.execute(
        sql_delete(ProjectFinancialPlan).where(
            ProjectFinancialPlan.project_id == project_id
        )
    )

    period_map = await _get_period_id_by_number(session)

    for item in items:
        period_id = period_map.get(item.period_number)
        if period_id is None:
            continue

        effective_opex = item.opex
        if item.opex_items:
            effective_opex = sum(
                (oi.amount for oi in item.opex_items), Decimal("0")
            )
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

        if item.opex_items or item.capex_items:
            await session.flush()
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
    return await list_plan_by_period(session, project_id)
