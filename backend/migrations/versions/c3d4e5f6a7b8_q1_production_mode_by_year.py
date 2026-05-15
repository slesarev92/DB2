"""Q1: production_mode_by_year на ProjectSKU (JSONB per-year override)

Заказчик 2026-05-15 (CLIENT_FEEDBACK_v2_DECISIONS.md Q1) попросил
возможность тюнинговать режим производства (копакинг / своё) по
годам: Y1=копак, Y2=своё, Y3+=копак. Гранулярность годовая.

Хранение: JSONB колонка `production_mode_by_year` на project_skus.
Ключи — строки "1".."10" (model_year), значения "own" | "copacking".
Пустой объект `{}` = годового override нет, используется скаляр
production_mode для всего горизонта.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-15 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_skus",
        sa.Column(
            "production_mode_by_year",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("project_skus", "production_mode_by_year")
