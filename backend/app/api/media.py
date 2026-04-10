"""Media upload / download endpoints (Фаза 4.5.2).

Файлы MediaAsset хранятся в файловой системе (Docker volume), в БД —
метаданные. Upload идёт через multipart/form-data, download —
StreamingResponse с правильным Content-Type.

Маршруты:
- POST   /api/projects/{project_id}/media  — upload (multipart)
- GET    /api/projects/{project_id}/media  — list для проекта
- GET    /api/media/{media_id}             — скачать файл
- DELETE /api/media/{media_id}             — удалить (файл + запись)
"""
from io import BytesIO
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db import get_db
from app.models import User
from app.schemas.media import MediaAssetRead
from app.services import media_service, project_service

# Один router на два префикса — маршруты объявляем полными путями,
# чтобы не городить два объекта (один `/api/projects/.../media`, второй
# `/api/media/...`) только ради общего tag.
router = APIRouter(tags=["media"])


_project_not_found = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Project not found",
)
_media_not_found = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Media asset not found",
)


@router.post(
    "/api/projects/{project_id}/media",
    response_model=MediaAssetRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_media_endpoint(
    project_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    file: Annotated[UploadFile, File(description="Бинарный файл (≤10 MB)")],
    kind: Annotated[
        str,
        Form(description="package_image | concept_design | other"),
    ] = "other",
) -> MediaAssetRead:
    """Upload файла в проект.

    Валидация: kind ∈ whitelist, content_type ∈ {png,jpeg,webp},
    размер ≤ 10 MB, файл не пустой. При ошибках — 400.
    """
    project = await project_service.get_project(session, project_id)
    if project is None:
        raise _project_not_found

    # UploadFile.content_type может быть None если клиент не прислал;
    # в таком случае считаем валидацию заведомо проваленной.
    content_type = file.content_type or ""
    filename = file.filename or "unnamed"

    try:
        asset = await media_service.save_uploaded_file(
            session,
            project_id=project_id,
            kind=kind,
            filename=filename,
            content_type=content_type,
            fileobj=file.file,
            uploaded_by=current_user.id,
        )
    except media_service.MediaValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    await session.commit()
    await session.refresh(asset)
    return MediaAssetRead.model_validate(asset)


@router.get(
    "/api/projects/{project_id}/media",
    response_model=list[MediaAssetRead],
)
async def list_project_media_endpoint(
    project_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[MediaAssetRead]:
    """Все MediaAsset проекта (DESC по created_at)."""
    project = await project_service.get_project(session, project_id)
    if project is None:
        raise _project_not_found

    assets = await media_service.list_media_for_project(session, project_id)
    return [MediaAssetRead.model_validate(a) for a in assets]


@router.get("/api/media/{media_id}")
async def download_media_endpoint(
    media_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    """Скачать файл. Возвращает stream с правильным Content-Type.

    Доступ без авторизации — используется в <img src> тегах на фронтенде,
    которые не передают Authorization header. RBAC-проверка принадлежности
    к проекту будет добавлена в Фазе 8 (Keycloak).
    """
    asset = await media_service.get_media_asset(session, media_id)
    if asset is None:
        raise _media_not_found

    # Проверка что родительский проект жив (не soft-deleted).
    project = await project_service.get_project(session, asset.project_id)
    if project is None:
        raise _media_not_found

    try:
        data = media_service.read_media_file(asset)
    except media_service.MediaFileMissingError as exc:
        # 500, а не 404 — БД и файловая система рассинхронизированы,
        # это операционный инцидент, не "нет такого ресурса".
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return StreamingResponse(
        BytesIO(data),
        media_type=asset.content_type,
        headers={
            "Content-Disposition": f'inline; filename="{asset.filename}"',
            "Content-Length": str(asset.size_bytes),
        },
    )


@router.delete(
    "/api/media/{media_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_media_endpoint(
    media_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Hard-delete: удаляет запись из БД и файл с диска."""
    asset = await media_service.get_media_asset(session, media_id)
    if asset is None:
        raise _media_not_found

    await media_service.delete_media_asset(session, asset)
    await session.commit()
