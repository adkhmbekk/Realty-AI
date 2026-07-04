"""agency_memberships — членство пользователя в агентстве (основа многоролевости)

Additive + бэкфилл: создаём таблицу и переносим в неё существующих сотрудников
(каждому — одно членство = его текущее агентство/роль). Поля User.agency_id/
role/is_owner при этом НЕ трогаем (остаются «домашним» членством) — существующее
поведение не меняется. Суперадминов не переносим (у них agency_id = NULL, они
работают через acting-контекст owner_telegram_id/is_shared).

Revision ID: 0035_agency_memberships
Revises: 0034_agency_tariff
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0035_agency_memberships"
down_revision: Union[str, Sequence[str], None] = "0034_agency_tariff"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agency_memberships",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("agency_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column(
            "is_owner", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agency_id"], ["agencies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "agency_id", name="uq_membership_user_agency"
        ),
    )
    op.create_index(
        "ix_agency_memberships_user_id", "agency_memberships", ["user_id"]
    )
    op.create_index(
        "ix_agency_memberships_agency_id", "agency_memberships", ["agency_id"]
    )
    # Бэкфилл: каждому существующему сотруднику — одно членство (его текущее
    # агентство и роль). Суперадминов (agency_id IS NULL) пропускаем.
    op.execute(
        """
        INSERT INTO agency_memberships
            (user_id, agency_id, role, is_owner, is_active, created_at)
        SELECT id, agency_id, role, is_owner, is_active, now()
        FROM users
        WHERE agency_id IS NOT NULL
          AND role IN ('agency_admin', 'agent')
        """
    )


def downgrade() -> None:
    op.drop_table("agency_memberships")
