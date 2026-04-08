"""Celery task: пересчёт KPI всех сценариев проекта.

Запускается через `POST /api/projects/{id}/recalculate` (см. api/projects.py).
Возвращает `task_id` клиенту, статус опрашивается через `GET /api/tasks/{id}`.

**Архитектурное замечание — asyncpg + Celery prefork + asyncio.run:**
Celery worker — sync процесс. Каждый вызов task делает `asyncio.run()`
который создаёт **новый event loop**. asyncpg connection pool привязывает
коннекшены к loop создания. Если использовать global `async_session_maker`
из `app.db`, то после первого task коннекшены в пуле принадлежат
закрытому loop → второй task падает с
`RuntimeError: Future attached to a different loop`.

**Решение:** создавать **локальный engine с NullPool** внутри каждого
вызова task. NullPool не переиспользует коннекшены — каждый запрос
открывает свежий. Коннекшены живут только в рамках текущего asyncio.run
и корректно закрываются.

Альтернативы: shared engine с pool per-loop (сложно), sync driver
psycopg2 (теряем async). NullPool простое и надёжное.
"""
from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.services.calculation_service import (
    NoLinesError,
    ProjectNotFoundError,
    calculate_all_scenarios,
)
from app.worker import celery_app


async def _calculate_project_async(project_id: int) -> dict[str, Any]:
    """Async-обёртка вокруг calculate_all_scenarios.

    Создаёт **локальный engine** с NullPool в рамках текущего event loop,
    вызывает сервис, коммитит, закрывает engine. При исключении —
    rollback и пробрасывает дальше (Celery поймает, пометит FAILURE).
    """
    engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,
        echo=False,
    )
    session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    try:
        async with session_maker() as session:
            try:
                results_by_scenario = await calculate_all_scenarios(
                    session, project_id
                )
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    finally:
        await engine.dispose()

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
