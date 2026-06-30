"""deals — сделки и комиссия (Волна 5)

Воронка сделки (Новый→Заинтересован→Показ→Договорились→Задаток→Договор→Продано,
плюс cancelled). Цена, комиссия, ответственный агент, чьё агентство выставило
объект (для будущей кросс-агентской сделки). ТОЛЬКО создание новой таблицы —
существующие данные не затрагиваются.

Revision ID: 0027_deals
Revises: 0026_tasks
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0027_deals"
down_revision: Union[str, Sequence[str], None] = "0026_tasks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STAGES = "('new','interested','shown','price_agreed','deposit','contract','sold','cancelled')"


def upgrade() -> None:
    op.create_table(
        "deals",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "agency_id", sa.BigInteger(),
            sa.ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False, index=True,
        ),
        sa.Column(
            "client_id", sa.BigInteger(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True,
        ),
        sa.Column(
            "apartment_id", sa.BigInteger(),
            sa.ForeignKey("apartments.id", ondelete="SET NULL"), nullable=True, index=True,
        ),
        sa.Column("stage", sa.String(), nullable=False, server_default="new"),
        sa.Column("price", sa.Numeric(18, 2), nullable=True),
        sa.Column("currency", sa.String(), nullable=True),
        sa.Column("commission", sa.Numeric(18, 2), nullable=True),
        sa.Column("commission_currency", sa.String(), nullable=True),
        # Ответственный агент (для расчёта комиссии по сотрудникам).
        sa.Column("agent_id", sa.BigInteger(), nullable=True),
        # Чьё агентство выставило объект (для кросс-агентской сделки; внутри = agency_id).
        sa.Column("seller_agency_id", sa.BigInteger(), nullable=True),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"stage IN {_STAGES}", name="ck_deals_stage"),
    )
    op.create_index("ix_deals_agency_stage", "deals", ["agency_id", "stage"])


def downgrade() -> None:
    op.drop_index("ix_deals_agency_stage", table_name="deals")
    op.drop_table("deals")
