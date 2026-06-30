"""apartments.shared_mls + request_matches.source — общая база MLS (Волна 9)

Закрытая общая база внутри агентств платформы: объект попадает в неё только если
агент отметил «поделиться» (shared_mls). Подбор находит и чужие shared-объекты,
помечая совпадение source='mls' (контакт владельца при этом скрывается).

ТОЛЬКО ДОБАВЛЕНИЕ колонок со значениями по умолчанию — данные не затрагиваются.

Revision ID: 0029_mls_sharing
Revises: 0028_notify_prefs
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0029_mls_sharing"
down_revision: Union[str, Sequence[str], None] = "0028_notify_prefs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "apartments",
        sa.Column("shared_mls", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "request_matches",
        sa.Column("source", sa.String(), nullable=False, server_default="own"),
    )
    op.create_index("ix_apartments_shared_mls", "apartments", ["shared_mls"])


def downgrade() -> None:
    op.drop_index("ix_apartments_shared_mls", table_name="apartments")
    op.drop_column("request_matches", "source")
    op.drop_column("apartments", "shared_mls")
