"""Async SQLAlchemy engine и session factory.

Используется приложением (FastAPI handlers) и сервисами. Alembic-миграции
ходят через отдельный sync-driver (psycopg) — см. backend/migrations/env.py.
"""
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    echo=False,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: открывает AsyncSession на запрос."""
    async with async_session_maker() as session:
        yield session
