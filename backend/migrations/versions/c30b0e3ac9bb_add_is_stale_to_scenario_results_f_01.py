"""add is_stale to scenario_results (F-01)

Revision ID: c30b0e3ac9bb
Revises: 7f562d5f84d2
Create Date: 2026-04-15 18:49:16.156930

Добавляет `ScenarioResult.is_stale` — флаг "параметры проекта изменились,
но пересчёт ещё не запускался". UI показывает badge "⚠️ Расчёт устарел"
когда флаг True.

Инвалидация через `invalidation_service.mark_project_stale(session,
project_id)` из PATCH/POST/DELETE endpoint'ов, меняющих pipeline input.
Сбрасывается в `calculation_service.calculate_and_save_scenario` —
старые records удаляются, новые создаются со `server_default='false'`.

Существующие results (до миграции) получают `is_stale=False` через
server_default — не "мигаем" пользователю красной метки на уже-
рассчитанных проектах.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c30b0e3ac9bb'
down_revision: Union[str, None] = '7f562d5f84d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'scenario_results',
        sa.Column(
            'is_stale',
            sa.Boolean(),
            server_default=sa.text('false'),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column('scenario_results', 'is_stale')
