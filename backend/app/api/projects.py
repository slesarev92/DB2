"""Projects CRUD endpoints (защищённые JWT)."""
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_owned_project
from app.core.rate_limit import limiter
from app.db import get_db
from app.models import Project, User
from app.schemas.project import (
    ProjectCreate,
    ProjectListItem,
    ProjectRead,
    ProjectUpdate,
)
from app.schemas.pnl import PnlResponse
from app.schemas.pricing import PricingSummaryResponse
from app.schemas.sensitivity import SensitivityResponse
from app.schemas.value_chain import ValueChainResponse
from app.services import invalidation_service, project_service

router = APIRouter(prefix="/api/projects", tags=["projects"])


_not_found = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Project not found",
)


def _build_export_content_disposition(
    project: Project | None, project_id: int, extension: str
) -> str:
    """Формирует Content-Disposition header с поддержкой UTF-8 имён проекта.

    HTTP headers по RFC 7230 — latin-1 only. Если имя проекта содержит
    не-ASCII (кириллица), прямое `filename="{name}"` падает с
    UnicodeEncodeError при сериализации. Решение RFC 5987:

        attachment; filename="ascii-fallback"; filename*=UTF-8''{percent}

    Современные браузеры используют `filename*`, старые — `filename`.
    """
    # ASCII fallback — сохраняем только латиницу+цифры+_
    ascii_slug = "project"
    if project is not None:
        ascii_slug = "".join(
            c if (c.isascii() and c.isalnum()) else "_" for c in project.name
        ).strip("_")[:50] or "project"

    ascii_filename = f"project_{project_id}_{ascii_slug}{extension}"

    # UTF-8 версия — полное имя через percent-encoding (RFC 5987).
    utf8_name_source = project.name if project is not None else "project"
    utf8_raw = f"project_{project_id}_{utf8_name_source}{extension}"
    utf8_encoded = quote(utf8_raw, safe="")

    return (
        f'attachment; filename="{ascii_filename}"; '
        f"filename*=UTF-8''{utf8_encoded}"
    )


