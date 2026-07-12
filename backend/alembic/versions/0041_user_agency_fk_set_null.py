"""users.agency_id FK → ON DELETE SET NULL (не сносить сотрудников при удалении агентства)

Критфикс (аудит 2026-07-11): удаление агентства (delete_agency/purge_user) не должно
удалять аккаунты его сотрудников. Раньше `delete_with_data` явно делал
`DELETE FROM users WHERE agency_id=X`, а внешний ключ users.agency_id в baseline
создавался БЕЗ ondelete (NO ACTION) — при этом членства удалённых юзеров в ДРУГИХ
агентствах уходили каскадом (agency_memberships.user_id = CASCADE), то есть удаление
одного тенанта рушило данные другого.

Теперь: сервис заранее переселяет/отвязывает сотрудников, а FK делаем SET NULL как
подстраховку — оставшийся сотрудник просто «отвязывается» (agency_id=NULL), а не удаляется.

Additive/безопасно: только смена правила ON DELETE у уже существующего FK.

Revision ID: 0041_user_agency_fk_set_null
Revises: 0040_user_agency_archive
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0041_user_agency_fk_set_null"
down_revision: Union[str, Sequence[str], None] = "0040_user_agency_archive"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Имя FK по умолчанию в Postgres: <таблица>_<колонка>_fkey.
_FK = "users_agency_id_fkey"


def upgrade() -> None:
    op.drop_constraint(_FK, "users", type_="foreignkey")
    op.create_foreign_key(
        _FK, "users", "agencies",
        ["agency_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(_FK, "users", type_="foreignkey")
    # Восстанавливаем как в baseline — без правила ON DELETE (NO ACTION).
    op.create_foreign_key(_FK, "users", "agencies", ["agency_id"], ["id"])
