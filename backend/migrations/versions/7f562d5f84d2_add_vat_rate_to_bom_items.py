"""add vat_rate to bom_items

Revision ID: 7f562d5f84d2
Revises: 6c10a01c69c0
Create Date: 2026-04-14 13:28:40.258019

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f562d5f84d2'
down_revision: Union[str, None] = '6c10a01c69c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # LOGIC-07: vat_rate на BOMItem (справочное, не влияет на расчёты).
    # server_default='0.20' чтобы существующие строки получили значение.
    op.add_column(
        'bom_items',
        sa.Column('vat_rate', sa.Numeric(precision=8, scale=6),
                  server_default='0.20', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('bom_items', 'vat_rate')
