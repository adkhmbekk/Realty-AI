"""CRM created_by/agent_id/seller_agency_id → настоящие FK с ON DELETE SET NULL

Аудит 2026-07-11 (HI-3): колонки-ссылки на пользователя/агентство в CRM были
простыми BigInteger без внешнего ключа. При удалении юзера/агентства ссылки
«повисали» на несуществующем id → неверная атрибуция комиссии и клиенты,
невидимые всем агентам. Делаем их настоящими FK с ondelete=SET NULL.

Перед добавлением ограничения ОБНУЛЯЕМ уже осиротевшие значения (иначе создание
FK упадёт на существующих «висячих» ссылках).

Revision ID: 0042_crm_created_by_fks
Revises: 0041_user_agency_fk_set_null
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0042_crm_created_by_fks"
down_revision: Union[str, Sequence[str], None] = "0041_user_agency_fk_set_null"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (таблица, колонка, целевая_таблица, имя_FK)
_USER_FKS = [
    ("deals", "agent_id", "deals_agent_id_fkey"),
    ("deals", "created_by", "deals_created_by_fkey"),
    ("clients", "created_by", "clients_created_by_fkey"),
    ("client_requests", "created_by", "client_requests_created_by_fkey"),
    ("client_activities", "created_by", "client_activities_created_by_fkey"),
    ("tasks", "created_by", "tasks_created_by_fkey"),
    ("watched_channels", "created_by", "watched_channels_created_by_fkey"),
]
_AGENCY_FKS = [
    ("deals", "seller_agency_id", "deals_seller_agency_id_fkey"),
]


def upgrade() -> None:
    # 1. Обнуляем сироты (значение указывает на несуществующую строку).
    for table, col, _name in _USER_FKS:
        op.execute(
            f"UPDATE {table} SET {col} = NULL "
            f"WHERE {col} IS NOT NULL AND {col} NOT IN (SELECT id FROM users)"
        )
    for table, col, _name in _AGENCY_FKS:
        op.execute(
            f"UPDATE {table} SET {col} = NULL "
            f"WHERE {col} IS NOT NULL AND {col} NOT IN (SELECT id FROM agencies)"
        )

    # 2. Добавляем внешние ключи с ON DELETE SET NULL.
    for table, col, name in _USER_FKS:
        op.create_foreign_key(name, table, "users", [col], ["id"], ondelete="SET NULL")
    for table, col, name in _AGENCY_FKS:
        op.create_foreign_key(name, table, "agencies", [col], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    for table, _col, name in _USER_FKS + _AGENCY_FKS:
        op.drop_constraint(name, table, type_="foreignkey")
