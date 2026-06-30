"""clients: priority (hot/warm/cold) + source (откуда пришёл клиент)

Волна 2 «Клиент богаче». ТОЛЬКО ДОБАВЛЕНИЕ необязательных колонок — существующие
данные не затрагиваются. NULL = не задан.

Revision ID: 0024_client_priority_source
Revises: 0023_request_area_score
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0024_client_priority_source"
down_revision: Union[str, Sequence[str], None] = "0023_request_area_score"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("priority", sa.String(), nullable=True))
    op.add_column("clients", sa.Column("source", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("clients", "source")
    op.drop_column("clients", "priority")
