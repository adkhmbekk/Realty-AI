"""agency_memberships.last_seen_at: присутствие юзера в конкретном агентстве

Additive. Колонка nullable — обновляется при входе в агентство и heartbeat'ами,
пока юзер внутри него. По ней карточка юзера у владельца платформы показывает
статус (онлайн/был только что/точное время) отдельно для каждого агентства.
Ничего в существующих данных не меняется.

Revision ID: 0045_membership_last_seen
Revises: 0044_tg_login_codes
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0045_membership_last_seen"
down_revision: Union[str, Sequence[str], None] = "0044_tg_login_codes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agency_memberships",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agency_memberships", "last_seen_at")
