"""apartments: частичный индекс для общей базы (MLS) — M5

Общая база (MLS) показывает объекты ВСЕХ агентств (по умолчанию без фильтра
agency_id), новые сверху. Существующие индексы (agency_id, ...) тут не
применимы, а одиночный булев ix_apartments_shared_mls не покрывает
ORDER BY created_at. Добавляем ЧАСТИЧНЫЙ индекс (created_at) WHERE
shared_mls AND deleted_at IS NULL — он покрывает и предикат, и сортировку,
и остаётся компактным (только расшаренные неудалённые строки).

Revision ID: 0036_apartment_mls_pool_index
Revises: 0035_agency_memberships
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0036_apartment_mls_pool_index"
down_revision: Union[str, Sequence[str], None] = "0035_agency_memberships"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # На большой «живой» таблице предпочтительно CONCURRENTLY (вне транзакции);
    # здесь таблица небольшая, поэтому обычный create_index в транзакции безопасен.
    op.create_index(
        "ix_apartments_mls_pool",
        "apartments",
        ["created_at"],
        postgresql_where=sa.text("shared_mls AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_apartments_mls_pool", table_name="apartments")
