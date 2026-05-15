"""Q6: CA&M и Marketing rates на ProjectSKUChannel (per-channel)

Заказчик 2026-05-15 (CLIENT_FEEDBACK_v2_DECISIONS.md Q6) попросил
перенести ca_m_rate и marketing_rate с ProjectSKU на
ProjectSKUChannel — в HM/SM маркетинг другой, чем в TT.

Миграция:
1. ADD ca_m_rate, marketing_rate в project_sku_channels (default 0)
2. COPY значения с project_skus в каждую дочернюю PSC запись
3. DROP ca_m_rate, marketing_rate из project_skus

Downgrade: обратное направление, при копировании используется AVG
по всем каналам SKU (не идеальное восстановление, но downgrade —
аварийный сценарий).

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-15 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_sku_channels",
        sa.Column(
            "ca_m_rate",
            sa.Numeric(8, 6),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "project_sku_channels",
        sa.Column(
            "marketing_rate",
            sa.Numeric(8, 6),
            nullable=False,
            server_default="0",
        ),
    )

    op.execute(
        """
        UPDATE project_sku_channels AS psc
        SET ca_m_rate = ps.ca_m_rate,
            marketing_rate = ps.marketing_rate
        FROM project_skus AS ps
        WHERE psc.project_sku_id = ps.id
        """
    )

    op.drop_column("project_skus", "ca_m_rate")
    op.drop_column("project_skus", "marketing_rate")


def downgrade() -> None:
    op.add_column(
        "project_skus",
        sa.Column(
            "ca_m_rate",
            sa.Numeric(8, 6),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "project_skus",
        sa.Column(
            "marketing_rate",
            sa.Numeric(8, 6),
            nullable=False,
            server_default="0",
        ),
    )

    op.execute(
        """
        UPDATE project_skus AS ps
        SET ca_m_rate = COALESCE((
                SELECT AVG(ca_m_rate)
                FROM project_sku_channels
                WHERE project_sku_id = ps.id
            ), 0),
            marketing_rate = COALESCE((
                SELECT AVG(marketing_rate)
                FROM project_sku_channels
                WHERE project_sku_id = ps.id
            ), 0)
        """
    )

    op.drop_column("project_sku_channels", "ca_m_rate")
    op.drop_column("project_sku_channels", "marketing_rate")
