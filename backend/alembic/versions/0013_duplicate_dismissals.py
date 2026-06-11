"""duplicate_dismissals: подтверждённые «не дубликаты»

Таблица, где хранятся группы объектов, которые пользователь отметил как «не
дубликаты» (по ключу группы — нормализованному телефону), чтобы они больше не
всплывали в менеджере дубликатов.

Revision ID: 0013_duplicate_dismissals
Revises: 0012_agency_owner
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0013_duplicate_dismissals"
down_revision: Union[str, Sequence[str], None] = "0012_agency_owner"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "duplicate_dismissals",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("agency_id", sa.BigInteger(), nullable=False),
        sa.Column("group_key", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["agency_id"], ["agencies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agency_id", "group_key", name="uq_dup_dismissal_agency_key"),
    )
    op.create_index(
        op.f("ix_duplicate_dismissals_agency_id"),
        "duplicate_dismissals", ["agency_id"], unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_duplicate_dismissals_agency_id"), table_name="duplicate_dismissals")
    op.drop_table("duplicate_dismissals")
