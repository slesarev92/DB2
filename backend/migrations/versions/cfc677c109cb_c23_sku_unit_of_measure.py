"""c23_sku_unit_of_measure

C #23: добавление SKU.unit_of_measure (Literal "л"/"кг", NOT NULL,
default "л"). Backfill existing SKU в "л" — текущее implicit поведение
(volume_l хранил литры).

Revision ID: cfc677c109cb
Revises: eb59341b9034
Create Date: 2026-05-16 15:39:53.250965
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "cfc677c109cb"
down_revision: Union[str, None] = "eb59341b9034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VALID_UNITS = ("л", "кг")


def upgrade() -> None:
    # 1. Add column nullable first to allow backfill
    op.add_column(
        "skus",
        sa.Column("unit_of_measure", sa.String(2), nullable=True),
    )
    # 2. Backfill existing → "л" (current implicit behaviour — volume_l stored litres)
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE skus SET unit_of_measure = 'л' WHERE unit_of_measure IS NULL"))
    # 3. Set NOT NULL + server_default
    op.alter_column("skus", "unit_of_measure", nullable=False, server_default="л")
    # 4. CHECK constraint (alembic naming convention adds ck_skus_ prefix automatically)
    units_sql = ",".join(f"'{u}'" for u in VALID_UNITS)
    op.create_check_constraint(
        "valid_sku_unit_of_measure_value",
        "skus",
        f"unit_of_measure IN ({units_sql})",
    )


def downgrade() -> None:
    # Naming convention in base.py adds ck_skus_ prefix automatically —
    # pass the raw name (same as create_check_constraint above).
    op.drop_constraint("valid_sku_unit_of_measure_value", "skus", type_="check")
    op.drop_column("skus", "unit_of_measure")
