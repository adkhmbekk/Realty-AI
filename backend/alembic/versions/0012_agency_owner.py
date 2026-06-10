"""agencies.owner_telegram_id: личные агентства владельца платформы

Добавляет колонку agencies.owner_telegram_id (nullable) + индекс. NULL —
обычное клиентское агентство; заполнено — личное агентство суперадмина с
этим telegram_id (он может «войти» в него как главный админ, подписка не
действует).

Revision ID: 0012_agency_owner
Revises: 0011_agency_sheets_snapshot
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0012_agency_owner"
down_revision: Union[str, Sequence[str], None] = "0011_agency_sheets_snapshot"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agencies",
        sa.Column("owner_telegram_id", sa.BigInteger(), nullable=True),
    )
    op.create_index(
        op.f("ix_agencies_owner_telegram_id"),
        "agencies",
        ["owner_telegram_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_agencies_owner_telegram_id"), table_name="agencies")
    op.drop_column("agencies", "owner_telegram_id")
