"""fine tuning per period overrides

Revision ID: d4c87e14d126
Revises: e5f6a7b8c9d0
Create Date: 2026-05-15 18:48:31.801405

C #14: per-period override JSONB-arrays (length 43) for copacking_rate
(ProjectSKU) and logistics_cost_per_kg / ca_m_rate / marketing_rate
(ProjectSKUChannel). NULL = no override (pipeline falls back to scalar).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d4c87e14d126"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "project_skus",
        sa.Column(
            "copacking_rate_by_period",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "project_sku_channels",
        sa.Column(
            "logistics_cost_per_kg_by_period",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "project_sku_channels",
        sa.Column(
            "ca_m_rate_by_period",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "project_sku_channels",
        sa.Column(
            "marketing_rate_by_period",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("project_sku_channels", "marketing_rate_by_period")
    op.drop_column("project_sku_channels", "ca_m_rate_by_period")
    op.drop_column("project_sku_channels", "logistics_cost_per_kg_by_period")
    op.drop_column("project_skus", "copacking_rate_by_period")
