"""users.session_epoch: мгновенный отзыв доступа (версия сессии)

Бамп этого числа делает ВСЕ ранее выданные пропуска (access + refresh) данного
пользователя недействительными сразу. Нужно для «выйти со всех устройств» и для
того, чтобы отключение/исключение сотрудника убивало даже долгоживущий
refresh-токен (и он не «воскресал» при повторном включении).

Revision ID: 0019_user_session_epoch
Revises: 0018_clients
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0019_user_session_epoch"
down_revision: Union[str, Sequence[str], None] = "0018_clients"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("session_epoch", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "session_epoch")
