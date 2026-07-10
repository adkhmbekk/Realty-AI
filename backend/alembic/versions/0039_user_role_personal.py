"""users: роль 'user' (личный аккаунт без агентства)

Открытая регистрация (2026-07): человек может войти и получить личный аккаунт,
ещё не состоя ни в одном агентстве. Для этого расширяем CHECK-ограничение роли
значением 'user'. Аддитивно: существующие роли не трогаются, поведение
авторизации без последующих правок не меняется.

Revision ID: 0039_user_role_personal
Revises: 0038_user_profile_fields
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0039_user_role_personal"
down_revision: Union[str, Sequence[str], None] = "0038_user_profile_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD = "role IN ('superadmin','agency_admin','agent')"
_NEW = "role IN ('superadmin','agency_admin','agent','user')"


def upgrade() -> None:
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint("ck_users_role", "users", _NEW)


def downgrade() -> None:
    # Внимание: откат упадёт, если в БД остались строки с role='user'.
    # Их нужно перевести/удалить перед downgrade.
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint("ck_users_role", "users", _OLD)
