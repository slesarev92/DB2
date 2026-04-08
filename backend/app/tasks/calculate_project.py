"""Celery task: пересчёт KPI всех сценариев проекта.

Запускается через `POST /api/projects/{id}/recalculate` (см. api/projects.py).
Возвращает `task_id` клиенту, статус опрашивается через `GET /api/tasks/{id}`.

Архитектура async ↔ Celery:
- Celery worker — sync процесс, не понимает asyncio из коробки.
- Расчётный сервис (`services/calculation_service.py`) использует
  AsyncSession (asyncpg). Поэтому в task'е оборачиваем async-вызов
  через `asyncio.run` — каждая task получает свой event loop.
- Сессия БД создаётся внутри async-функции через `async_session_maker`
  (тот же engine что и FastAPI dependency).
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.db import async_session_maker
from app.services.calculation_service import (
    NoLinesError,
    ProjectNotFoundError,
    calculate_all_scenarios,
)
from app.worker import celery_app


async def _calculate_project_async(project_id: int) -> dict[str, Any]:
    """Async-обёртка вокруг calculate_all_scenarios.

    Открывает AsyncSession, вызывает сервис, коммитит транзакцию. При
    исключении делает rollback и пробрасывает дальше — Celery поймает
    и пометит task FAILED с traceback в result backend.
    """
    async with async_session_maker() as session:
        try:
            results_by_scenario = await calculate_all_scenarios(session, project_id)
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    # Сериализуемый ответ для Celery result backend (только примитивы)
    return {
        "project_id": project_id,
        "scenarios_calculated": len(results_by_scenario),
        "scenario_ids": list(results_by_scenario.keys()),
        "total_results": sum(len(rs) for rs in results_by_scenario.values()),
    }


@celery_app.task(
    name="calculations.calculate_project",
    bind=True,
    # autoretry — НЕТ. Если упало — это либо bug в коде, либо bad data.
    # Тихий retry скроет проблему.
)
def calculate_project_task(self, project_id: int) -> dict[str, Any]:
    """Celery entrypoint. Конвертирует ProjectNotFoundError/NoLinesError
    в человекочитаемые ошибки в task result, остальные исключения
    пробрасывает (Celery пометит task FAILED).
    """
    try:
        return asyncio.run(_calculate_project_async(project_id))
    except (ProjectNotFoundError, NoLinesError) as exc:
        # Эти ошибки — bad request, не баг. Возвращаем как failed result
        # с понятным сообщением. Celery state будет SUCCESS (task не упал),
        # но результат содержит error-поле.
        return {
            "project_id": project_id,
            "error": type(exc).__name__,
            "message": str(exc) or type(exc).__name__,
        }
