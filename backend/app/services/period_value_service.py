"""PeriodValue service: трёхслойная модель данных, версионирование, view modes.

Реализация ADR-05 (приоритет actual > finetuned > predict) и плана
задачи 1.5. Версионирование append-only: каждый PATCH создаёт новую
строку с увеличенным version_id, старые остаются как audit log.

Predict-слой в 1.5 НЕ генерируется автоматически — это задача 2.5.
Тесты создают predict вручную через сервис при необходимости.

Actual-слой в 1.5 архитектурно поддерживается через source_type, но
endpoint для записи actual не делается (импорт actual из Excel —
backlog B-02).
"""
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Period,
    PeriodValue,
    ProjectSKU,
    ProjectSKUChannel,
    Scenario,
    SourceType,
)
from app.schemas.period_value import (
    CompareResponseItem,
    HybridResponseItem,
)


# ============================================================
# Custom exceptions для validation
# ============================================================


class PSKChannelNotFoundError(Exception):
    """psk_channel_id не существует."""


class PeriodNotFoundError(Exception):
    """period_id не существует в справочнике."""


class ScenarioMismatchError(Exception):
    """scenario_id не существует или не принадлежит тому же проекту."""


# ============================================================
# Validation
# ============================================================


async def validate_context(
    session: AsyncSession,
    psk_channel_id: int,
    scenario_id: int,
    period_id: int | None = None,
) -> tuple[ProjectSKUChannel, Scenario, Period | None]:
    """Проверяет всю цепочку для PeriodValue запроса.

    Бизнес-инвариант: scenario должен принадлежать тому же проекту,
    к которому привязан psk_channel (через ProjectSKU).

    Возвращает (psk_channel, scenario, period|None).
    Поднимает соответствующее исключение при первой неудаче.
    """
    psk_channel = await session.get(ProjectSKUChannel, psk_channel_id)
    if psk_channel is None:
        raise PSKChannelNotFoundError()

    scenario = await session.get(Scenario, scenario_id)
    if scenario is None:
        raise ScenarioMismatchError(f"Scenario {scenario_id} not found")

    psk = await session.get(ProjectSKU, psk_channel.project_sku_id)
    # psk не может быть None, если psk_channel есть (FK constraint),
    # но проверка для type narrowing
    if psk is None or scenario.project_id != psk.project_id:
        raise ScenarioMismatchError(
            "Scenario does not belong to the project of this ProjectSKUChannel"
        )

    period = None
    if period_id is not None:
        period = await session.get(Period, period_id)
        if period is None:
            raise PeriodNotFoundError(f"Period {period_id} not found")

    return psk_channel, scenario, period


# ============================================================
# Read: 4 view modes
# ============================================================


async def _fetch_all_layers(
    session: AsyncSession,
    psk_channel_id: int,
    scenario_id: int,
) -> list[tuple[PeriodValue, Period]]:
    """Все слои всех периодов для (psk_channel, scenario)."""
    stmt = (
        select(PeriodValue, Period)
        .join(Period, Period.id == PeriodValue.period_id)
        .where(
            PeriodValue.psk_channel_id == psk_channel_id,
            PeriodValue.scenario_id == scenario_id,
        )
        .order_by(Period.period_number)
    )
    return [(pv, p) for pv, p in (await session.execute(stmt)).all()]


def _resolve_priority(
    rows: list[tuple[PeriodValue, Period]],
    *,
    exclude_actual: bool = False,
) -> list[HybridResponseItem]:
    """Группирует по period_id и применяет приоритет actual > finetuned > predict.

    Для каждого слоя берёт строку с максимальным version_id (latest).
    Если exclude_actual=True — actual-слой игнорируется (для plan_only).
    """
    # period_id -> {source_type: latest_pv}
    by_period: dict[int, dict[SourceType, PeriodValue]] = {}
    period_objs: dict[int, Period] = {}

    for pv, period in rows:
        if exclude_actual and pv.source_type == SourceType.ACTUAL:
            continue
        period_objs[period.id] = period
        layers = by_period.setdefault(period.id, {})
        existing = layers.get(pv.source_type)
        if existing is None or pv.version_id > existing.version_id:
            layers[pv.source_type] = pv

    items: list[HybridResponseItem] = []
    for period_id, layers in by_period.items():
        # Приоритет
        if SourceType.ACTUAL in layers:
            chosen = layers[SourceType.ACTUAL]
        elif SourceType.FINETUNED in layers:
            chosen = layers[SourceType.FINETUNED]
        elif SourceType.PREDICT in layers:
            chosen = layers[SourceType.PREDICT]
        else:
            continue

        period = period_objs[period_id]
        items.append(
            HybridResponseItem(
                period_id=period_id,
                period_number=period.period_number,
                source_type=chosen.source_type,
                values=chosen.values,
                is_overridden=chosen.is_overridden,
            )
        )

    items.sort(key=lambda r: r.period_number)
    return items


