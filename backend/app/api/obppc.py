"""OBPPC Price-Pack-Channel matrix API (B-13).

CRUD /api/projects/{project_id}/obppc
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_owned_project
from app.db import get_db
from app.models import User
from app.schemas.obppc import OBPPCCreate, OBPPCRead, OBPPCUpdate
from app.services import obppc_service

router = APIRouter(
    prefix="/api/projects/{project_id}/obppc",
    tags=["obppc"],
    dependencies=[Depends(require_owned_project)],
)

_not_found = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="OBPPC entry not found",
)


@router.get("", response_model=list[OBPPCRead])
async def list_obppc_endpoint(
    project_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[OBPPCRead]:
    entries = await obppc_service.list_entries(session, project_id)
    return [OBPPCRead.model_validate(e) for e in entries]


@router.post("", response_model=OBPPCRead, status_code=status.HTTP_201_CREATED)
async def create_obppc_endpoint(
    project_id: int,
    data: OBPPCCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OBPPCRead:
    entry = await obppc_service.create_entry(session, project_id, data)
    await session.commit()
    refreshed = await obppc_service.get_entry(session, entry.id)
    return OBPPCRead.model_validate(refreshed)


@router.get("/{entry_id}", response_model=OBPPCRead)
async def get_obppc_endpoint(
    project_id: int,
    entry_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OBPPCRead:
    entry = await obppc_service.get_entry(session, entry_id)
    if entry is None or entry.project_id != project_id:
        raise _not_found
    return OBPPCRead.model_validate(entry)


@router.patch("/{entry_id}", response_model=OBPPCRead)
async def update_obppc_endpoint(
    project_id: int,
    entry_id: int,
    data: OBPPCUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OBPPCRead:
    entry = await obppc_service.get_entry(session, entry_id)
    if entry is None or entry.project_id != project_id:
        raise _not_found
    updated = await obppc_service.update_entry(session, entry, data)
    await session.commit()
    refreshed = await obppc_service.get_entry(session, updated.id)
    return OBPPCRead.model_validate(refreshed)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_obppc_endpoint(
    project_id: int,
    entry_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    entry = await obppc_service.get_entry(session, entry_id)
    if entry is None or entry.project_id != project_id:
        raise _not_found
    await obppc_service.delete_entry(session, entry)
    await session.commit()
