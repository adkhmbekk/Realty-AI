"""add index (agency_id, created_by) on apartments

Ускоряет выборки объектов конкретного агента внутри агентства
(например, экран AgentDetail и фильтр «мои объекты»). См. аудит-находку L4.

Revision ID: 0006_idx_agency_created_by
Revises: 0005_audit_payments
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0006_idx_agency_created_by"
down_revision: Union[str, Sequence[str], None] = "0005_audit_payments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_apartments_agency_created_by",
        "apartments",
        ["agency_id", "created_by"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_apartments_agency_created_by", table_name="apartments")
