"""SQLAlchemy базовый класс, миксины и перечисления.

Все модели наследуются от `Base`. Naming convention для constraints
важна — без неё Alembic генерирует хешированные имена, что ломает
downgrade-миграции при изменении схемы.
"""
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum as SAEnum, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Стабильные имена constraint'ов для Alembic.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    """Колонки created_at / updated_at, автоматически проставляются БД."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )


# ============================================================
# Перечисления (используются как SAEnum native_enum=False)
# ============================================================


class ScenarioType(str, PyEnum):
    """Тип сценария проекта (раздел 8.6 ТЗ)."""

    BASE = "base"
    CONSERVATIVE = "conservative"
    AGGRESSIVE = "aggressive"


class SourceType(str, PyEnum):
    """Слой данных в PeriodValue (ADR-05).

    Приоритет при отображении: actual > finetuned > predict.
    """

    PREDICT = "predict"
    FINETUNED = "finetuned"
    ACTUAL = "actual"


class PeriodType(str, PyEnum):
    """Тип периода в справочнике."""

    MONTHLY = "monthly"  # M1..M36
    ANNUAL = "annual"    # Y4..Y10


class PeriodScope(str, PyEnum):
    """Горизонт расчёта KPI (NPV Y1-3 / Y1-5 / Y1-10)."""

    Y1Y3 = "y1y3"
    Y1Y5 = "y1y5"
    Y1Y10 = "y1y10"


class UserRole(str, PyEnum):
    """Роли пользователей (для MVP — только analyst, admin — задел на Этап 2)."""

    ADMIN = "admin"
    ANALYST = "analyst"


# ============================================================
# Helpers
# ============================================================


def varchar_enum(enum_cls: type[PyEnum], name: str, length: int = 20) -> SAEnum:
    """SAEnum как VARCHAR + CHECK, хранящий .value (lowercase).

    По умолчанию SQLAlchemy с PyEnum хранит .name (UPPERCASE) — это ломает
    JSON API и SQL-запросы, потому что значения в нашем коде объявлены
    в lowercase (`MONTHLY = "monthly"`). values_callable заставляет
    использовать .value.
    """
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        length=length,
        values_callable=lambda enums: [e.value for e in enums],
    )
