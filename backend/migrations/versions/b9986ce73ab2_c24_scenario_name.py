"""c24 scenario name

Revision ID: b9986ce73ab2
Revises: 649d7f6f7144
Create Date: 2026-05-16 11:54:05.356162

C #24 (MEMO 5.3): добавляет поле scenarios.name VARCHAR(200) NULL —
пользовательское название сценария поверх системного type (Base/
Conservative/Aggressive). UI показывает type-based fallback когда
name=NULL.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b9986ce73ab2'
down_revision: Union[str, None] = '649d7f6f7144'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scenarios",
        sa.Column("name", sa.String(length=200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scenarios", "name")
