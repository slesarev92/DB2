"""Q5 MEMO 5.2: BOM 3 уровня себестоимости (max/normal/optimal)

Заказчик 2026-05-15 (CLIENT_FEEDBACK_v2_DECISIONS.md Q5 / MEMO 5.2):
каждый ингредиент BOM имеет три уровня себестоимости. Pipeline
выбирает уровень per период через ProjectSKU.bom_cost_level (скаляр)
+ bom_cost_level_by_year (JSONB годовой override).

Миграция:
1. ADD bom_items.cost_level VARCHAR(20) NOT NULL DEFAULT 'normal'
   — существующие строки автоматически становятся "normal".
2. ADD UNIQUE (project_sku_id, ingredient_name, cost_level) —
   старого UNIQUE на (project_sku, ingredient_name) не было,
   поэтому только добавляем новый.
3. ADD project_skus.bom_cost_level VARCHAR(20) NOT NULL DEFAULT 'normal'.
4. ADD project_skus.bom_cost_level_by_year JSONB NOT NULL DEFAULT '{}'.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-15 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # BOMItem.cost_level
    op.add_column(
        "bom_items",
        sa.Column(
            "cost_level",
            sa.String(length=20),
            nullable=False,
            server_default="normal",
        ),
    )
    op.create_unique_constraint(
        "uq_bom_items_psk_ingredient_level",
        "bom_items",
        ["project_sku_id", "ingredient_name", "cost_level"],
    )

    # ProjectSKU scalar + per-year override
    op.add_column(
        "project_skus",
        sa.Column(
            "bom_cost_level",
            sa.String(length=20),
            nullable=False,
            server_default="normal",
        ),
    )
    op.add_column(
        "project_skus",
        sa.Column(
            "bom_cost_level_by_year",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("project_skus", "bom_cost_level_by_year")
    op.drop_column("project_skus", "bom_cost_level")
    op.drop_constraint(
        "uq_bom_items_psk_ingredient_level",
        "bom_items",
        type_="unique",
    )
    op.drop_column("bom_items", "cost_level")
