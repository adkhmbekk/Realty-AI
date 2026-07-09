"""users: поля личного профиля (first_name/last_name/phone/phone_verified/language)

Additive + бэкфилл: добавляем поля личного аккаунта (юзер-центричная модель) и
переносим first_name из существующего full_name. Поведение авторизации не
меняется — членства (0035) остаются источником правды о ролях.

Revision ID: 0038_user_profile_fields
Revises: 0037_invite_multiuse
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0038_user_profile_fields"
down_revision: Union[str, Sequence[str], None] = "0037_invite_multiuse"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("first_name", sa.String(), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.String(), nullable=True))
    op.add_column("users", sa.Column("phone", sa.String(), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "phone_verified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "language",
            sa.String(),
            server_default=sa.text("'ru'"),
            nullable=False,
        ),
    )
    # Уникальность номера — частичный индекс: NULL-номера не конфликтуют между
    # собой (пока номер необязателен), а заданные — уникальны.
    op.create_index(
        "uq_users_phone",
        "users",
        ["phone"],
        unique=True,
        postgresql_where=sa.text("phone IS NOT NULL"),
    )
    # Бэкфилл: first_name из full_name (фамилию не делим — оставляем пусто).
    op.execute(
        "UPDATE users SET first_name = full_name "
        "WHERE first_name IS NULL AND full_name IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_index("uq_users_phone", table_name="users")
    op.drop_column("users", "language")
    op.drop_column("users", "phone_verified")
    op.drop_column("users", "phone")
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")
