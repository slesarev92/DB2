"""File storage для MediaAsset (Фаза 4.5.2 + B-15 S3/MinIO).

B-15: если `settings.s3_endpoint` задан — файлы хранятся в S3/MinIO.
Иначе — filesystem (Docker named volume `media-storage`).

В обоих случаях `storage_path` в БД — относительный ключ:
    {project_id}/{kind}/{uuid}_{sanitized_filename}

Валидация:
- размер ≤ MEDIA_MAX_FILE_SIZE (10 MB)
- content_type в whitelist (image/png, image/jpeg, image/webp)
- filename очищается от path separators и управляющих символов
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.entities import MediaAsset

# Whitelist MIME-типов для upload. Ограничиваем только картинками —
# package_image и concept_design. Если понадобятся PDF-вложения,
# расширяем явно (и проверяем антивирусом на проде).
ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset(
    {"image/png", "image/jpeg", "image/webp"}
)

# Whitelist kind (совпадает с Literal в schemas/media.py и CHECK
# constraint `ck_media_assets_kind` в миграции 2e7b824682be).
ALLOWED_KINDS: frozenset[str] = frozenset(
    {"package_image", "concept_design", "ai_reference", "ai_generated", "other"}
)


# ============================================================
# Domain exceptions
# ============================================================


class MediaValidationError(Exception):
    """Файл не прошёл валидацию (размер, MIME, пустое имя)."""


class MediaNotFoundError(Exception):
    """MediaAsset с заданным id отсутствует в БД."""


class MediaFileMissingError(Exception):
    """Запись в БД есть, но файла на диске нет (битая ссылка).

    Indicates операционный инцидент — нужно либо восстановить файл,
    либо удалить запись. Не скрываем за 404.
    """


# ============================================================
# Helpers
# ============================================================


# Безопасные символы в filename: латиница, кириллица, цифры, пробел,
# точка, дефис, подчёркивание. Всё остальное заменяем на `_`.
_FILENAME_SAFE_RE = re.compile(r"[^\w\-. а-яА-ЯёЁ]", re.UNICODE)


def _sanitize_filename(raw: str) -> str:
    """Убирает path separators, control chars, keeps базовое имя файла.

    >>> _sanitize_filename("../../etc/passwd")
    'etc_passwd'
    >>> _sanitize_filename("  упаковка v2.png ")
    'упаковка v2.png'
    """
    # Обрезаем path — берём только basename.
    name = Path(raw).name.strip()
    if not name:
        return "unnamed"
    # Заменяем небезопасные символы.
    cleaned = _FILENAME_SAFE_RE.sub("_", name)
    # Ограничиваем длину до 200 символов (БД колонка 500, запас для uuid).
    return cleaned[:200] or "unnamed"


def _storage_root() -> Path:
    """Корень файлового хранилища (Path)."""
    return Path(settings.media_storage_root)


def _build_storage_path(project_id: int, kind: str, filename: str) -> Path:
    """Относительный путь `{project_id}/{kind}/{uuid}_{filename}`.

    Корень (`settings.media_storage_root`) prepend'ится в `_absolute_path`.
    В БД сохраняем именно относительный путь — при смене root-маунта не
    нужна массовая миграция записей.
    """
    safe = _sanitize_filename(filename)
    unique_name = f"{uuid.uuid4().hex}_{safe}"
    return Path(str(project_id)) / kind / unique_name


def _absolute_path(relative: str | Path) -> Path:
    """Склеивает корень с относительным путём из БД."""
    return _storage_root() / Path(relative)


# ============================================================
# Public API
# ============================================================


async def save_uploaded_file(
    session: AsyncSession,
    *,
    project_id: int,
    kind: str,
    filename: str,
    content_type: str,
    fileobj: BinaryIO,
    uploaded_by: int | None,
) -> MediaAsset:
    """Валидирует, пишет файл на диск, создаёт MediaAsset запись.

    Порядок: validate → write file → INSERT в БД. Если INSERT падает,
    удаляем уже записанный файл (компенсация, чтобы не оставалось
    сирот).

    Raises:
        MediaValidationError: неподходящий kind / content_type / размер.
    """
    if kind not in ALLOWED_KINDS:
        raise MediaValidationError(
            f"kind должен быть одним из {sorted(ALLOWED_KINDS)}, получено {kind!r}"
        )
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise MediaValidationError(
            f"content_type {content_type!r} не разрешён. "
            f"Разрешены: {sorted(ALLOWED_CONTENT_TYPES)}"
        )

    # Читаем содержимое в память. Для MVP 10 MB лимита это нормально;
    # при переходе на streaming write (S3/MinIO) заменяется на chunked.
    data = fileobj.read()
    size = len(data)
    if size == 0:
        raise MediaValidationError("Пустой файл не принимается")
    if size > settings.media_max_file_size:
        raise MediaValidationError(
            f"Файл {size} байт превышает лимит "
            f"{settings.media_max_file_size} байт"
        )

    rel_path = _build_storage_path(project_id, kind, filename)
    storage_key = str(rel_path).replace("\\", "/")

    # B-15: S3 or filesystem
    from app.services.s3_storage import is_s3_configured

    use_s3 = is_s3_configured()

    if use_s3:
        from app.services.s3_storage import delete_object, upload_bytes

        upload_bytes(storage_key, data, content_type)
    else:
        abs_path = _absolute_path(rel_path)
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(data)

    try:
        asset = MediaAsset(
            project_id=project_id,
            kind=kind,
            filename=_sanitize_filename(filename),
            content_type=content_type,
            storage_path=storage_key,
            size_bytes=size,
            uploaded_by=uploaded_by,
        )
        session.add(asset)
        await session.flush()
        await session.refresh(asset)
        return asset
    except Exception:
        # Откат файла при DB failure
        try:
            if use_s3:
                delete_object(storage_key)
            else:
                _absolute_path(rel_path).unlink(missing_ok=True)
        except OSError:
            pass
        raise


async def get_media_asset(
    session: AsyncSession, media_id: int
) -> MediaAsset | None:
    """Возвращает MediaAsset по id, или None."""
    stmt = select(MediaAsset).where(MediaAsset.id == media_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_media_for_project(
    session: AsyncSession, project_id: int
) -> list[MediaAsset]:
    """Все MediaAsset конкретного проекта, отсортированные по created_at DESC."""
    stmt = (
        select(MediaAsset)
        .where(MediaAsset.project_id == project_id)
        .order_by(MediaAsset.created_at.desc(), MediaAsset.id.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


def read_media_file(asset: MediaAsset) -> bytes:
    """Читает файл из S3 или с диска.

    Raises:
        MediaFileMissingError: запись в БД есть, но файла нет.
    """
    from app.services.s3_storage import is_s3_configured

    if is_s3_configured():
        from app.services.s3_storage import download_bytes

        try:
            return download_bytes(asset.storage_path)
        except FileNotFoundError as exc:
            raise MediaFileMissingError(
                f"S3 object {asset.storage_path} отсутствует (MediaAsset id={asset.id})"
            ) from exc
    else:
        abs_path = _absolute_path(asset.storage_path)
        if not abs_path.is_file():
            raise MediaFileMissingError(
                f"Файл {abs_path} отсутствует (MediaAsset id={asset.id})"
            )
        return abs_path.read_bytes()


async def delete_media_asset(
    session: AsyncSession, asset: MediaAsset
) -> None:
    """Hard-delete: удаляет запись из БД и файл с диска.

    Соображения hard vs soft: MediaAsset — это blob, а не финансовая
    сущность. Хранить soft-deleted файлы накладно (место на диске).
    Приоритет экономики > audit — если нужен audit, храним отдельно в
    event log, не в самом assets.

    FK ProjectSKU.package_image_id = ON DELETE SET NULL — ссылки
    разрываются без каскада.
    """
    storage_key = asset.storage_path
    await session.delete(asset)
    await session.flush()

    from app.services.s3_storage import is_s3_configured

    try:
        if is_s3_configured():
            from app.services.s3_storage import delete_object

            delete_object(storage_key)
        else:
            _absolute_path(storage_key).unlink(missing_ok=True)
    except OSError:
        pass
