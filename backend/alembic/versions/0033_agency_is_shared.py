"""agencies.is_shared — общее агентство владельцев платформы («Realty AI»)

Additive: булева колонка (default false). Общее агентство — одно на платформу;
в него могут «входить» ВСЕ суперадмины (acting-контекст), подписка не действует.
Само агентство создаётся при старте (см. ensure_shared_agency в main.py).

Revision ID: 0033_agency_is_shared
Revises: 0032_apartment_added_via
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0033_agency_is_shared"
down_revision: Union[str, Sequence[str], None] = "0032_apartment_added_via"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agencies",
        sa.Column(
            "is_shared",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("agencies", "is_shared")
