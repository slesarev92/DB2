"""User CRUD и аутентификация."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models import User
from app.schemas.user import UserCreate


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    return await session.scalar(select(User).where(User.email == email))


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def create_user(session: AsyncSession, data: UserCreate) -> User:
    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        role=data.role,
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


async def authenticate_user(
    session: AsyncSession,
    email: str,
    password: str,
) -> User | None:
    """Возвращает User если пара email+password валидна, иначе None."""
    user = await get_user_by_email(session, email)
    if user is None:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
