"""аренда: deal_type + rent_period на объектах и заявках, статус 'rented'

Добавляем «тип сделки» (продажа/аренда) на объект И на заявку клиента, «срок
аренды» (месяц/сутки) на объект, и новый статус объекта 'rented' («Сдан»).

Всё существующее = продажа (server_default='sale'), поэтому старые данные и
текущая логира поиска/подбора продолжают работать без изменений.

Revision ID: 0020_apartment_rent
Revises: 0019_user_session_epoch
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0020_apartment_rent"
down_revision: Union[str, Sequence[str], None] = "0019_user_session_epoch"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── apartments: тип сделки + срок аренды ──────────────────────────
    op.add_column(
        "apartments",
        sa.Column("deal_type", sa.String(), nullable=False, server_default="sale"),
    )
    op.add_column(
        "apartments",
        sa.Column("rent_period", sa.String(), nullable=True),
    )
    op.create_check_constraint(
        "ck_apartments_deal_type", "apartments", "deal_type IN ('sale','rent')"
    )
    op.create_check_constraint(
        "ck_apartments_rent_period",
        "apartments",
        "rent_period IS NULL OR rent_period IN ('month','day')",
    )
    # Новый статус 'rented' («Сдан») — расширяем существующее ограничение статуса.
    op.drop_constraint("ck_apartments_status", "apartments", type_="check")
    op.create_check_constraint(
        "ck_apartments_status",
        "apartments",
        "status IN ('active','deposit','sold','rented')",
    )
    op.create_index(
        "ix_apartments_agency_deal", "apartments", ["agency_id", "deal_type"]
    )

    # ── client_requests: тип сделки заявки (покупатель/арендатор) ──────
    op.add_column(
        "client_requests",
        sa.Column("deal_type", sa.String(), nullable=False, server_default="sale"),
    )


def downgrade() -> None:
    op.drop_column("client_requests", "deal_type")
    op.drop_index("ix_apartments_agency_deal", table_name="apartments")
    op.drop_constraint("ck_apartments_status", "apartments", type_="check")
    op.create_check_constraint(
        "ck_apartments_status", "apartments", "status IN ('active','deposit','sold')"
    )
    op.drop_constraint("ck_apartments_rent_period", "apartments", type_="check")
    op.drop_constraint("ck_apartments_deal_type", "apartments", type_="check")
    op.drop_column("apartments", "rent_period")
    op.drop_column("apartments", "deal_type")
