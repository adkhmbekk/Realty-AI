"""phone_otp_codes: одноразовые SMS-коды входа по номеру телефона

Additive. Вход в нативное приложение по номеру: /auth/phone/request шлёт SMS с
6-значным кодом (TTL 5 мин), /auth/phone/verify обменивает код на сессию.
Ничего в существующих таблицах не меняется.

Revision ID: 0046_phone_otp_codes
Revises: 0045_membership_last_seen
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0046_phone_otp_codes"
down_revision: Union[str, Sequence[str], None] = "0045_membership_last_seen"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "phone_otp_codes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("phone", sa.String(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_phone_otp_codes_phone", "phone_otp_codes", ["phone"])


def downgrade() -> None:
    op.drop_index("ix_phone_otp_codes_phone", table_name="phone_otp_codes")
    op.drop_table("phone_otp_codes")
