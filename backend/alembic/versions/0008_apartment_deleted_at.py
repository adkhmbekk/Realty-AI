"""add deleted_at (archive bin) to apartments

Revision ID: 0008_apartment_deleted_at
Revises: 0007_audit_ip
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0008_apartment_deleted_at"
down_revision: Union[str, Sequence[str], None] = "0007_audit_ip"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "apartments",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_apartments_agency_deleted", "apartments", ["agency_id", "deleted_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_apartments_agency_deleted", table_name="apartments")
    op.drop_column("apartments", "deleted_at")
