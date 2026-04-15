"""add tax_loss_carryforward to Project (4.1)

Revision ID: d894b52f645b
Revises: c30b0e3ac9bb
Create Date: 2026-04-15 19:30:01.718298

4.1 engine audit — добавляет `Project.tax_loss_carryforward` (default False).
Когда True, расчётное ядро применяет перенос убытков прошлых лет
(ст.283 НК РФ, cap 50% прибыли) в `s10_discount.py`.

Default False сохраняет Excel-compat поведение для существующих проектов —
NPV/IRR/ROI baseline не меняется. См. D-24 в TZ_VS_EXCEL_DISCREPANCIES.md.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd894b52f645b'
down_revision: Union[str, None] = 'c30b0e3ac9bb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'projects',
        sa.Column(
            'tax_loss_carryforward',
            sa.Boolean(),
            server_default=sa.text('false'),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column('projects', 'tax_loss_carryforward')
