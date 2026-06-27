"""agencies.client_phone: номер человека, открывшего агентство (для владельца)

Необязательное поле в карточке агентства (видит только суперадмин): телефон
клиента, с которым договорились об открытии агентства. Можно заполнить позже.
Отличается от contact_phone (публичный номер агентства для клиентов при «поделиться»).

Revision ID: 0021_agency_client_phone
Revises: 0020_apartment_rent
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0021_agency_client_phone"
down_revision: Union[str, Sequence[str], None] = "0020_apartment_rent"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agencies", sa.Column("client_phone", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("agencies", "client_phone")
