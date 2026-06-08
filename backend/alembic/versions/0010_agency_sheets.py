"""agency_sheets: связь агентства с Google-таблицей

Revision ID: 0010_agency_sheets
Revises: 0009_apartment_land_area
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0010_agency_sheets"
down_revision: Union[str, Sequence[str], None] = "0009_apartment_land_area"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agency_sheets",
        sa.Column("agency_id", sa.BigInteger(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("spreadsheet_id", sa.Text(), nullable=True),
        sa.Column("spreadsheet_url", sa.Text(), nullable=True),
        sa.Column("sheet_title", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="disconnected"),
        sa.Column("error_note", sa.Text(), nullable=True),
        sa.Column("last_modified_time", sa.Text(), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["agency_id"], ["agencies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("agency_id"),
    )


def downgrade() -> None:
    op.drop_table("agency_sheets")
