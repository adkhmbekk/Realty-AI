"""client_requests: площадь (квадратура) + request_matches: score/reasons

Волна 1 «Умный подбор». ТОЛЬКО ДОБАВЛЕНИЕ необязательных колонок — существующие
данные (реальные объекты/заявки) не затрагиваются.

  • client_requests.area_min / area_max — клиент может искать по площади (м²),
    как у объекта (apartments.area). Раньше у заявки была только land_area (сотки).
  • request_matches.score (0-100) и reasons (JSON {"good":[...],"missing":[...]}) —
    балл совпадения и причины. NULL у старых совпадений — UI просто не покажет %.

Revision ID: 0023_request_area_score
Revises: 0022_agency_pending_activation
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0023_request_area_score"
down_revision: Union[str, Sequence[str], None] = "0022_agency_pending_activation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("client_requests", sa.Column("area_min", sa.Numeric(8, 2), nullable=True))
    op.add_column("client_requests", sa.Column("area_max", sa.Numeric(8, 2), nullable=True))
    op.add_column("request_matches", sa.Column("score", sa.Integer(), nullable=True))
    op.add_column("request_matches", sa.Column("reasons", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("request_matches", "reasons")
    op.drop_column("request_matches", "score")
    op.drop_column("client_requests", "area_max")
    op.drop_column("client_requests", "area_min")
