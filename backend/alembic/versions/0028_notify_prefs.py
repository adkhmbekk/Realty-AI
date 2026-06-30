"""users.match_notify + clients.muted — настройки уведомлений (Волна 8)

ТОЛЬКО ДОБАВЛЕНИЕ колонок со значениями по умолчанию — существующие данные не
затрагиваются. match_notify: off / instant / daily (как часто слать бот-пуш о
новых совпадениях). muted: приглушить уведомления по конкретному клиенту.

Revision ID: 0028_notify_prefs
Revises: 0027_deals
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0028_notify_prefs"
down_revision: Union[str, Sequence[str], None] = "0027_deals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("match_notify", sa.String(), nullable=False, server_default="instant"),
    )
    op.add_column(
        "clients",
        sa.Column("muted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("clients", "muted")
    op.drop_column("users", "match_notify")
