"""invites: многоразовость (max_uses / used_count)

Additive: добавляем лимит использований кода приглашения и счётчик уже
использованных вступлений. Существующие приглашения остаются одноразовыми
(max_uses=1); уже использованным проставляем used_count=1, чтобы их статус
не «ожил» после добавления счётчика.

Revision ID: 0037_invite_multiuse
Revises: 0036_apartment_mls_pool_index
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0037_invite_multiuse"
down_revision: Union[str, Sequence[str], None] = "0036_apartment_mls_pool_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "invites",
        sa.Column(
            "max_uses", sa.Integer(), server_default=sa.text("1"), nullable=False
        ),
    )
    op.add_column(
        "invites",
        sa.Column(
            "used_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
    )
    # Бэкфилл: уже использованные (одноразовые) приглашения = 1 использование.
    op.execute("UPDATE invites SET used_count = 1 WHERE used_at IS NOT NULL")


def downgrade() -> None:
    op.drop_column("invites", "used_count")
    op.drop_column("invites", "max_uses")
