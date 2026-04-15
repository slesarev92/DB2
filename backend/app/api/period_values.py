"""PeriodValues endpoints — трёхслойная модель данных.

  GET    /api/project-sku-channels/{id}/values?scenario_id&view_mode=hybrid
  PATCH  /api/project-sku-channels/{id}/values/{period_id}?scenario_id
  DELETE /api/project-sku-channels/{id}/values/{period_id}/override?scenario_id
"""
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_owned_project
from app.db import get_db
from app.models import User
from app.schemas.period_value import (
    BatchPeriodValueRequest,
    BatchPeriodValueResponse,
    PatchPeriodValueResponse,
    PeriodValueWrite,
    ResetOverrideResponse,
    ViewMode,
)
from app.services import (
    invalidation_service,
    period_value_service,
    project_service,
    project_sku_channel_service,
    project_sku_service,
)

router = APIRouter(
    prefix="/api/project-sku-channels",
    tags=["period-values"],
)


_psc_not_found = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="ProjectSKUChannel not found",
)


async def _require_psc_owned(
    session: AsyncSession, psk_channel_id: int, user: User
) -> None:
    """Load psc → psk → project, verify ownership. 404 otherwise."""
    psc = await project_sku_channel_service.get_psk_channel(
        session, psk_channel_id
    )
    if psc is None:
        raise _psc_not_found
    psk = await project_sku_service.get_project_sku(session, psc.project_sku_id)
    if psk is None or not await project_service.is_project_owned_by(
        session, psk.project_id, user
    ):
        raise _psc_not_found


# ============================================================
# Validation helper
# ============================================================


async def _validate_or_raise(
    session: AsyncSession,
    psk_channel_id: int,
    scenario_id: int,
    period_id: int | None = None,
):
    """Перевод service-исключений в HTTPException."""
    try:
        return await period_value_service.validate_context(
            session, psk_channel_id, scenario_id, period_id
        )
    except period_value_service.PSKChannelNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ProjectSKUChannel not found",
        )
    except period_value_service.PeriodNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except period_value_service.ScenarioMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


# ============================================================
# GET /values — все 4 view modes
# ============================================================


@router.get("/{psk_channel_id}/values")
async def get_values_endpoint(
    psk_channel_id: int,
    scenario_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    view_mode: ViewMode = ViewMode.HYBRID,
) -> Any:
    """Возвращает значения по периодам.

    Response shape зависит от view_mode:
      - hybrid / fact_only / plan_only → list[HybridResponseItem]
      - compare                        → list[CompareResponseItem]

    Frontend знает что ожидать по тому какой view_mode он передал.
    response_model=Any потому что union response model в FastAPI
    путает OpenAPI генерацию.
    """
    await _require_psc_owned(session, psk_channel_id, current_user)
    await _validate_or_raise(session, psk_channel_id, scenario_id)

    if view_mode == ViewMode.HYBRID:
        return await period_value_service.get_values_hybrid(
            session, psk_channel_id, scenario_id
        )
    if view_mode == ViewMode.FACT_ONLY:
        return await period_value_service.get_values_fact_only(
            session, psk_channel_id, scenario_id
        )
    if view_mode == ViewMode.PLAN_ONLY:
        return await period_value_service.get_values_plan_only(
            session, psk_channel_id, scenario_id
        )
    # COMPARE
    return await period_value_service.get_values_compare(
        session, psk_channel_id, scenario_id
    )


# ============================================================
# PATCH /values/{period_id} — fine-tune (создаёт новую версию)
# ============================================================


