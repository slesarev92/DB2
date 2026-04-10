"""Channels CRUD + региональная фильтрация (B-05).

  GET    /api/channels?region=...    ← list (optional region filter)
  GET    /api/channels/{id}          ← one
  POST   /api/channels               ← create
  PATCH  /api/channels/{id}          ← update
  DELETE /api/channels/{id}          ← delete
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db import get_db
from app.models import User
from app.schemas.channel import ChannelCreate, ChannelRead, ChannelUpdate
from app.services import channel_service

router = APIRouter(prefix="/api/channels", tags=["channels"])

_not_found = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Channel not found",
)


@router.get("", response_model=list[ChannelRead])
async def list_channels_endpoint(
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    region: str | None = Query(default=None, description="Filter by region"),
) -> list[ChannelRead]:
    channels = await channel_service.list_channels(session, region=region)
    return [ChannelRead.model_validate(c) for c in channels]


@router.get("/{channel_id}", response_model=ChannelRead)
async def get_channel_endpoint(
    channel_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ChannelRead:
    channel = await channel_service.get_channel(session, channel_id)
    if channel is None:
        raise _not_found
    return ChannelRead.model_validate(channel)


@router.post("", response_model=ChannelRead, status_code=status.HTTP_201_CREATED)
async def create_channel_endpoint(
    data: ChannelCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ChannelRead:
    ch = await channel_service.create_channel(session, data)
    await session.commit()
    return ChannelRead.model_validate(ch)


@router.patch("/{channel_id}", response_model=ChannelRead)
async def update_channel_endpoint(
    channel_id: int,
    data: ChannelUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ChannelRead:
    channel = await channel_service.get_channel(session, channel_id)
    if channel is None:
        raise _not_found
    updated = await channel_service.update_channel(session, channel, data)
    await session.commit()
    return ChannelRead.model_validate(updated)


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel_endpoint(
    channel_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    channel = await channel_service.get_channel(session, channel_id)
    if channel is None:
        raise _not_found
    await channel_service.delete_channel(session, channel)
    await session.commit()
