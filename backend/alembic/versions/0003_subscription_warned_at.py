"""add agencies.subscription_warned_at

Колонка-метка: когда владельцу агентства в последний раз отправляли
предупреждение об окончании подписки. Нужна, чтобы фоновая задача не слала
предупреждение слишком часто.

Revision ID: 0003_subscription_warned_at
Revises: 0002_cleanup_legacy
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0003_subscription_warned_at"
down_revision: Union[str, Sequence[str], None] = "0002_cleanup_legacy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agencies",
        sa.Column("subscription_warned_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agencies", "subscription_warned_at")
