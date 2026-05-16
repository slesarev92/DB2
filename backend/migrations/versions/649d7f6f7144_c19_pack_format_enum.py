"""c19 pack format enum

Revision ID: 649d7f6f7144
Revises: d4c87e14d126
Create Date: 2026-05-16 10:53:59.413363

C #19: SKU.format → enum (ПЭТ/Стекло/Банка/Сашет/Стик/Пауч + NULL).

Шаг 1: backfill existing значений через fuzzy mapping
(case-insensitive substring match). Несовпадающие → NULL с логом.
Шаг 2: ADD CHECK constraint.

Spec: docs/superpowers/specs/2026-05-16-c19-pack-format-enum-design.md
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '649d7f6f7144'
down_revision: Union[str, None] = 'd4c87e14d126'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# C #19 enum values (Cyrillic). Должны совпадать с PackFormat Literal
# в backend/app/schemas/sku.py.
VALID_FORMATS = ("ПЭТ", "Стекло", "Банка", "Сашет", "Стик", "Пауч")

# Fuzzy mapping: case-insensitive substring patterns → target enum value.
# Первый match wins (порядок важен; более специфичные паттерны раньше).
MAPPING_RULES = [
    ("ПЭТ", ["пэт", "pet", "p.e.t"]),
    ("Стекло", ["стекл", "glass"]),
    ("Банка", ["банк", "can", "tin"]),
    ("Сашет", ["саше", "sachet"]),
    ("Стик", ["стик", "stick"]),
    ("Пауч", ["пауч", "pouch"]),
]


def upgrade() -> None:
    conn = op.get_bind()

    # Step 1: backfill fuzzy matches.
    for target, patterns in MAPPING_RULES:
        like_clauses = " OR ".join(
            [f"LOWER(format) LIKE '%{p}%'" for p in patterns]
        )
        conn.execute(sa.text(
            f"UPDATE skus SET format = :tgt "
            f"WHERE format IS NOT NULL AND ({like_clauses})"
        ), {"tgt": target})

    # Step 2: log + null out non-matching.
    in_list = ", ".join([f"'{v}'" for v in VALID_FORMATS])
    rows = conn.execute(sa.text(
        f"SELECT format, COUNT(*) FROM skus "
        f"WHERE format IS NOT NULL AND format NOT IN ({in_list}) "
        f"GROUP BY format"
    )).fetchall()
    if rows:
        print(f"[C #19] Setting to NULL non-mappable formats:")
        for fmt, cnt in rows:
            print(f"  '{fmt}': {cnt} rows")
    conn.execute(sa.text(
        f"UPDATE skus SET format = NULL "
        f"WHERE format IS NOT NULL AND format NOT IN ({in_list})"
    ))

    # Step 3: ADD CHECK constraint.
    # NOTE: Alembic naming convention expands "format" → "ck_skus_format"
    # (via "ck": "ck_%(table_name)s_%(constraint_name)s" in base.py).
    op.create_check_constraint(
        "format",
        "skus",
        f"format IS NULL OR format IN ({in_list})",
    )


def downgrade() -> None:
    op.drop_constraint("ck_skus_format", "skus", type_="check")
