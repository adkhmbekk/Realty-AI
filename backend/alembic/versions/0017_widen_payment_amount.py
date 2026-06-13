"""subscription_payments.amount: расширить до Numeric(18, 2)

Зачем: то же, что и с apartments.price (миграция 0016) — платёж может быть в
сумах (крупные суммы), а Numeric(12, 2) переполняется на значениях ≥10 млрд.
Профилактически выравниваем под Numeric(18, 2).

Revision ID: 0017_widen_payment_amount
Revises: 0016_widen_price
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0017_widen_payment_amount"
down_revision: Union[str, Sequence[str], None] = "0016_widen_price"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "subscription_payments", "amount",
        existing_type=sa.Numeric(12, 2),
        type_=sa.Numeric(18, 2),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "subscription_payments", "amount",
        existing_type=sa.Numeric(18, 2),
        type_=sa.Numeric(12, 2),
        existing_nullable=True,
    )
