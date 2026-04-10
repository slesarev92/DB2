"""Pydantic-схемы для MediaAsset (Фаза 4.5).

Read-only schemas — upload идёт через multipart/form-data, не через
обычный JSON body. POST endpoint принимает FastAPI `UploadFile` напрямую,
не Pydantic model.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


# Whitelist kind значений (синхронизировано с CHECK constraint
# `ck_media_assets_kind` в миграции 2e7b824682be).
MediaKind = Literal["package_image", "concept_design", "ai_reference", "ai_generated", "other"]


class MediaAssetRead(BaseModel):
    """Возвращается из POST /api/projects/{id}/media и
    GET /api/projects/{id}/media (list).

    Не содержит storage_path — это внутренний путь файловой системы,
    который не должен быть exposed в API. Frontend скачивает файл
    через GET /api/media/{id} (StreamingResponse).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    kind: MediaKind
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime
    uploaded_by: int | None = None
