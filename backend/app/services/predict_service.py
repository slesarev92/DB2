"""Predict-слой: автогенерация ND/Offtake/Shelf Price для всех 43 периодов.

Вызывается при создании ProjectSKUChannel — заполняет PeriodValue с
`source_type=predict` для всех 3 сценариев проекта (Base/Conservative/
Aggressive). Сценарные дельты применяются runtime в pipeline (см.
`calculation_service.build_line_inputs`), поэтому predict значения
одинаковы для всех 3 сценариев.

Алгоритмы (из TZ_VS_EXCEL_DISCREPANCIES.md):

1. **ND рамп-ап (D-10):**
   ND[M1]      = nd_target × ND_START_PCT (= 0.20)
   ND[Mt]      = ND[M(t-1)] + (nd_target − ND[M1]) / nd_ramp_months   for t ∈ [2, ramp_months]
   ND[Mt > ramp_months]  = nd_target  (плато)
   ND[Yk] = nd_target  (годовые периоды Y4..Y10 — после рамп-апа)

2. **Offtake рамп-ап (D-11):** аналогично ND с тем же ramp_months
   (в текущей схеме отдельного offtake_ramp_months нет — используется
   `nd_ramp_months`).

3. **Shelf Price (D-08):**
   shelf[M1] = shelf_price_reg (база PSC)
   shelf[Mt] = shelf[M(t-1)] × (1 + monthly_deltas[(month_num−1)])
   где monthly_deltas — массив 12 значений для месяцев 1..12 из профиля
   `Project.inflation_profile_id` (RefInflation).
   shelf[Y4..Y10] = shelf[предыдущего годового или M36] × (1 + yearly_growth[k])
   где yearly_growth — массив 7 значений из того же профиля.
   Если у проекта нет инфляционного профиля → shelf константа.

Идемпотентность: при повторном вызове старые predict-записи (для всех
3 сценариев данного PSC) удаляются и заменяются новыми. Finetuned и
actual слои не трогаются.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Period,
    PeriodType,
    PeriodValue,
    Project,
    ProjectSKUChannel,
    RefInflation,
    Scenario,
    SourceType,
)


# Параметры рамп-апа из D-10/D-11. Стартуем с 20% от target.
ND_START_PCT = 0.20
OFFTAKE_START_PCT = 0.20


def _ramp_values(
    target: float,
    ramp_months: int,
    *,
    start_pct: float,
    n_monthly: int,
) -> list[float]:
    """Линейная интерполяция от target × start_pct до target за ramp_months.

    Возвращает массив длины n_monthly значений (по одному на каждый
    monthly период). После ramp_months значения = target (плато).

    Граничные случаи:
    - target = 0 → все нули
    - ramp_months = 0 → старт сразу с target (без рамп-апа)
    - ramp_months > n_monthly → не достигаем target в monthly периодах
    """
    if target == 0.0:
        return [0.0] * n_monthly
    if ramp_months <= 0:
        return [target] * n_monthly

    start = target * start_pct
    step = (target - start) / ramp_months  # инкремент за месяц

    out: list[float] = []
    for i in range(n_monthly):
        if i >= ramp_months:
            out.append(target)
        else:
            # i = 0 → start (M1), i = ramp_months − 1 → start + (ramp_months − 1)/ramp_months * (target − start)
            # i = ramp_months → target (но мы уже в else)
            out.append(start + step * i)
    return out


def _shelf_price_series(
    base_price: float,
    sorted_periods: list[Period],
    inflation_profile: RefInflation | None,
) -> list[float]:
    """Применяет инфляционный профиль к базовой shelf price.

    Алгоритм:
    - Для monthly периодов (M1..M36): shelf[t] = shelf[t-1] × (1 + monthly_deltas[month_num-1])
      М1 — стартует с base_price без модификации (даже если monthly_deltas[0] != 0;
      ступенька применяется при ПЕРЕХОДЕ в этот месяц).

      Wait — тогда как обработать M1 если monthly_deltas[0] (январь) > 0? Всё-таки
      delta применяется ПРИ ПЕРЕХОДЕ в месяц, т.е. shelf[M1] = base × (1 + delta[Jan])?

      Excel D-08 говорит: "SHELF_PRICE_REG[t] = SHELF_PRICE_REG[t-1] × (1 + MONTHLY_INFLATION[t])".
      Это значит дельта применяется на каждый месяц, включая первый. shelf[M1] = base × (1 + delta[Jan]).

      В GORJI тестах extracted: M1 (январь 2024) = 74.99, M2 (февраль) = 74.99, ..., M4 (апрель) = 74.99.
      Цена не растёт в апреле! Значит инфляция в shelf не была применена в этой части модели.

      Поэтому реализуем формулу D-08 буквально, но если профиль = "No_Inflation" или
      все коэффициенты 0 → shelf константа.

    - Для yearly периодов (Y4..Y10): shelf[Yk] = shelf[предыдущего] × (1 + yearly_growth[k-4]).
    """
    n = len(sorted_periods)
    if inflation_profile is None:
        return [base_price] * n

    raw = inflation_profile.month_coefficients or {}
    monthly_deltas: list[float] = []
    yearly_growth: list[float] = []
    if isinstance(raw, dict):
        monthly_deltas = [float(x) for x in raw.get("monthly_deltas", [0.0] * 12)]
        yearly_growth = [float(x) for x in raw.get("yearly_growth", [0.0] * 7)]

    if not monthly_deltas:
        monthly_deltas = [0.0] * 12
    if not yearly_growth:
        yearly_growth = [0.0] * 7

    out: list[float] = []
    prev_price = base_price
    for period in sorted_periods:
        if period.type == PeriodType.MONTHLY and period.month_num is not None:
            # Применяем месячную дельту при переходе
            delta = monthly_deltas[period.month_num - 1] if 0 <= period.month_num - 1 < 12 else 0.0
            prev_price = prev_price * (1.0 + delta)
        else:
            # Yearly период (Y4..Y10): индекс в yearly_growth = model_year - 4
            idx = period.model_year - 4
            growth = yearly_growth[idx] if 0 <= idx < len(yearly_growth) else 0.0
            prev_price = prev_price * (1.0 + growth)
        out.append(prev_price)
    return out


async def fill_predict_for_psk_channel(
    session: AsyncSession,
    psk_channel: ProjectSKUChannel,
    *,
    project: Project | None = None,
) -> int:
    """Создаёт 43×3 = 129 PeriodValue с predict-слоем для PSC.

    Args:
        session: AsyncSession.
        psk_channel: уже существующий ProjectSKUChannel.
        project: опционально — если уже загружен, не делаем запрос.

    Returns:
        Количество созданных PeriodValue (обычно 129 = 43 × 3 сценария).

    Идемпотентность: удаляет все существующие PREDICT записи для этого
    psk_channel (по всем сценариям) перед созданием новых. Finetuned и
    actual слои не трогаются.
    """
    # 1. Загружаем нужные данные
    if project is None:
        # Идём к проекту через project_sku → project
        from app.models import ProjectSKU

        psk = await session.get(ProjectSKU, psk_channel.project_sku_id)
        assert psk is not None
        project = await session.get(Project, psk.project_id)
        assert project is not None

    # 2. Все сценарии проекта (3 штуки)
    scenarios = (
        await session.scalars(
            select(Scenario).where(Scenario.project_id == project.id)
        )
    ).all()
    if not scenarios:
        return 0  # нет сценариев — нечего заполнять

    # 3. Сортированные периоды (43)
    sorted_periods = list(
        (await session.scalars(select(Period).order_by(Period.period_number))).all()
    )

    # 4. Инфляционный профиль (опц.)
    inflation_profile: RefInflation | None = None
    if project.inflation_profile_id is not None:
        inflation_profile = await session.get(
            RefInflation, project.inflation_profile_id
        )

    # 5. Считаем массивы значений
    n_monthly = sum(1 for p in sorted_periods if p.type == PeriodType.MONTHLY)
    nd_target = float(psk_channel.nd_target)
    offtake_target = float(psk_channel.offtake_target)
    ramp = int(psk_channel.nd_ramp_months)

    nd_monthly = _ramp_values(
        nd_target, ramp, start_pct=ND_START_PCT, n_monthly=n_monthly
    )
    offtake_monthly = _ramp_values(
        offtake_target, ramp, start_pct=OFFTAKE_START_PCT, n_monthly=n_monthly
    )

    base_shelf = float(psk_channel.shelf_price_reg)
    shelf_series = _shelf_price_series(base_shelf, sorted_periods, inflation_profile)

    # 6. Удаляем старый predict для этого psc по всем сценариям
    await session.execute(
        sql_delete(PeriodValue).where(
            PeriodValue.psk_channel_id == psk_channel.id,
            PeriodValue.source_type == SourceType.PREDICT,
        )
    )

    # 7. Создаём новые predict записи: 43 периода × 3 сценария
    created = 0
    monthly_idx = 0  # счётчик monthly периодов (для индексации nd_monthly/offtake_monthly)
    for period_idx, period in enumerate(sorted_periods):
        # ND/Offtake для текущего периода
        if period.type == PeriodType.MONTHLY:
            nd_val = nd_monthly[monthly_idx]
            offtake_val = offtake_monthly[monthly_idx]
            monthly_idx += 1
        else:
            # Yearly период (Y4..Y10) — после рамп-апа, всегда target
            nd_val = nd_target
            offtake_val = offtake_target

        shelf_val = shelf_series[period_idx]

        values: dict[str, Any] = {
            "nd": nd_val,
            "offtake": offtake_val,
            "shelf_price": shelf_val,
        }

        for sc in scenarios:
            session.add(
                PeriodValue(
                    psk_channel_id=psk_channel.id,
                    scenario_id=sc.id,
                    period_id=period.id,
                    source_type=SourceType.PREDICT,
                    version_id=1,
                    values=values,
                )
            )
            created += 1

    await session.flush()
    return created
