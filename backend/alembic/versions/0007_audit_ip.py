"""add ip column to audit_log

Сохраняем IP-адрес источника действия (например, при входе) для разбора
инцидентов. См. аудит-находку L8. Колонка nullable — старые записи остаются как есть.

Revision ID: 0007_audit_ip
Revises: 0006_idx_agency_created_by
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0007_audit_ip"
down_revision: Union[str, Sequence[str], None] = "0006_idx_agency_created_by"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("audit_log", sa.Column("ip", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("audit_log", "ip")
