"""Projects CRUD endpoints (защищённые JWT)."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db import get_db
from app.models import User
from app.schemas.project import (
    ProjectCreate,
    ProjectListItem,
    ProjectRead,
    ProjectUpdate,
)
from app.schemas.sensitivity import SensitivityResponse
from app.services import project_service

router = APIRouter(prefix="/api/projects", tags=["projects"])


_not_found = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Project not found",
)


@router.get("", response_model=list[ProjectListItem])
async def list_projects_endpoint(
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[ProjectListItem]:
    """Список проектов с базовыми KPI (Base scenario, Y1Y10 scope).

    KPI (npv_y1y10, irr_y1y10, go_no_go) = None пока расчёт не выполнен.
    После POST /api/projects/{id}/recalculate появляются значения из
    ScenarioResult (LEFT JOIN в project_service.list_projects).
    """
    rows = await project_service.list_projects(session)
    items: list[ProjectListItem] = []
    for row in rows:
        item = ProjectListItem.model_validate(row.project)
        item.npv_y1y10 = row.npv_y1y10
        item.irr_y1y10 = row.irr_y1y10
        item.go_no_go = row.go_no_go
        items.append(item)
    return items


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project_endpoint(
    data: ProjectCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ProjectRead:
    """Создаёт проект и одновременно — 3 сценария (Base/Cons/Aggr)."""
    project = await project_service.create_project(
        session,
        data,
        created_by=current_user.id,
    )
    await session.commit()
    await session.refresh(project)
    return ProjectRead.model_validate(project)


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project_endpoint(
    project_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ProjectRead:
    project = await project_service.get_project(session, project_id)
    if project is None:
        raise _not_found
    return ProjectRead.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project_endpoint(
    project_id: int,
    data: ProjectUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ProjectRead:
    project = await project_service.get_project(session, project_id)
    if project is None:
        raise _not_found
    updated = await project_service.update_project(session, project, data)
    await session.commit()
    await session.refresh(updated)
    return ProjectRead.model_validate(updated)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_endpoint(
    project_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Soft delete: проставляет deleted_at, физически не удаляет."""
    project = await project_service.get_project(session, project_id)
    if project is None:
        raise _not_found
    await project_service.soft_delete_project(session, project)
    await session.commit()


@router.post(
    "/{project_id}/recalculate",
    status_code=status.HTTP_202_ACCEPTED,
)
async def recalculate_project_endpoint(
    project_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str | int]:
    """Запускает Celery task на пересчёт всех 3 сценариев проекта.

    Возвращает task_id для опроса статуса через GET /api/tasks/{task_id}.
    Сам расчёт выполняется асинхронно в celery-worker, не блокирует HTTP-запрос.

    Импорт task'а внутри функции, чтобы при загрузке модуля projects.py
    не подтягивать celery_app (упрощает unit-тестирование api без worker).
    """
    project = await project_service.get_project(session, project_id)
    if project is None:
        raise _not_found

    from app.tasks.calculate_project import calculate_project_task

    async_result = calculate_project_task.delay(project_id)
    return {
        "task_id": async_result.id,
        "project_id": project_id,
        "status": "PENDING",
    }


@router.post(
    "/{project_id}/sensitivity",
    response_model=SensitivityResponse,
)
async def sensitivity_analysis_endpoint(
    project_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    scenario_id: int | None = None,
) -> SensitivityResponse:
    """Sensitivity analysis для проекта (задача 4.4 / E-09).

    Принимает project_id + опционально scenario_id (если не указан —
    используется Base сценарий проекта). Считает 4 параметра ×
    5 уровней (-20%/-10%/Base/+10%/+20%) = 20 ячеек, каждая с NPV Y1-Y10
    и Contribution Margin ratio.

    Расчёт выполняется **синхронно** в endpoint'е (не через Celery), потому
    что 20 in-memory pipeline runs занимают ~50-100ms — нет смысла
    городить async task. Backend возвращает готовый response.

    Возможные ошибки:
    - 404: project не найден или scenario не принадлежит проекту
    - 400: в проекте нет PSC (NoLinesError)
    """
    from app.services.calculation_service import (
        NoLinesError,
        ProjectNotFoundError,
    )
    from app.services.sensitivity_service import compute_sensitivity
    from sqlalchemy import select
    from app.models import Scenario, ScenarioType

    project = await project_service.get_project(session, project_id)
    if project is None:
        raise _not_found

    # Если scenario_id не указан — берём Base сценарий проекта
    if scenario_id is None:
        base = await session.scalar(
            select(Scenario).where(
                Scenario.project_id == project_id,
                Scenario.type == ScenarioType.BASE,
            )
        )
        if base is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Base scenario не найден для проекта",
            )
        scenario_id = base.id

    try:
        result = await compute_sensitivity(session, project_id, scenario_id)
    except NoLinesError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    return SensitivityResponse(**result)
