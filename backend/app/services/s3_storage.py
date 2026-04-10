"""S3/MinIO storage backend (B-15).

Тонкая обёртка над boto3 для операций с файлами в S3-совместимом
хранилище. Используется media_service когда settings.s3_endpoint задан.

При первом обращении создаёт bucket если не существует.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import BinaryIO

import boto3
from botocore.exceptions import ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_s3_client():
    """Singleton S3 client."""
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )


def _ensure_bucket() -> None:
    """Создаёт bucket если не существует (idempotent)."""
    client = _get_s3_client()
    try:
        client.head_bucket(Bucket=settings.s3_bucket)
    except ClientError:
        client.create_bucket(Bucket=settings.s3_bucket)
        logger.info("Created S3 bucket: %s", settings.s3_bucket)


def is_s3_configured() -> bool:
    """True если S3 endpoint настроен."""
    return bool(settings.s3_endpoint)


def upload_bytes(key: str, data: bytes, content_type: str) -> None:
    """Загружает bytes в S3 по ключу."""
    _ensure_bucket()
    client = _get_s3_client()
    client.put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
    )


def download_bytes(key: str) -> bytes:
    """Скачивает файл из S3 по ключу.

    Raises:
        FileNotFoundError: если объект не существует.
    """
    client = _get_s3_client()
    try:
        response = client.get_object(Bucket=settings.s3_bucket, Key=key)
        return response["Body"].read()
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "NoSuchKey":
            raise FileNotFoundError(f"S3 object not found: {key}") from exc
        raise


def delete_object(key: str) -> None:
    """Удаляет объект из S3 (idempotent — не падает если не существует)."""
    client = _get_s3_client()
    client.delete_object(Bucket=settings.s3_bucket, Key=key)
