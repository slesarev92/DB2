"""API endpoints для импорта фактических данных из Excel (B-02).

POST /api/projects/{project_id}/actual-import?scenario_id
  — загрузка Excel с actual-данными, создание PeriodValue source_type=actual

GET /api/projects/{project_id}/actual-import/template
  — скачать пустой xlsx-шаблон для заполнения
"""
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db import get_db
from app.models import User
from app.services import invalidation_service, project_service
from app.services.actual_import_service import (
    ActualImportError,
    EmptyFileError,
    ImportResult,
    InvalidFormatError,
    generate_template,
    import_actual_data,
)

router = APIRouter(tags=["actual-import"])

_project_not_found = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Project not found",
)


class ActualImportResponse(BaseModel):
    """Результат импорта actual-данных."""

    imported: int
    skipped: int
    errors: list[str]


@router.post(
    "/api/projects/{project_id}/actual-import",
    response_model=ActualImportResponse,
)
async def upload_actual_data_endpoint(
    project_id: int,
    scenario_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    file: Annotated[UploadFile, File(description="Excel (.xlsx) с actual-данными")],
) -> ActualImportResponse:
    """Импортирует фактические данные из Excel.

    Формат: колонки Period, SKU, Channel, nd, offtake, shelf_price.
    Скачайте шаблон через GET .../actual-import/template.
    """
    project = await project_service.get_project(session, project_id, user=current_user)
    if project is None:
        raise _project_not_found

    # Validate content type
    ct = file.content_type or ""
    if not ct.startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml"
    ) and ct not in (
        "application/vnd.ms-excel",
        "application/octet-stream",
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ожидается .xlsx файл, получен content-type: {ct}",
        )

    try:
        result = await import_actual_data(
            session,
            project_id=project_id,
            scenario_id=scenario_id,
            fileobj=file.file,
        )
    except EmptyFileError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except InvalidFormatError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ActualImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if result.imported > 0:
        await invalidation_service.mark_project_stale(session, project_id)
    await session.commit()
    return ActualImportResponse(
        imported=result.imported,
        skipped=result.skipped,
        errors=result.errors,
    )


@router.get("/api/projects/{project_id}/actual-import/template")
async def download_actual_template_endpoint(
    project_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Response:
    """Скачать пустой Excel-шаблон для импорта actual-данных.

    Шаблон содержит строки для каждой комбинации
    (Period × SKU × Channel) данного проекта.
    """
    project = await project_service.get_project(session, project_id, user=current_user)
    if project is None:
        raise _project_not_found

    xlsx_bytes = await generate_template(session, project_id)

    return Response(
        content=xlsx_bytes,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"actual_template_project_{project_id}.xlsx\""
            ),
        },
    )