async def get_values_hybrid(
    session: AsyncSession,
    psk_channel_id: int,
    scenario_id: int,
) -> list[HybridResponseItem]:
    """Эффективное значение на каждый период: actual > finetuned > predict."""
    rows = await _fetch_all_layers(session, psk_channel_id, scenario_id)
    return _resolve_priority(rows)


async def get_values_fact_only(
    session: AsyncSession,
    psk_channel_id: int,
    scenario_id: int,
) -> list[HybridResponseItem]:
    """Только actual-слой. Периоды без actual не возвращаются."""
    stmt = (
        select(PeriodValue, Period)
        .join(Period, Period.id == PeriodValue.period_id)
        .where(
            PeriodValue.psk_channel_id == psk_channel_id,
            PeriodValue.scenario_id == scenario_id,
            PeriodValue.source_type == SourceType.ACTUAL,
        )
        .order_by(Period.period_number, PeriodValue.version_id.desc())
    )
    rows = list((await session.execute(stmt)).all())

    # Берём latest version для каждого period
    seen: set[int] = set()
    items: list[HybridResponseItem] = []
    for pv, period in rows:
        if period.id in seen:
            continue
        seen.add(period.id)
        items.append(
            HybridResponseItem(
                period_id=period.id,
                period_number=period.period_number,
                source_type=pv.source_type,
                values=pv.values,
                is_overridden=pv.is_overridden,
            )
        )

    items.sort(key=lambda r: r.period_number)
    return items


async def get_values_plan_only(
    session: AsyncSession,
    psk_channel_id: int,
    scenario_id: int,
) -> list[HybridResponseItem]:
    """Только plan: finetuned (latest) или predict, исключает actual."""
    rows = await _fetch_all_layers(session, psk_channel_id, scenario_id)
    return _resolve_priority(rows, exclude_actual=True)


async def get_values_compare(
    session: AsyncSession,
    psk_channel_id: int,
    scenario_id: int,
) -> list[CompareResponseItem]:
    """Все три слоя в одной структуре на каждый период."""
    rows = await _fetch_all_layers(session, psk_channel_id, scenario_id)

    # period_id -> {source_type: latest_values}
    by_period: dict[int, dict[SourceType, dict[str, Any]]] = {}
    by_period_versions: dict[int, dict[SourceType, int]] = {}
    period_objs: dict[int, Period] = {}

    for pv, period in rows:
        period_objs[period.id] = period
        layers = by_period.setdefault(period.id, {})
        versions = by_period_versions.setdefault(period.id, {})
        if pv.source_type not in versions or pv.version_id > versions[pv.source_type]:
            layers[pv.source_type] = pv.values
            versions[pv.source_type] = pv.version_id

    items: list[CompareResponseItem] = []
    for period_id, layers in by_period.items():
        period = period_objs[period_id]
        items.append(
            CompareResponseItem(
                period_id=period_id,
                period_number=period.period_number,
                predict=layers.get(SourceType.PREDICT),
                finetuned=layers.get(SourceType.FINETUNED),
                actual=layers.get(SourceType.ACTUAL),
            )
        )

    items.sort(key=lambda r: r.period_number)
    return items


# ============================================================
# Write: append-only versioning
# ============================================================


async def patch_value(
    session: AsyncSession,
    psk_channel_id: int,
    scenario_id: int,
    period_id: int,
    values: dict[str, Any],
) -> PeriodValue:
    """Создаёт новую finetuned-версию (append-only).

    version_id = MAX(version_id) WHERE source_type='finetuned' AND
                 (psk_channel, scenario, period) match  + 1.
    Если ни одной finetuned ещё нет — version_id = 1.
    """
    max_version = await session.scalar(
        select(func.max(PeriodValue.version_id)).where(
            PeriodValue.psk_channel_id == psk_channel_id,
            PeriodValue.scenario_id == scenario_id,
            PeriodValue.period_id == period_id,
            PeriodValue.source_type == SourceType.FINETUNED,
        )
    )
    new_version = (max_version or 0) + 1

    pv = PeriodValue(
        psk_channel_id=psk_channel_id,
        scenario_id=scenario_id,
        period_id=period_id,
        source_type=SourceType.FINETUNED,
        version_id=new_version,
        values=values,
        is_overridden=True,
    )
    session.add(pv)
    await session.flush()
    await session.refresh(pv)
    return pv


# ============================================================
# Reset to predict
# ============================================================


async def reset_value_to_predict(
    session: AsyncSession,
    psk_channel_id: int,
    scenario_id: int,
    period_id: int,
) -> int:
    """Удаляет ВСЕ finetuned-версии для периода.

    После этого hybrid view вернёт predict (если есть в БД) или
    пропустит этот период (если predict ещё не сгенерирован).

    Возвращает количество удалённых строк.
    """
    stmt = delete(PeriodValue).where(
        PeriodValue.psk_channel_id == psk_channel_id,
        PeriodValue.scenario_id == scenario_id,
        PeriodValue.period_id == period_id,
        PeriodValue.source_type == SourceType.FINETUNED,
    )
    result = await session.execute(stmt)
    return result.rowcount or 0
