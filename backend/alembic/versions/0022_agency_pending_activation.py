"""agencies: статус 'pending' + pending_days (активация по ссылке)

Агентство теперь можно создать «черновиком» (status='pending'): без админа и без
запущенной подписки. Владелец отправляет ссылку-активацию; кто откроет её в
Telegram — становится главным админом, и подписка стартует с этого момента на
pending_days дней.

Revision ID: 0022_agency_pending_activation
Revises: 0021_agency_client_phone
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0022_agency_pending_activation"
down_revision: Union[str, Sequence[str], None] = "0021_agency_client_phone"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Новый статус 'pending' (ожидает активации по ссылке).
    op.drop_constraint("ck_agencies_status", "agencies", type_="check")
    op.create_check_constraint(
        "ck_agencies_status",
        "agencies",
        "status IN ('trial','active','frozen','expired','pending')",
    )
    # На сколько дней дать подписку при активации (запоминаем до момента активации).
    op.add_column("agencies", sa.Column("pending_days", sa.Integer(), nullable=True))


def downgrade() -> None:
    # Черновики (status='pending') не пройдут старое ограничение — переводим их
    # в 'expired' ДО пересоздания constraint, иначе downgrade упадёт.
    op.execute("UPDATE agencies SET status='expired' WHERE status='pending'")
    op.drop_column("agencies", "pending_days")
    op.drop_constraint("ck_agencies_status", "agencies", type_="check")
    op.create_check_constraint(
        "ck_agencies_status",
        "agencies",
        "status IN ('trial','active','frozen','expired')",
    )
