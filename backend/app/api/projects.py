"""Projects CRUD endpoints (защищённые JWT)."""
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db import get_db
from app.models import Project, User
from app.schemas.project import (
    ProjectCreate,
    ProjectListItem,
    ProjectRead,
    ProjectUpdate,
)
from app.schemas.pricing import PricingSummaryResponse
from app.schemas.sensitivity import SensitivityResponse
from app.services import project_service

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
    rows = await project_service.list_projects(session)
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
    project = await project_service.get_project(session, project_id)
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
    project = await project_service.get_project(session, project_id)
    if project is None:
        raise _not_found
    updated = await project_service.update_project(session, project, data)
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
    project = await project_service.get_project(session, project_id)
    if project is None:
        raise _not_found
    await project_service.soft_delete_project(session, project)
    await session.commit()


@router.post(
    "/{project_id}/recalculate",
    status_code=status.HTTP_202_ACCEPTED,
)
async def recalculate_project_endpoint(
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
    project = await project_service.get_project(session, project_id)
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

    project = await project_service.get_project(session, project_id)
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
        result = await compute_sensitivity(session, project_id, scenario_id)
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
    """Сводная ценовая таблица (Phase 8.1).

    Для каждого SKU × Channel:
    - shelf_price_reg, shelf_price_promo, shelf_price_weighted
    - ex_factory (с VAT-коррекцией / (1+VAT))
    - channel_margin, promo_discount, promo_share
    - COGS per unit из BOM
    """
    from decimal import Decimal

    from sqlalchemy.orm import selectinload as sil

    from app.models import BOMItem, ProjectSKU, ProjectSKUChannel
    from app.schemas.pricing import PricingCell, SKUPricingColumn

    project = await project_service.get_project(session, project_id)
    if project is None:
        raise _not_found

    vat_rate = project.vat_rate

    # Load all PSKs with SKU + channels
    from sqlalchemy import select

    psk_stmt = (
        select(ProjectSKU)
        .where(ProjectSKU.project_id == project_id, ProjectSKU.include.is_(True))
        .options(sil(ProjectSKU.sku))
        .order_by(ProjectSKU.id)
    )
    psks = (await session.scalars(psk_stmt)).all()

    skus: list[SKUPricingColumn] = []
    for psk in psks:
        # COGS per unit from BOM
        boms = (
            await session.scalars(
                select(BOMItem).where(BOMItem.project_sku_id == psk.id)
            )
        ).all()
        cogs = Decimal("0")
        for b in boms:
            cogs += b.quantity_per_unit * b.price_per_unit * (Decimal("1") + b.loss_pct)

        # Channels
        psc_stmt = (
            select(ProjectSKUChannel)
            .where(ProjectSKUChannel.project_sku_id == psk.id)
            .options(sil(ProjectSKUChannel.channel))
            .order_by(ProjectSKUChannel.id)
        )
        pscs = (await session.scalars(psc_stmt)).all()

        channels: list[PricingCell] = []
        for psc in pscs:
            sp_reg = psc.shelf_price_reg
            sp_promo = sp_reg * (Decimal("1") - psc.promo_discount)
            sp_weighted = (
                sp_reg * (Decimal("1") - psc.promo_share)
                + sp_promo * psc.promo_share
            )
            ex_factory = (
                sp_weighted
                / (Decimal("1") + vat_rate)
                * (Decimal("1") - psc.channel_margin)
            )
            channels.append(
                PricingCell(
                    channel_code=psc.channel.code,
                    channel_name=psc.channel.name,
                    shelf_price_reg=sp_reg,
                    shelf_price_promo=sp_promo,
                    shelf_price_weighted=sp_weighted,
                    ex_factory=ex_factory,
                    channel_margin=psc.channel_margin,
                    promo_discount=psc.promo_discount,
                    promo_share=psc.promo_share,
                )
            )

        skus.append(
            SKUPricingColumn(
                sku_brand=psk.sku.brand,
                sku_name=psk.sku.name,
                sku_format=psk.sku.format,
                sku_volume_l=psk.sku.volume_l,
                cogs_per_unit=cogs,
                channels=channels,
            )
        )

    return PricingSummaryResponse(vat_rate=vat_rate, skus=skus)


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
async def export_project_xlsx_endpoint(
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

    project = await project_service.get_project(session, project_id)
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
async def export_project_pptx_endpoint(
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

    project = await project_service.get_project(session, project_id)
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
async def export_project_pdf_endpoint(
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

    project = await project_service.get_project(session, project_id)
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
