"""add scenario deltas price/cogs/logistics (4.5)

Revision ID: 3e5dcbc50271
Revises: d894b52f645b
Create Date: 2026-04-15 19:38:09.441981

4.5 engine audit — добавляет 3 новых project-wide delta на Scenario:
- delta_shelf_price: мультипликативный shift цены полки (0.10 = +10%)
- delta_bom_cost:    shift BOM / COGS materials (0.15 = подорожание сырья 15%)
- delta_logistics:   shift logistics_cost_per_kg

Применяются во всех psk_channel сценария (проект-wide, не per-channel,
в отличие от существующих delta_nd/delta_offtake). Default 0 сохраняет
baseline поведение для Base + уже-существующих Conservative/Aggressive.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3e5dcbc50271'
down_revision: Union[str, None] = 'd894b52f645b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'scenarios',
        sa.Column(
            'delta_shelf_price',
            sa.Numeric(precision=8, scale=6),
            server_default='0',
            nullable=False,
        ),
    )
    op.add_column(
        'scenarios',
        sa.Column(
            'delta_bom_cost',
            sa.Numeric(precision=8, scale=6),
            server_default='0',
            nullable=False,
        ),
    )
    op.add_column(
        'scenarios',
        sa.Column(
            'delta_logistics',
            sa.Numeric(precision=8, scale=6),
            server_default='0',
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column('scenarios', 'delta_logistics')
    op.drop_column('scenarios', 'delta_bom_cost')
    op.drop_column('scenarios', 'delta_shelf_price')
