"""c21_project_status

C #21: добавление Project.status (lifecycle: draft/active/paused/
cancelled/completed/archived), NOT NULL default "active". Auto-backfill
existing projects в "active" — они все рабочие на момент миграции.

Revision ID: 1cf4e0350bce
Revises: cfc677c109cb
Create Date: 2026-05-16 17:58:24.323770

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "1cf4e0350bce"
down_revision: Union[str, None] = "cfc677c109cb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VALID_STATUSES = (
    "draft", "active", "paused", "cancelled", "completed", "archived",
)


def upgrade() -> None:
    # Step 1: add nullable first (existing rows have no value yet)
    op.add_column(
        "projects",
        sa.Column("status", sa.String(20), nullable=True),
    )
    # Step 2: backfill all existing projects to "active"
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE projects SET status = 'active' WHERE status IS NULL"))
    # Step 3: now make it NOT NULL with server_default
    op.alter_column("projects", "status", nullable=False, server_default="active")
    # Step 4: add CHECK constraint
    statuses_sql = ",".join(f"'{s}'" for s in VALID_STATUSES)
    op.create_check_constraint(
        "valid_project_status_value",
        "projects",
        f"status IN ({statuses_sql})",
    )


def downgrade() -> None:
    op.drop_constraint("valid_project_status_value", "projects", type_="check")
    op.drop_column("projects", "status")
