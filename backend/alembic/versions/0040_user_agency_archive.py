"""users/agencies: архивация (удаление юзеров владельцем платформы)

Additive. Добавляем archived_at пользователю и агентству. Ключевое: уникальность
telegram_id и phone делаем ЧАСТИЧНОЙ (только среди НЕархивных) — тогда архивный
аккаунт сохраняет свои telegram_id/номер, а человек при следующем входе заводит
новый чистый аккаунт с тем же Telegram, без конфликта уникальности.

Revision ID: 0040_user_agency_archive
Revises: 0039_user_role_personal
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0040_user_agency_archive"
down_revision: Union[str, Sequence[str], None] = "0039_user_role_personal"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agencies", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_users_archived_at", "users", ["archived_at"])
    op.create_index("ix_agencies_archived_at", "agencies", ["archived_at"])

    # telegram_id: заменяем сплошной уникальный индекс на ЧАСТИЧНЫЙ (только активные).
    op.drop_index("ix_users_telegram_id", table_name="users")
    op.create_index(
        "ix_users_telegram_id", "users", ["telegram_id"], unique=False
    )
    op.create_index(
        "uq_users_telegram_id_active",
        "users",
        ["telegram_id"],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
    )

    # phone: уникальность тоже только среди активных (архивный номер не мешает
    # новому аккаунту заново поделиться тем же номером).
    op.drop_index("uq_users_phone", table_name="users")
    op.create_index(
        "uq_users_phone",
        "users",
        ["phone"],
        unique=True,
        postgresql_where=sa.text("phone IS NOT NULL AND archived_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_users_phone", table_name="users")
    op.create_index(
        "uq_users_phone",
        "users",
        ["phone"],
        unique=True,
        postgresql_where=sa.text("phone IS NOT NULL"),
    )
    op.drop_index("uq_users_telegram_id_active", table_name="users")
    op.drop_index("ix_users_telegram_id", table_name="users")
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)
    op.drop_index("ix_agencies_archived_at", table_name="agencies")
    op.drop_index("ix_users_archived_at", table_name="users")
    op.drop_column("agencies", "archived_at")
    op.drop_column("users", "archived_at")
