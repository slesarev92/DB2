"""c16_channel_group_source_type

C #16: добавление channel_group (8 значений) и source_type (5 значений
nullable) на таблицу channels. Backfill существующих 25 GORJI каналов
через MAPPING_RULES (см. _resolve_group).

Pre-flight для прода: SELECT DISTINCT code FROM channels — кастомные
коды (не из 25 known) попадут в OTHER. Если юзер хочет другое — UPDATE
до миграции.

Revision ID: eb59341b9034
Revises: b9986ce73ab2
Create Date: 2026-05-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "eb59341b9034"
down_revision: Union[str, None] = "b9986ce73ab2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ============================================================
# Backfill rules — единый источник истины для миграции и seed.
# ============================================================

EXACT_RULES: dict[str, str] = {
    "HM": "HM",
    "SM": "SM",
    "MM": "MM",
    "TT": "TT",
    "Vkusno I tochka": "QSR",
    "Burger king": "QSR",
    "Rostics": "QSR",
    "Do-Do_pizza": "QSR",
}
PREFIX_RULES: list[tuple[str, str]] = [
    ("E-COM_", "E_COM"),
    ("E_COM_", "E_COM"),
    ("HORECA_", "HORECA"),
]

VALID_GROUPS = ("HM", "SM", "MM", "TT", "E_COM", "HORECA", "QSR", "OTHER")
VALID_SOURCES = ("nielsen", "tsrpt", "gis2", "infoline", "custom")


def _resolve_group(code: str) -> str:
    """Маппит channel.code → channel_group. Неизвестные коды → 'OTHER'."""
    if code in EXACT_RULES:
        return EXACT_RULES[code]
    for prefix, group in PREFIX_RULES:
        if code.startswith(prefix):
            return group
    return "OTHER"


def upgrade() -> None:
    # 1. Добавляем колонки nullable — чтобы существующие rows не упали на NOT NULL.
    op.add_column(
        "channels",
        sa.Column("channel_group", sa.String(20), nullable=True),
    )
    op.add_column(
        "channels",
        sa.Column("source_type", sa.String(20), nullable=True),
    )

    # 2. Backfill channel_group по коду.
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, code FROM channels")).fetchall()
    for row_id, code in rows:
        group = _resolve_group(code)
        conn.execute(
            sa.text("UPDATE channels SET channel_group = :g WHERE id = :id"),
            {"g": group, "id": row_id},
        )
    # source_type оставляем NULL — юзер укажет вручную через UI.

    # 3. Set NOT NULL + server_default + CHECK constraints.
    op.alter_column(
        "channels",
        "channel_group",
        nullable=False,
        server_default="OTHER",
    )
    # CHECK строится из VALID_* — единый источник внутри миграции.
    # Naming convention в base.py добавит префикс ck_channels_ → итоговое
    # имя ck_channels_valid_channel_group_value (см. C #19 для прецедента).
    _groups_sql = ",".join(f"'{g}'" for g in VALID_GROUPS)
    _sources_sql = ",".join(f"'{s}'" for s in VALID_SOURCES)
    op.create_check_constraint(
        "valid_channel_group_value",
        "channels",
        f"channel_group IN ({_groups_sql})",
    )
    op.create_check_constraint(
        "valid_channel_source_type_value",
        "channels",
        f"source_type IS NULL OR source_type IN ({_sources_sql})",
    )


def downgrade() -> None:
    op.drop_constraint(
        "valid_channel_source_type_value", "channels", type_="check"
    )
    op.drop_constraint(
        "valid_channel_group_value", "channels", type_="check"
    )
    op.drop_column("channels", "source_type")
    op.drop_column("channels", "channel_group")
