"""AKB distribution plan API (B-12).

CRUD /api/projects/{project_id}/akb
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_owned_project
from app.db import get_db
from app.models import User
from app.schemas.akb import AKBCreate, AKBRead, AKBUpdate
from app.services import akb_service

router = APIRouter(
    prefix="/api/projects/{project_id}/akb",
    tags=["akb"],
    dependencies=[Depends(require_owned_project)],
)

_not_found = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="AKB entry not found",
)


@router.get("", response_model=list[AKBRead])
async def list_akb_endpoint(
    project_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[AKBRead]:
    entries = await akb_service.list_entries(session, project_id)
    return [AKBRead.model_validate(e) for e in entries]


@router.post("", response_model=AKBRead, status_code=status.HTTP_201_CREATED)
async def create_akb_endpoint(
    project_id: int,
    data: AKBCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AKBRead:
    entry = await akb_service.create_entry(session, project_id, data)
    await session.commit()
    refreshed = await akb_service.get_entry(session, entry.id)
    return AKBRead.model_validate(refreshed)


@router.get("/{akb_id}", response_model=AKBRead)
async def get_akb_endpoint(
    project_id: int,
    akb_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AKBRead:
    entry = await akb_service.get_entry(session, akb_id)
    if entry is None or entry.project_id != project_id:
        raise _not_found
    return AKBRead.model_validate(entry)


@router.patch("/{akb_id}", response_model=AKBRead)
async def update_akb_endpoint(
    project_id: int,
    akb_id: int,
    data: AKBUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AKBRead:
    entry = await akb_service.get_entry(session, akb_id)
    if entry is None or entry.project_id != project_id:
        raise _not_found
    updated = await akb_service.update_entry(session, entry, data)
    await session.commit()
    refreshed = await akb_service.get_entry(session, updated.id)
    return AKBRead.model_validate(refreshed)


@router.delete("/{akb_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_akb_endpoint(
    project_id: int,
    akb_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    entry = await akb_service.get_entry(session, akb_id)
    if entry is None or entry.project_id != project_id:
        raise _not_found
    await akb_service.delete_entry(session, entry)
    await session.commit()
