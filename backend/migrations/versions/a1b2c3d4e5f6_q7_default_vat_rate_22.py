"""Q7 default vat_rate 0.22 (РФ с 01.01.2026)

Меняет server_default колонки projects.vat_rate с 0.20 на 0.22 для
новых проектов. Существующие проекты НЕ затрагиваем — заказчик может
вручную поднять ставку через UI на странице проекта.

См. docs/CLIENT_FEEDBACK_v2_DECISIONS.md Q7.

Revision ID: a1b2c3d4e5f6
Revises: 3e5dcbc50271
Create Date: 2026-05-15 00:00:00.000000
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "3e5dcbc50271"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "projects",
        "vat_rate",
        server_default="0.220000",
    )


def downgrade() -> None:
    op.alter_column(
        "projects",
        "vat_rate",
        server_default="0.200000",
    )
