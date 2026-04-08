"""Celery-приложение.

В задаче 0.2 — минимальная заглушка, чтобы сервис celery-worker запускался
в docker-compose и подключался к Redis-брокеру.

Реальные задачи расчётного ядра (calculate_project и др.) добавляются
в задаче 2.4 (Celery pipeline orchestration).
"""
from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "digital_passport",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_send_task_events=True,
    task_send_sent_event=True,
)


@celery_app.task(name="system.ping")
def ping() -> str:
    """Liveness probe для worker. Вызывается руками для проверки связи с broker."""
    return "pong"


# Регистрация tasks. Импорт после создания celery_app, чтобы избежать
# circular import (calculate_project импортирует celery_app отсюда).
import app.tasks  # noqa: E402, F401
