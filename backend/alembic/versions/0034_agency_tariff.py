"""agencies.tariff — тариф агентства (сейчас у всех бесплатный 'start')

Additive: строковая колонка (default 'start', not null). Подписка отключена
(agency_is_active всегда True), у всех агентств бесплатный тариф без даты
окончания. Платные тарифы добавим позже — колонка задел на будущее.

Revision ID: 0034_agency_tariff
Revises: 0033_agency_is_shared
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0034_agency_tariff"
down_revision: Union[str, Sequence[str], None] = "0033_agency_is_shared"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agencies",
        sa.Column(
            "tariff",
            sa.String(),
            nullable=False,
            server_default=sa.text("'start'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("agencies", "tariff")
