"""watched_channels.share_mls — делиться авто-импортом в общей базе (фикс MLS)

ТОЛЬКО ДОБАВЛЕНИЕ колонки со значением по умолчанию (false) — данные не трогаем.

Revision ID: 0030_watch_share_mls
Revises: 0029_mls_sharing
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0030_watch_share_mls"
down_revision: Union[str, Sequence[str], None] = "0029_mls_sharing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "watched_channels",
        sa.Column("share_mls", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("watched_channels", "share_mls")