@router.patch(
    "/{psk_channel_id}/values/{period_id}",
    response_model=PatchPeriodValueResponse,
)
async def patch_value_endpoint(
    psk_channel_id: int,
    period_id: int,
    scenario_id: int,
    body: PeriodValueWrite,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PatchPeriodValueResponse:
    """Создаёт новую finetuned-версию.

    Append-only: каждый PATCH = новая строка с увеличенным version_id.
    Старые версии остаются как audit log.
    """
    await _require_psc_owned(session, psk_channel_id, current_user)
    await _validate_or_raise(session, psk_channel_id, scenario_id, period_id)

    pv = await period_value_service.patch_value(
        session,
        psk_channel_id=psk_channel_id,
        scenario_id=scenario_id,
        period_id=period_id,
        values=body.values,
    )
    await invalidation_service.mark_stale_by_psc(session, psk_channel_id)
    await session.commit()

    return PatchPeriodValueResponse(
        period_id=pv.period_id,
        scenario_id=pv.scenario_id,
        psk_channel_id=pv.psk_channel_id,
        source_type=pv.source_type,
        version_id=pv.version_id,
        is_overridden=pv.is_overridden,
        values=pv.values,
    )


# ============================================================
# GET /values/{period_id}/history — all versions (B-10)
# ============================================================


@router.get("/{psk_channel_id}/values/{period_id}/history")
async def get_value_history_endpoint(
    psk_channel_id: int,
    period_id: int,
    scenario_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Any:
    """Все версии PeriodValue для (psk_channel × scenario × period).

    Возвращает append-only историю: predict → finetuned (v1, v2, ...) → actual.
    """
    await _require_psc_owned(session, psk_channel_id, current_user)
    await _validate_or_raise(session, psk_channel_id, scenario_id, period_id)
    return await period_value_service.get_value_history(
        session, psk_channel_id, scenario_id, period_id
    )


# ============================================================
# PATCH /values/batch — batch fine-tune (B-17)
# ============================================================


batch_router = APIRouter(
    prefix="/api/projects/{project_id}/scenarios/{scenario_id}",
    tags=["period-values"],
    dependencies=[Depends(require_owned_project)],
)


@batch_router.patch(
    "/period-values/batch",
    response_model=BatchPeriodValueResponse,
)
async def batch_patch_values(
    project_id: int,
    scenario_id: int,
    body: BatchPeriodValueRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> BatchPeriodValueResponse:
    """Batch fine-tune нескольких period values за один HTTP вызов.

    Все изменения применяются в одной транзакции. При ошибке в любом
    элементе — откат всех.
    """
    if len(body.items) == 0:
        return BatchPeriodValueResponse(updated=0, items=[])
    if len(body.items) > 200:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Batch лимит 200 элементов",
        )

    results: list[PatchPeriodValueResponse] = []
    for item in body.items:
        await _validate_or_raise(
            session, item.psk_channel_id, scenario_id, item.period_id
        )
        pv = await period_value_service.patch_value(
            session,
            psk_channel_id=item.psk_channel_id,
            scenario_id=scenario_id,
            period_id=item.period_id,
            values=item.values,
        )
        results.append(
            PatchPeriodValueResponse(
                period_id=pv.period_id,
                scenario_id=pv.scenario_id,
                psk_channel_id=pv.psk_channel_id,
                source_type=pv.source_type,
                version_id=pv.version_id,
                is_overridden=pv.is_overridden,
                values=pv.values,
            )
        )

    # F-01: batch PATCH каналов одного проекта → одна инвалидация
    # по project_id (minimal SQL overhead).
    await invalidation_service.mark_project_stale(session, project_id)
    await session.commit()
    return BatchPeriodValueResponse(updated=len(results), items=results)


# ============================================================
# DELETE override — сброс к predict
# ============================================================


@router.delete(
    "/{psk_channel_id}/values/{period_id}/override",
    response_model=ResetOverrideResponse,
)
async def reset_override_endpoint(
    psk_channel_id: int,
    period_id: int,
    scenario_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ResetOverrideResponse:
    """Удаляет ВСЕ finetuned-версии для (psk_channel, scenario, period).

    После сброса hybrid view вернёт predict (если есть) или пропустит
    период. Идемпотентно: если finetuned не было — вернёт deleted=0
    без ошибки.
    """
    await _require_psc_owned(session, psk_channel_id, current_user)
    await _validate_or_raise(session, psk_channel_id, scenario_id, period_id)

    deleted = await period_value_service.reset_value_to_predict(
        session,
        psk_channel_id=psk_channel_id,
        scenario_id=scenario_id,
        period_id=period_id,
    )
    if deleted > 0:
        await invalidation_service.mark_stale_by_psc(session, psk_channel_id)
    await session.commit()
    return ResetOverrideResponse(deleted_versions=deleted)
