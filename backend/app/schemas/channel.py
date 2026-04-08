"""Pydantic-схемы справочника каналов сбыта.

Channels — read-only в MVP. CRUD не нужен: каналы наполняются один раз
seed-скриптом из листа DASH MENU модели GORJI (25 каналов).
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ChannelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    universe_outlets: int | None = None
    created_at: datetime
