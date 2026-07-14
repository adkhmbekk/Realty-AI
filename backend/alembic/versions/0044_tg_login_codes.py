"""tg_login_codes: одноразовые коды входа через Telegram-бота

Additive. Нативное приложение входит через отдельного бота (@realtyloginbot) с
подтверждением по кнопке. Таблица хранит короткоживущие (5 мин) одноразовые коды:
приложение создаёт код, бот его подтверждает (webhook), приложение опрашивает и
получает сессию. Ничего в существующих таблицах не меняется.

Revision ID: 0044_tg_login_codes
Revises: 0043_native_oauth_identities
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0044_tg_login_codes"
down_revision: Union[str, Sequence[str], None] = "0043_native_oauth_identities"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tg_login_codes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("tg_first_name", sa.String(), nullable=True),
        sa.Column("tg_last_name", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("uq_tg_login_codes_code", "tg_login_codes", ["code"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_tg_login_codes_code", table_name="tg_login_codes")
    op.drop_table("tg_login_codes")
