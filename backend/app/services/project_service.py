"""Project CRUD + soft delete + auto-creation сценариев."""
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    PeriodScope,
    Project,
    Scenario,
    ScenarioResult,
    ScenarioType,
)
from app.schemas.project import ProjectCreate, ProjectUpdate


@dataclass
class ProjectListRow:
    """Строка результата list_projects: проект + KPI из расчёта (если есть).

    KPI берутся из ScenarioResult по сценарию Base, scope Y1Y10. None
    если расчёт не выполнен (LEFT JOIN не нашёл связанной строки).
    """

    project: Project
    npv_y1y10: Decimal | None
    irr_y1y10: Decimal | None
    go_no_go: bool | None


async def list_projects(session: AsyncSession) -> list[ProjectListRow]:
    """Все проекты, не помеченные удалёнными, + KPI Base/Y1Y10.

    LEFT JOIN на Scenario (Base) → ScenarioResult (Y1Y10). Если расчёт
    не выполнен — KPI поля None. Один SQL запрос вместо N+1.
    """
    stmt = (
        select(
            Project,
            ScenarioResult.npv,
            ScenarioResult.irr,
            ScenarioResult.go_no_go,
        )
        .join(
            Scenario,
            (Scenario.project_id == Project.id)
            & (Scenario.type == ScenarioType.BASE),
            isouter=True,
        )
        .join(
            ScenarioResult,
            (ScenarioResult.scenario_id == Scenario.id)
            & (ScenarioResult.period_scope == PeriodScope.Y1Y10),
            isouter=True,
        )
        .where(Project.deleted_at.is_(None))
        .order_by(Project.created_at.desc())
    )
    result = await session.execute(stmt)
    return [
        ProjectListRow(
            project=row[0],
            npv_y1y10=row[1],
            irr_y1y10=row[2],
            go_no_go=row[3],
        )
        for row in result.all()
    ]


async def get_project(
    session: AsyncSession, project_id: int
) -> Project | None:
    """Один проект по id, или None если не найден / помечен удалённым."""
    stmt = select(Project).where(
        Project.id == project_id,
        Project.deleted_at.is_(None),
    )
    return await session.scalar(stmt)


async def create_project(
    session: AsyncSession,
    data: ProjectCreate,
    created_by: int | None = None,
) -> Project:
    """Создаёт проект и автоматически — 3 сценария (Base/Cons/Aggr).

    Всё в одной транзакции (вызывающий код делает session.commit()).
    Если что-то падает на середине — rollback.
    """
    project = Project(
        **data.model_dump(),
        created_by=created_by,
    )
    session.add(project)
    await session.flush()  # получаем project.id

    for scenario_type in (
        ScenarioType.BASE,
        ScenarioType.CONSERVATIVE,
        ScenarioType.AGGRESSIVE,
    ):
        session.add(Scenario(project_id=project.id, type=scenario_type))

    await session.flush()
    await session.refresh(project)
    return project


async def update_project(
    session: AsyncSession,
    project: Project,
    data: ProjectUpdate,
) -> Project:
    """PATCH: обновляет только переданные поля (exclude_unset)."""
    update_fields = data.model_dump(exclude_unset=True)
    for key, value in update_fields.items():
        setattr(project, key, value)
    await session.flush()
    await session.refresh(project)
    return project


async def soft_delete_project(
    session: AsyncSession,
    project: Project,
) -> None:
    """Soft delete: проставляет deleted_at = now()."""
    project.deleted_at = datetime.now(timezone.utc)
    await session.flush()
