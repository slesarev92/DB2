"""Media upload/download/delete API tests (Фаза 4.5.2).

Покрывает:
  - POST upload: успех, 401, 404 project, 400 невалидный kind/content_type/size/empty
  - GET list: пустой и с данными (DESC order)
  - GET download: bytes + headers, 404, 500 при missing-on-disk
  - DELETE: 204 + файл удалён с диска + запись из БД, 404

Файлы пишутся в `tmp_path` через monkeypatch'енный `settings.media_storage_root`
— тесты не трогают боевой /media volume.
"""
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import MediaAsset


# Минимальный PNG signature + произвольный payload. Backend не парсит
# изображение — он проверяет только Content-Type из multipart. Такой
# файл симулирует небольшое PNG и распознаётся как image/png.
FAKE_PNG_BYTES = b"\x89PNG\r\n\x1a\nFAKE_IMAGE_DATA_FOR_TEST"

VALID_PROJECT_BODY = {
    "name": "Media Test Project",
    "start_date": "2025-01-01",
    "horizon_years": 10,
    "wacc": "0.19",
    "tax_rate": "0.20",
    "wc_rate": "0.12",
    "vat_rate": "0.20",
    "currency": "RUB",
}


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def isolated_media_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Path:
    """Каждый тест media пишет в свой tmp_path, не в /media volume.

    `autouse=True` — применяется ко всем тестам этого модуля без явного
    включения в сигнатуру. Возвращает tmp_path для удобства ассертов.
    """
    monkeypatch.setattr(settings, "media_storage_root", str(tmp_path))
    # B-15: force filesystem mode in tests (no S3)
    monkeypatch.setattr(settings, "s3_endpoint", "")
    return tmp_path


@pytest_asyncio.fixture
async def project_id(auth_client: AsyncClient) -> int:
    """Создаёт проект через API и возвращает его id."""
    resp = await auth_client.post("/api/projects", json=VALID_PROJECT_BODY)
    assert resp.status_code == 201, resp.text
    return int(resp.json()["id"])


# ============================================================
# POST /api/projects/{id}/media — upload
# ============================================================


async def test_upload_media_creates_asset(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    project_id: int,
    isolated_media_root: Path,
) -> None:
    resp = await auth_client.post(
        f"/api/projects/{project_id}/media",
        files={"file": ("package.png", FAKE_PNG_BYTES, "image/png")},
        data={"kind": "package_image"},
    )
    assert resp.status_code == 201, resp.text

    body = resp.json()
    assert body["project_id"] == project_id
    assert body["kind"] == "package_image"
    assert body["filename"] == "package.png"
    assert body["content_type"] == "image/png"
    assert body["size_bytes"] == len(FAKE_PNG_BYTES)
    assert body["uploaded_by"] is not None
    # storage_path не должен exposed'иться наружу
    assert "storage_path" not in body

    # Asset существует в БД
    asset = await db_session.scalar(
        select(MediaAsset).where(MediaAsset.id == body["id"])
    )
    assert asset is not None
    assert asset.storage_path.startswith(f"{project_id}/package_image/")

    # Файл реально записан на диск
    on_disk = isolated_media_root / asset.storage_path
    assert on_disk.is_file()
    assert on_disk.read_bytes() == FAKE_PNG_BYTES


async def test_upload_media_requires_auth(client: AsyncClient) -> None:
    # Не берём project_id fixture — она использует auth_client и оставляет
    # Authorization header'ом на общем `client`. Auth проверяется до
    # существования проекта, 401 вернётся даже для несуществующего id.
    resp = await client.post(
        "/api/projects/1/media",
        files={"file": ("x.png", FAKE_PNG_BYTES, "image/png")},
        data={"kind": "other"},
    )
    assert resp.status_code == 401


async def test_upload_media_project_not_found(
    auth_client: AsyncClient,
) -> None:
    resp = await auth_client.post(
        "/api/projects/99999/media",
        files={"file": ("x.png", FAKE_PNG_BYTES, "image/png")},
        data={"kind": "other"},
    )
    assert resp.status_code == 404


async def test_upload_media_invalid_content_type(
    auth_client: AsyncClient, project_id: int
) -> None:
    resp = await auth_client.post(
        f"/api/projects/{project_id}/media",
        files={"file": ("evil.exe", b"MZ\x90\x00payload", "application/octet-stream")},
        data={"kind": "other"},
    )
    assert resp.status_code == 400
    assert "content_type" in resp.json()["detail"]


async def test_upload_media_invalid_kind(
    auth_client: AsyncClient, project_id: int
) -> None:
    resp = await auth_client.post(
        f"/api/projects/{project_id}/media",
        files={"file": ("x.png", FAKE_PNG_BYTES, "image/png")},
        data={"kind": "bogus_kind"},
    )
    assert resp.status_code == 400
    assert "kind" in resp.json()["detail"]


