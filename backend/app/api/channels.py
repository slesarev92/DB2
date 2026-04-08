"""Channels справочник — read-only API.

В MVP каналы не редактируются через UI (вариант A одобрен). Только GET.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db import get_db
from app.models import User
from app.schemas.channel import ChannelRead
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
) -> list[ChannelRead]:
    channels = await channel_service.list_channels(session)
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
