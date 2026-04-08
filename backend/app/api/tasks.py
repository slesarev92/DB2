"""Tasks status endpoints — опрос Celery result backend.

Используется фронтендом после `POST /api/projects/{id}/recalculate` для
polling'а статуса до завершения. Возвращает 4 возможных статуса:

- `PENDING`  — task ещё не подхвачен worker'ом (или уже забыт result backend)
- `STARTED`  — worker обрабатывает (если включён task_track_started)
- `SUCCESS`  — завершён, в `result` лежит JSON от Celery task
- `FAILURE`  — упал, в `error` сообщение исключения

Эндпоинт защищён JWT — опрашивать чужие task ID нельзя по дизайну,
но Celery sам не привязывает task к user. Защита через auth — минимум.
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models import User

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/{task_id}")
async def get_task_status_endpoint(
    task_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Возвращает статус Celery task по id.

    Импорт celery_app внутри функции — модуль `app.api.tasks` не должен
    зависеть от worker'а на import-time (для тестов FastAPI без брокера).
    """
    from celery.result import AsyncResult

    from app.worker import celery_app

    async_result = AsyncResult(task_id, app=celery_app)
    state = async_result.state  # PENDING / STARTED / SUCCESS / FAILURE

    response: dict[str, Any] = {
        "task_id": task_id,
        "status": state,
    }

    if state == "SUCCESS":
        response["result"] = async_result.result
    elif state == "FAILURE":
        # async_result.result содержит само исключение при FAILURE
        response["error"] = str(async_result.result)
        response["traceback"] = async_result.traceback

    return response
