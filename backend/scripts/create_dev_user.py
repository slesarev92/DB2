"""Создаёт dev-юзера для frontend разработки.

ВНИМАНИЕ: только для dev-окружения. В prod пользователи создаются
через Keycloak (см. ADR-08) или административные процедуры.

Использование:
    docker compose -f infra/docker-compose.dev.yml exec backend \\
        python -m scripts.create_dev_user

Идемпотентно: повторный запуск не дублирует. Если user с email
admin@example.com уже есть — обновляет пароль на дефолтный.

Логин/пароль: admin@example.com / admin123
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.security import hash_password
from app.db import async_session_maker
from app.models import User, UserRole

DEV_EMAIL = "admin@example.com"
DEV_PASSWORD = "admin123"


async def main() -> None:
    async with async_session_maker() as session:
        existing = await session.scalar(
            select(User).where(User.email == DEV_EMAIL)
        )
        if existing is not None:
            existing.hashed_password = hash_password(DEV_PASSWORD)
            await session.commit()
            print(f"Updated password for existing user: {DEV_EMAIL}")
        else:
            user = User(
                email=DEV_EMAIL,
                hashed_password=hash_password(DEV_PASSWORD),
                role=UserRole.ANALYST,
            )
            session.add(user)
            await session.commit()
            print(f"Created dev user: {DEV_EMAIL} / {DEV_PASSWORD}")

        print(f"Login at: http://localhost:3000/login")


if __name__ == "__main__":
    asyncio.run(main())
