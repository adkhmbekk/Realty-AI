"""apartments.price: расширить до Numeric(18, 2)

Зачем: цены в сумах (UZS) бывают очень крупными — дом за 18 млрд сум (~$1.4M)
не влезал в Numeric(12, 2) (предел ~10 млрд) и импорт падал с numeric field
overflow. Расширяем до Numeric(18, 2) — с запасом на любые сумовые суммы.

Revision ID: 0016_widen_price
Revises: 0015_apartment_source
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0016_widen_price"
down_revision: Union[str, Sequence[str], None] = "0015_apartment_source"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "apartments", "price",
        existing_type=sa.Numeric(12, 2),
        type_=sa.Numeric(18, 2),
        existing_nullable=True,
    )


def downgrade() -> None:
    # Назад сужаем только если все значения влезают в 12,2 (иначе упадёт — и
    # правильно: данные терять нельзя).
    op.alter_column(
        "apartments", "price",
        existing_type=sa.Numeric(18, 2),
        type_=sa.Numeric(12, 2),
        existing_nullable=True,
    )
