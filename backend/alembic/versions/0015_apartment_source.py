"""apartments.source: название источника (канала)

Внутреннее поле: откуда взято объявление (название канала/площадки). Видно
команде, но не уходит клиенту при «поделиться».

Revision ID: 0015_apartment_source
Revises: 0014_watched_channels
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0015_apartment_source"
down_revision: Union[str, Sequence[str], None] = "0014_watched_channels"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("apartments", sa.Column("source", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("apartments", "source")