async def test_upload_media_empty_file(
    auth_client: AsyncClient, project_id: int
) -> None:
    resp = await auth_client.post(
        f"/api/projects/{project_id}/media",
        files={"file": ("empty.png", b"", "image/png")},
        data={"kind": "other"},
    )
    assert resp.status_code == 400
    assert "Пустой" in resp.json()["detail"]


async def test_upload_media_oversized(
    auth_client: AsyncClient,
    project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Снижаем лимит до 100 байт чтобы не гонять 10 MB в тесте
    monkeypatch.setattr(settings, "media_max_file_size", 100)

    big_payload = b"\x89PNG\r\n\x1a\n" + b"A" * 200
    resp = await auth_client.post(
        f"/api/projects/{project_id}/media",
        files={"file": ("big.png", big_payload, "image/png")},
        data={"kind": "other"},
    )
    assert resp.status_code == 400
    assert "превышает лимит" in resp.json()["detail"]


# ============================================================
# GET /api/projects/{id}/media — list
# ============================================================


async def test_list_media_empty(
    auth_client: AsyncClient, project_id: int
) -> None:
    resp = await auth_client.get(f"/api/projects/{project_id}/media")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_media_returns_uploaded(
    auth_client: AsyncClient, project_id: int
) -> None:
    # Загружаем два файла
    for i, kind in enumerate(["package_image", "concept_design"]):
        resp = await auth_client.post(
            f"/api/projects/{project_id}/media",
            files={"file": (f"file_{i}.png", FAKE_PNG_BYTES, "image/png")},
            data={"kind": kind},
        )
        assert resp.status_code == 201

    resp = await auth_client.get(f"/api/projects/{project_id}/media")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    # DESC order: последний загруженный — первым
    assert items[0]["kind"] == "concept_design"
    assert items[1]["kind"] == "package_image"


async def test_list_media_project_not_found(
    auth_client: AsyncClient,
) -> None:
    resp = await auth_client.get("/api/projects/99999/media")
    assert resp.status_code == 404


# ============================================================
# GET /api/media/{id} — download
# ============================================================


async def test_download_media_returns_bytes(
    auth_client: AsyncClient, project_id: int
) -> None:
    upload_resp = await auth_client.post(
        f"/api/projects/{project_id}/media",
        files={"file": ("pkg.png", FAKE_PNG_BYTES, "image/png")},
        data={"kind": "package_image"},
    )
    media_id = upload_resp.json()["id"]

    resp = await auth_client.get(f"/api/media/{media_id}")
    assert resp.status_code == 200
    assert resp.content == FAKE_PNG_BYTES
    assert resp.headers["content-type"] == "image/png"
    assert "pkg.png" in resp.headers["content-disposition"]
    assert resp.headers["content-length"] == str(len(FAKE_PNG_BYTES))


async def test_download_media_not_found(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/api/media/99999")
    assert resp.status_code == 404


async def test_download_media_file_missing_on_disk(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    project_id: int,
    isolated_media_root: Path,
) -> None:
    upload_resp = await auth_client.post(
        f"/api/projects/{project_id}/media",
        files={"file": ("pkg.png", FAKE_PNG_BYTES, "image/png")},
        data={"kind": "package_image"},
    )
    media_id = upload_resp.json()["id"]

    # Разрываем ссылку: удаляем файл с диска, оставляя запись в БД
    asset = await db_session.scalar(
        select(MediaAsset).where(MediaAsset.id == media_id)
    )
    assert asset is not None
    (isolated_media_root / asset.storage_path).unlink()

    resp = await auth_client.get(f"/api/media/{media_id}")
    assert resp.status_code == 500
    assert "отсутствует" in resp.json()["detail"]


# ============================================================
# DELETE /api/media/{id}
# ============================================================


async def test_delete_media_removes_record_and_file(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    project_id: int,
    isolated_media_root: Path,
) -> None:
    upload_resp = await auth_client.post(
        f"/api/projects/{project_id}/media",
        files={"file": ("pkg.png", FAKE_PNG_BYTES, "image/png")},
        data={"kind": "package_image"},
    )
    body = upload_resp.json()
    media_id = body["id"]

    asset = await db_session.scalar(
        select(MediaAsset).where(MediaAsset.id == media_id)
    )
    assert asset is not None
    on_disk = isolated_media_root / asset.storage_path
    assert on_disk.is_file()

    resp = await auth_client.delete(f"/api/media/{media_id}")
    assert resp.status_code == 204

    # Запись удалена из БД
    after = await db_session.scalar(
        select(MediaAsset).where(MediaAsset.id == media_id)
    )
    assert after is None
    # И файл тоже ушёл
    assert not on_disk.exists()


async def test_delete_media_not_found(auth_client: AsyncClient) -> None:
    resp = await auth_client.delete("/api/media/99999")
    assert resp.status_code == 404


async def test_delete_media_requires_auth(client: AsyncClient) -> None:
    # Auth dependency проверяется до lookup'а в БД — 401 для любого id
    resp = await client.delete("/api/media/1")
    assert resp.status_code == 401
