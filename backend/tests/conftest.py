"""Pytest fixtures для интеграционных тестов backend.

Стратегия (выбрана пользователем для задачи 1.1):
  - Тесты идут против реального postgres из docker compose, не против SQLite.
    JSONB и PG enums критичны для расчётного ядра, SQLite их не поддержит.
  - Отдельная тестовая БД `dbpassport_test` создаётся session-fixture'ом
    через admin connection к default БД `postgres`.
  - Schema создаётся через `Base.metadata.create_all` (не Alembic — быстрее
    и не требует sync psycopg в test path).
  - Изоляция тестов: connection + transaction + rollback на каждый тест.
    Все вставки текущего теста откатываются → полная независимость.
"""
from typing import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.db import get_db
from app.main import app
from app.models import Base, User

TEST_DB_NAME = "dbpassport_test"

# B-15: disable S3 in all tests — use filesystem fallback.
# Cannot use monkeypatch in session fixture (function scope only),
# so we patch settings directly at import time.
settings.s3_endpoint = ""


def _replace_db_name(url: str, new_db: str) -> str:
    """Меняет имя БД в DSN-строке (последний сегмент после '/')."""
    return url.rsplit("/", 1)[0] + "/" + new_db


@pytest_asyncio.fixture(scope="session")
async def test_db_url() -> AsyncGenerator[str, None]:
    """Создаёт чистую тестовую БД и возвращает её URL.

    Подключается к default БД `postgres` под тем же пользователем
    (POSTGRES_USER в compose — суперюзер), форс-дисконнектит активные
    сессии к тестовой БД, дропает её и создаёт заново.
    """
    admin_url = _replace_db_name(settings.database_url, "postgres")
    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")

    async with admin_engine.connect() as conn:
        await conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{TEST_DB_NAME}' AND pid <> pg_backend_pid()"
            )
        )
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}"'))
        await conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))

    await admin_engine.dispose()

    yield _replace_db_name(settings.database_url, TEST_DB_NAME)


@pytest_asyncio.fixture(scope="session")
async def test_engine(test_db_url: str) -> AsyncGenerator[AsyncEngine, None]:
    """Engine для тестовой БД с применённой схемой и засеянными справочниками.

    После `Base.metadata.create_all` сразу заполняем справочные таблицы
    (Channel, RefInflation, RefSeasonality, Period) теми же данными, что
    использует prod (см. scripts/seed_reference_data.py). Это коммитится
    один раз на pytest-сессию — каждый тест видит эти данные через свою
    транзакцию (изменения теста откатываются в `db_session` fixture, но
    коммиченный seed остаётся).

    Зачем: для read-only ресурсов (Channels — задача 1.4) и для будущего
    (PeriodValues — задача 1.5 нужны 43 периода).
    """
    engine = create_async_engine(test_db_url, poolclass=NullPool)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed справочников через тестовый engine (не через app.db, который
    # привязан к prod DATABASE_URL)
    from app.models import Channel, Period, RefInflation, RefSeasonality
    from scripts.seed_reference_data import (
        CHANNELS_DATA,
        INFLATION_PROFILES,
        SEASONALITY_PROFILES,
        generate_periods,
    )

    test_session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with test_session_maker() as session:
        for ch in CHANNELS_DATA:
            session.add(Channel(**ch))
        for prof in INFLATION_PROFILES:
            session.add(RefInflation(**prof))
        for prof in SEASONALITY_PROFILES:
            session.add(RefSeasonality(**prof))
        for p in generate_periods():
            session.add(Period(**p))
        await session.commit()

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(
    test_engine: AsyncEngine,
) -> AsyncGenerator[AsyncSession, None]:
    """Изолированная транзакция на тест.

    Каждый тест получает свежую сессию, привязанную к открытой транзакции.
    После теста транзакция откатывается — БД возвращается к исходному
    состоянию (пустые таблицы).
    """
    connection = await test_engine.connect()
    transaction = await connection.begin()

    session_maker = async_sessionmaker(
        bind=connection,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    session = session_maker()

    try:
        yield session
    finally:
        await session.close()
        await transaction.rollback()
        await connection.close()


@pytest_asyncio.fixture
async def client(
    db_session: AsyncSession,
) -> AsyncGenerator[AsyncClient, None]:
    """HTTPX async client с подменой dependency `get_db` на тестовую сессию.

    Endpoint'ы FastAPI получат ту же сессию что и тест → все запросы
    видят данные, созданные через db_session.add/flush.
    """

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Тестовый пользователь для защищённых endpoint'ов.

    Role=ADMIN — смотрит любые проекты (для тестов бизнес-логики,
    которые создают projects напрямую через session без `created_by`).
    Для specific security/IDOR тестов использовать отдельный ANALYST
    fixture (см. tests/api/test_security_idor.py).
    """
    from app.models import UserRole
    user = User(
        email="testuser@example.com",
        hashed_password=hash_password("testpass123"),
        role=UserRole.ADMIN,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient, test_user: User) -> AsyncClient:
    """HTTPX клиент с Authorization Bearer для test_user."""
    token = create_access_token(test_user.id)
    client.headers["Authorization"] = f"Bearer {token}"
    return client
