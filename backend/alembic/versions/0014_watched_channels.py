"""watched_channels: фоновый авто-импорт из Telegram-каналов

Каналы, которые агентство «слушает»: сервер периодически проверяет их и сам
добавляет новые посты в базу. last_post_id — курсор уже учтённых постов.

Revision ID: 0014_watched_channels
Revises: 0013_duplicate_dismissals
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0014_watched_channels"
down_revision: Union[str, Sequence[str], None] = "0013_duplicate_dismissals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "watched_channels",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("agency_id", sa.BigInteger(), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("last_post_id", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["agency_id"], ["agencies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agency_id", "channel", name="uq_watched_agency_channel"),
    )
    op.create_index(
        op.f("ix_watched_channels_agency_id"),
        "watched_channels", ["agency_id"], unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_watched_channels_agency_id"), table_name="watched_channels")
    op.drop_table("watched_channels")
