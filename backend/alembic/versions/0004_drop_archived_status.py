"""drop the 'archived' apartment status (convert any leftovers to 'active')

Статус «Архив» убран из приложения как недостижимый и путающий. На случай, если
в базе остались объекты со статусом 'archived' (его нельзя было выставить из
интерфейса, но подстрахуемся) — переводим их обратно в 'active'.

Revision ID: 0004_drop_archived_status
Revises: 0003_subscription_warned_at
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0004_drop_archived_status"
down_revision: Union[str, Sequence[str], None] = "0003_subscription_warned_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text("UPDATE apartments SET status = 'active' WHERE status = 'archived'")
    )


def downgrade() -> None:
    # Обратной операции нет: какие объекты были «архивными», не сохранялось.
    pass
