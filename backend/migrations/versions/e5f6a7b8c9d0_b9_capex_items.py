"""B.9 / MEMO 2.1: статьи CAPEX (CapexItem) — разбивка ProjectFinancialPlan.capex

Заказчик MEMO 2.1: CAPEX должен иметь статьи затрат (Молды и оснастка,
Линия розлива, Оборудование, …) с возможностью add/remove — аналог
существующих OpexItem.

Структура capex_items идентична opex_items (financial_plan_id, category,
name, amount + UNIQUE на тройку). CASCADE через FK на ProjectFinancialPlan.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-15 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "capex_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("financial_plan_id", sa.Integer(), nullable=False),
        sa.Column(
            "category", sa.String(length=50), nullable=False,
            server_default="other",
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "amount", sa.Numeric(precision=20, scale=2), nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["financial_plan_id"], ["project_financial_plans.id"],
            name=op.f("fk_capex_items_financial_plan_id_project_financial_plans"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_capex_items")),
        sa.UniqueConstraint(
            "financial_plan_id", "category", "name",
            name="uq_capex_items_plan_category_name",
        ),
    )


def downgrade() -> None:
    op.drop_table("capex_items")
