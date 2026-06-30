"""client_activities — лента действий по клиенту (Волна 3)

Звонки/показы/встречи/сообщения/заметки/смена цены по клиенту. ТОЛЬКО создание
новой таблицы — существующие данные не затрагиваются.

Revision ID: 0025_client_activities
Revises: 0024_client_priority_source
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0025_client_activities"
down_revision: Union[str, Sequence[str], None] = "0024_client_priority_source"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "client_activities",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "agency_id", sa.BigInteger(),
            sa.ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False, index=True,
        ),
        sa.Column(
            "client_id", sa.BigInteger(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True,
        ),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('call','show','meeting','message','note','price_change')",
            name="ck_client_activities_kind",
        ),
    )
    op.create_index(
        "ix_client_activities_client_created", "client_activities", ["client_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_client_activities_client_created", table_name="client_activities")
    op.drop_table("client_activities")
