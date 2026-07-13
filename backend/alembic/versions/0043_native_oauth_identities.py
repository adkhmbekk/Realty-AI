"""users: внешние идентичности для нативного приложения (Google/Apple)

Additive. Нативное приложение (Android/iOS, 2026-07) входит вне Telegram — через
Google/Apple. У таких пользователей НЕТ telegram_id, их личность — стабильный
'sub' провайдера. Поэтому:
  - telegram_id делаем NULLABLE (native-юзер его не имеет);
  - добавляем google_sub / apple_sub (уникальны среди активных, как phone) и
    email (справочно, НЕ ключ связывания аккаунтов — риск угона).

Связывание Telegram- и native-аккаунтов одного человека делаем ПОЗЖЕ по
телефону-якорю, отдельной миграцией/логикой.

Revision ID: 0043_native_oauth_identities
Revises: 0042_crm_created_by_fks
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0043_native_oauth_identities"
down_revision: Union[str, Sequence[str], None] = "0042_crm_created_by_fks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Новые колонки идентичности (все необязательные — существующим Telegram-
    #    юзерам добавятся как NULL, данные не трогаются).
    op.add_column("users", sa.Column("google_sub", sa.String(), nullable=True))
    op.add_column("users", sa.Column("apple_sub", sa.String(), nullable=True))
    op.add_column("users", sa.Column("email", sa.String(), nullable=True))

    # 2. telegram_id больше не обязателен: native-пользователь входит без него.
    op.alter_column(
        "users", "telegram_id", existing_type=sa.BigInteger(), nullable=True
    )

    # 3. Уникальность google_sub/apple_sub — только среди активных (как phone):
    #    архивный аккаунт сохраняет свой sub, а новый вход того же провайдера
    #    заведёт чистый аккаунт без конфликта уникальности.
    op.create_index(
        "uq_users_google_sub",
        "users",
        ["google_sub"],
        unique=True,
        postgresql_where=sa.text("google_sub IS NOT NULL AND archived_at IS NULL"),
    )
    op.create_index(
        "uq_users_apple_sub",
        "users",
        ["apple_sub"],
        unique=True,
        postgresql_where=sa.text("apple_sub IS NOT NULL AND archived_at IS NULL"),
    )
    # email — не уникален (у провайдеров бывает переиспользование/отсутствие),
    # просто индекс для поиска.
    op.create_index("ix_users_email", "users", ["email"])


def downgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("uq_users_apple_sub", table_name="users")
    op.drop_index("uq_users_google_sub", table_name="users")
    # Вернуть NOT NULL можно только если нет native-юзеров (telegram_id IS NULL).
    op.alter_column(
        "users", "telegram_id", existing_type=sa.BigInteger(), nullable=False
    )
    op.drop_column("users", "email")
    op.drop_column("users", "apple_sub")
    op.drop_column("users", "google_sub")
