"""users.last_seen_at: присутствие «в сети» (последний heartbeat)

ТОЛЬКО ДОБАВЛЕНИЕ nullable-колонки — существующие данные не трогаем. Колонка
обновляется, пока пользователь в приложении (периодический heartbeat), и
используется для статуса «в сети» и точного времени активности в панели
владельца платформы.

Revision ID: 0031_user_last_seen
Revises: 0030_watch_share_mls
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0031_user_last_seen"
down_revision: Union[str, Sequence[str], None] = "0030_watch_share_mls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "last_seen_at")
