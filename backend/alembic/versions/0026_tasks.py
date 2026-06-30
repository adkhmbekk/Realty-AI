"""tasks — задачи по клиенту (ручные + авто «молчит N дней») (Волна 4)

ТОЛЬКО создание новой таблицы — существующие данные не затрагиваются.

Revision ID: 0026_tasks
Revises: 0025_client_activities
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0026_tasks"
down_revision: Union[str, Sequence[str], None] = "0025_client_activities"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "agency_id", sa.BigInteger(),
            sa.ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False, index=True,
        ),
        sa.Column(
            "client_id", sa.BigInteger(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True,
        ),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("deadline", sa.Date(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="open"),
        sa.Column("kind", sa.String(), nullable=False, server_default="manual"),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('open','done')", name="ck_tasks_status"),
        sa.CheckConstraint("kind IN ('manual','auto')", name="ck_tasks_kind"),
    )
    op.create_index("ix_tasks_agency_status", "tasks", ["agency_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_tasks_agency_status", table_name="tasks")
    op.drop_table("tasks")
