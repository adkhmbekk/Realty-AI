"""add land_area (соток) to apartments

Revision ID: 0009_apartment_land_area
Revises: 0008_apartment_deleted_at
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0009_apartment_land_area"
down_revision: Union[str, Sequence[str], None] = "0008_apartment_deleted_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "apartments",
        sa.Column("land_area", sa.Numeric(10, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("apartments", "land_area")