@router.get("", response_model=list[ProjectListItem])
async def list_projects_endpoint(
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[ProjectListItem]:
    """Список проектов с базовыми KPI (Base scenario, Y1Y10 scope).

    KPI (npv_y1y10, irr_y1y10, go_no_go) = None пока расчёт не выполнен.
    После POST /api/projects/{id}/recalculate появляются значения из
    ScenarioResult (LEFT JOIN в project_service.list_projects).
    """
    rows = await project_service.list_projects(session, user=current_user)
    items: list[ProjectListItem] = []
    for row in rows:
        item = ProjectListItem.model_validate(row.project)
        item.npv_y1y10 = row.npv_y1y10
        item.irr_y1y10 = row.irr_y1y10
        item.go_no_go = row.go_no_go
        items.append(item)
    return items


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project_endpoint(
    data: ProjectCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ProjectRead:
    """Создаёт проект и одновременно — 3 сценария (Base/Cons/Aggr)."""
    project = await project_service.create_project(
        session,
        data,
        created_by=current_user.id,
    )
    await session.commit()
    await session.refresh(project)
    return ProjectRead.model_validate(project)


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project_endpoint(
    project_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ProjectRead:
    project = await project_service.get_project(session, project_id, user=current_user)
    if project is None:
        raise _not_found
    return ProjectRead.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project_endpoint(
    project_id: int,
    data: ProjectUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ProjectRead:
    project = await project_service.get_project(session, project_id, user=current_user)
    if project is None:
        raise _not_found
    updated = await project_service.update_project(session, project, data)
    # F-01: project-level fields (wacc/tax_rate/wc_rate/vat_rate/cm_threshold)
    # являются pipeline input — помечаем результаты устаревшими.
    await invalidation_service.mark_project_stale(session, project_id)
    await session.commit()
    await session.refresh(updated)
    return ProjectRead.model_validate(updated)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_endpoint(
    project_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Soft delete: проставляет deleted_at, физически не удаляет."""
    project = await project_service.get_project(session, project_id, user=current_user)
    if project is None:
        raise _not_found
    await project_service.soft_delete_project(session, project)
    await session.commit()


@router.post(
    "/{project_id}/recalculate",
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("10/minute")
async def recalculate_project_endpoint(
    request: Request,  # noqa: ARG001 — slowapi key_func читает request.client
    project_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str | int]:
    """Запускает Celery task на пересчёт всех 3 сценариев проекта.

    Возвращает task_id для опроса статуса через GET /api/tasks/{task_id}.
    Сам расчёт выполняется асинхронно в celery-worker, не блокирует HTTP-запрос.

    Импорт task'а внутри функции, чтобы при загрузке модуля projects.py
    не подтягивать celery_app (упрощает unit-тестирование api без worker).
    """
    project = await project_service.get_project(session, project_id, user=current_user)
    if project is None:
        raise _not_found

    from app.tasks.calculate_project import calculate_project_task

    async_result = calculate_project_task.delay(project_id)
    return {
        "task_id": async_result.id,
        "project_id": project_id,
        "status": "PENDING",
    }


@router.post(
    "/{project_id}/sensitivity",
    response_model=SensitivityResponse,
)
async def sensitivity_analysis_endpoint(
    project_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    scenario_id: int | None = None,
    scope: str = "y1y10",
) -> SensitivityResponse:
    """Sensitivity analysis для проекта (задача 4.4 / E-09).

    Принимает project_id + опционально scenario_id (если не указан —
    используется Base сценарий проекта). Считает 4 параметра ×
    5 уровней (-20%/-10%/Base/+10%/+20%) = 20 ячеек, каждая с NPV Y1-Y10
    и Contribution Margin ratio.

    Расчёт выполняется **синхронно** в endpoint'е (не через Celery), потому
    что 20 in-memory pipeline runs занимают ~50-100ms — нет смысла
    городить async task. Backend возвращает готовый response.

    Возможные ошибки:
    - 404: project не найден или scenario не принадлежит проекту
    - 400: в проекте нет PSC (NoLinesError)
    """
    from app.services.calculation_service import (
        NoLinesError,
        ProjectNotFoundError,
    )
    from app.services.sensitivity_service import compute_sensitivity
    from sqlalchemy import select
    from app.models import Scenario, ScenarioType

    project = await project_service.get_project(session, project_id, user=current_user)
    if project is None:
        raise _not_found

    # Если scenario_id не указан — берём Base сценарий проекта
    if scenario_id is None:
        base = await session.scalar(
            select(Scenario).where(
                Scenario.project_id == project_id,
                Scenario.type == ScenarioType.BASE,
            )
        )
        if base is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Base scenario не найден для проекта",
            )
        scenario_id = base.id

    try:
        result = await compute_sensitivity(session, project_id, scenario_id, scope=scope)
    except NoLinesError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    return SensitivityResponse(**result)


@router.get(
    "/{project_id}/pricing-summary",
    response_model=PricingSummaryResponse,
    summary="Pricing summary: shelf / ex-factory / COGS по SKU × канал",
)
async def pricing_summary_endpoint(
    project_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PricingSummaryResponse:
    """Сводная ценовая таблица (Phase 8.1)."""
    from app.services.pricing_service import build_pricing_summary

    project = await project_service.get_project(session, project_id, user=current_user)
    if project is None:
        raise _not_found

    return await build_pricing_summary(session, project)


@router.get(
    "/{project_id}/value-chain",
    response_model=ValueChainResponse,
    summary="Value Chain: per-unit waterfall экономика по SKU × канал",
)
async def value_chain_endpoint(
    project_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ValueChainResponse:
    """Стакан / Value Chain (Phase 8.2)."""
    from app.services.pricing_service import build_value_chain

    project = await project_service.get_project(session, project_id, user=current_user)
    if project is None:
        raise _not_found

    return await build_value_chain(session, project)


@router.get(
    "/{project_id}/pnl",
    response_model=PnlResponse,
    summary="P&L per-period: NR/COGS/GP/CM/EBITDA/FCF для base scenario",
)
async def pnl_endpoint(
    project_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PnlResponse:
    """Per-period P&L из pipeline (Phase 8.5).

    Запускает pipeline для Base сценария и возвращает 43 периода
    с P&L метриками. Frontend группирует по месяцам/кварталам/годам.
    """
    from sqlalchemy import select

    from app.engine.pipeline import run_project_pipeline
    from app.models import Scenario, ScenarioType
    from app.schemas.pnl import PnlPeriod
    from app.services.calculation_service import (
        _load_period_catalog,
        _load_project_financial_plan,
        build_line_inputs,
    )

    project = await project_service.get_project(session, project_id, user=current_user)
    if project is None:
        raise _not_found

    # Find base scenario

    base = (
        await session.scalars(
            select(Scenario).where(
                Scenario.project_id == project_id,
                Scenario.type == ScenarioType.BASE,
            )
        )
    ).first()
    if base is None:
        raise HTTPException(status_code=404, detail="Base scenario not found")

    try:
        line_inputs = await build_line_inputs(session, project_id, base.id)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Нет SKU/каналов для расчёта P&L",
        )

    sorted_periods, _ = await _load_period_catalog(session)
    capex, opex = await _load_project_financial_plan(
        session, project_id, sorted_periods
    )
    agg = run_project_pipeline(
        line_inputs, project_capex=capex, project_opex=opex
    )

    n = agg.input.period_count
    periods: list[PnlPeriod] = []
    for t in range(n):
        is_monthly = agg.input.period_is_monthly[t]
        month_num = agg.input.period_month_num[t]
        model_year = agg.input.period_model_year[t]
        quarter = ((month_num - 1) // 3 + 1) if month_num is not None else None

        if is_monthly:
            # M1..M36 — sequential number within monthly range
            label = f"M{t + 1}"
            ptype = "monthly"
        else:
            label = f"Y{model_year}"
            ptype = "annual"

        periods.append(
            PnlPeriod(
                period_label=label,
                period_type=ptype,
                model_year=model_year,
                month_num=month_num,
                quarter=quarter,
                volume_units=agg.volume_units[t],
                volume_liters=agg.volume_liters[t],
                net_revenue=agg.net_revenue[t],
                cogs_material=agg.cogs_material[t] if agg.cogs_material else 0.0,
                cogs_production=agg.cogs_production[t] if agg.cogs_production else 0.0,
                cogs_copacking=agg.cogs_copacking[t] if agg.cogs_copacking else 0.0,
                cogs_total=agg.cogs_total[t],
                gross_profit=agg.gross_profit[t],
                logistics_cost=agg.logistics_cost[t],
                contribution=agg.contribution[t],
                ca_m_cost=agg.ca_m_cost[t],
                marketing_cost=agg.marketing_cost[t],
                ebitda=agg.ebitda[t],
                working_capital=agg.working_capital[t] if agg.working_capital else 0.0,
                delta_working_capital=agg.delta_working_capital[t] if agg.delta_working_capital else 0.0,
                tax=agg.tax[t] if agg.tax else 0.0,
                operating_cash_flow=agg.operating_cash_flow[t] if agg.operating_cash_flow else 0.0,
                investing_cash_flow=agg.investing_cash_flow[t] if agg.investing_cash_flow else 0.0,
                free_cash_flow=agg.free_cash_flow[t],
            )
        )

    return PnlResponse(scenario_type="base", periods=periods)


@router.get(
    "/{project_id}/export/xlsx",
    responses={
        200: {
            "content": {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}
            },
            "description": "XLSX файл с тремя листами: Вводные / PnL / KPI",
        },
        404: {"description": "Project не найден"},
    },
)
@limiter.limit("20/minute")
async def export_project_xlsx_endpoint(
    request: Request,  # noqa: ARG001 — slowapi key_func читает request.client
    project_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> StreamingResponse:
    """Экспорт проекта в XLSX (задача 5.1, F-08).

    Возвращает .xlsx файл с тремя листами:
    - **Вводные**: параметры проекта, SKU+BOM, каналы, financial plan
    - **PnL по периодам**: per-period финансовые показатели Base сценария
      (volume, NR, COGS, GP, CM, EBITDA, WC, Tax, OCF, FCF) + годовые
      агрегаты Y1..Y10
    - **KPI**: NPV/IRR/ROI/Payback × 3 сценария × 3 scope (Y1Y3/Y1Y5/Y1Y10)

    Если расчёт ещё не выполнен (нет ScenarioResult) — KPI лист содержит
    "—" в ячейках, PnL лист пустой с пометкой. Чтобы получить полный
    экспорт — сначала POST /api/projects/{id}/recalculate.

    Filename: `project_{id}_{name_slug}.xlsx`. Stream без temp files.
    """
    from io import BytesIO
    from app.export.excel_exporter import (
        ProjectNotFoundForExport,
        generate_project_xlsx,
    )

    try:
        xlsx_bytes = await generate_project_xlsx(session, project_id)
    except ProjectNotFoundForExport:
        raise _not_found

    project = await project_service.get_project(session, project_id, user=current_user)
    content_disposition = _build_export_content_disposition(
        project, project_id, ".xlsx"
    )

    return StreamingResponse(
        BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": content_disposition,
            "Content-Length": str(len(xlsx_bytes)),
        },
    )


@router.get(
    "/{project_id}/export/pptx",
    responses={
        200: {
            "content": {
                "application/vnd.openxmlformats-officedocument.presentationml.presentation": {}
            },
            "description": "PPTX файл с 13 слайдами паспорта проекта",
        },
        404: {"description": "Project не найден"},
    },
)
@limiter.limit("20/minute")
async def export_project_pptx_endpoint(
    request: Request,  # noqa: ARG001 — slowapi key_func читает request.client
    project_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> StreamingResponse:
    """Экспорт проекта в PPTX (задача 5.2, F-09).

    13 слайдов: титул / общая / концепция / технология / валидация /
    продуктовый микс (с package images) / макро-факторы / KPI /
    PnL по годам / стакан+fin plan / риски+функции / roadmap+согласующие /
    executive summary.

    Включает content fields из Фазы 4.5 + расчётные KPI/PnL (если
    `POST /api/projects/{id}/recalculate` был выполнен). Если content
    поля или расчёт отсутствуют — секции показывают «—» / placeholder.

    Filename: `project_{id}_{name_slug}.pptx`. Stream без temp files.
    """
    from io import BytesIO
    from app.export.excel_exporter import ProjectNotFoundForExport
    from app.export.ppt_exporter import generate_project_pptx

    try:
        pptx_bytes = await generate_project_pptx(session, project_id)
    except ProjectNotFoundForExport:
        raise _not_found

    project = await project_service.get_project(session, project_id, user=current_user)
    content_disposition = _build_export_content_disposition(
        project, project_id, ".pptx"
    )

    return StreamingResponse(
        BytesIO(pptx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={
            "Content-Disposition": content_disposition,
            "Content-Length": str(len(pptx_bytes)),
        },
    )


@router.get(
    "/{project_id}/export/pdf",
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "PDF паспорт проекта (A4, многостраничный)",
        },
        404: {"description": "Project не найден"},
    },
)
@limiter.limit("20/minute")
async def export_project_pdf_endpoint(
    request: Request,  # noqa: ARG001 — slowapi key_func читает request.client
    project_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> StreamingResponse:
    """Экспорт проекта в PDF (задача 5.3, F-10).

    HTML-шаблон (Jinja2) → WeasyPrint → PDF A4. 12 секций: титул,
    общая информация, концепция, технология, валидация, продуктовый
    микс (с package images), макро-факторы, KPI, PnL по годам, стакан
    себестоимости + fin plan, риски + готовность функций, дорожная
    карта + согласующие, executive summary.

    Filename — RFC 5987 Content-Disposition (поддержка кириллицы).
    """
    from io import BytesIO
    from app.export.excel_exporter import ProjectNotFoundForExport
    from app.export.pdf_exporter import generate_project_pdf

    try:
        pdf_bytes = await generate_project_pdf(session, project_id)
    except ProjectNotFoundForExport:
        raise _not_found

    project = await project_service.get_project(session, project_id, user=current_user)
    content_disposition = _build_export_content_disposition(
        project, project_id, ".pdf"
    )

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": content_disposition,
            "Content-Length": str(len(pdf_bytes)),
        },
    )
