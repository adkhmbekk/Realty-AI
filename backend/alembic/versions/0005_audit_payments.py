"""audit log, subscription payments, per-agency display counter, drop agents,
CHECK constraints, ON DELETE CASCADE for photos/events, trigram search indexes

Что делает эта миграция (одним пакетом, см. аудит-правки):
  1) переносит счётчик номеров объектов из таблицы agents в новое поле
     agencies.last_display_number (с переносом текущего максимума);
  2) удаляет таблицу agents (подсистема «Агенты» убрана как неиспользуемая);
  3) создаёт таблицы audit_log (общий журнал действий) и subscription_payments
     (история платежей/продлений подписки);
  4) добавляет CHECK-ограничения целостности (статусы, роли, валюта, мебель);
  5) добавляет ON DELETE CASCADE для apartment_photos/apartment_events → apartments
     (раньше удаление объекта/агентства с фото падало с ошибкой целостности);
  6) включает расширение pg_trgm и строит GIN-индексы для быстрого текстового
     поиска (ILIKE по наименованию/адресу/телефону/номеру).

Шаги 4–6 специфичны для PostgreSQL и выполняются только на нём.

Revision ID: 0005_audit_payments_counter_indexes
Revises: 0004_drop_archived_status
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0005_audit_payments"
down_revision: Union[str, Sequence[str], None] = "0004_drop_archived_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    # ── 1) Счётчик номеров объектов внутри агентства ────────────────────────
    op.add_column(
        "agencies",
        sa.Column(
            "last_display_number",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    # Переносим текущий максимум номера каждого агентства, чтобы новые номера
    # продолжились без коллизий с уже выданными.
    if is_pg:
        op.execute(
            """
            UPDATE agencies a
            SET last_display_number = COALESCE((
                SELECT MAX(CAST(ap.display_id AS INTEGER))
                FROM apartments ap
                WHERE ap.agency_id = a.id AND ap.display_id ~ '^[0-9]+$'
            ), 0)
            """
        )
    else:
        op.execute(
            """
            UPDATE agencies
            SET last_display_number = COALESCE((
                SELECT MAX(CAST(ap.display_id AS INTEGER))
                FROM apartments ap
                WHERE ap.agency_id = agencies.id
                  AND ap.display_id GLOB '[0-9]*'
            ), 0)
            """
        )

    # ── 2) Удаляем таблицу agents (подсистема убрана) ───────────────────────
    # Колонка apartments.agent_id уже удалена в миграции 0002, внешних ссылок нет.
    op.drop_index("ix_agents_agency_id", table_name="agents")
    op.drop_table("agents")

    # ── 3) Новые таблицы: журнал аудита и история платежей ──────────────────
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("agency_id", sa.BigInteger(), nullable=True),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("actor_telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("actor_name", sa.String(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("target", sa.String(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_log_agency_id"), "audit_log", ["agency_id"], unique=False)
    op.create_index(op.f("ix_audit_log_action"), "audit_log", ["action"], unique=False)
    op.create_index("ix_audit_log_agency_created", "audit_log", ["agency_id", "created_at"], unique=False)

    op.create_table(
        "subscription_payments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("agency_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("days", sa.BigInteger(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("currency", sa.String(), nullable=True),
        sa.Column("method", sa.String(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("expires_at_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["agency_id"], ["agencies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_subscription_payments_agency_id"), "subscription_payments", ["agency_id"], unique=False)
    op.create_index("ix_subscription_payments_agency_created", "subscription_payments", ["agency_id", "created_at"], unique=False)

    # Шаги ниже — только PostgreSQL (прод). На прочих диалектах пропускаем.
    if not is_pg:
        return

    # ── 4) CHECK-ограничения целостности значений ───────────────────────────
    op.create_check_constraint(
        "ck_agencies_status", "agencies",
        "status IN ('trial','active','frozen','expired')",
    )
    op.create_check_constraint(
        "ck_users_role", "users",
        "role IN ('superadmin','agency_admin','agent')",
    )
    op.create_check_constraint(
        "ck_apartments_status", "apartments",
        "status IN ('active','deposit','sold')",
    )
    op.create_check_constraint(
        "ck_apartments_furniture", "apartments",
        "furniture_appliances IS NULL OR furniture_appliances IN "
        "('furniture_and_appliances','furniture_only','appliances_only','none')",
    )
    op.create_check_constraint(
        "ck_apartments_currency", "apartments",
        "length(currency) BETWEEN 1 AND 8",
    )

    # ── 5) ON DELETE CASCADE для фото и событий объектов ────────────────────
    # Раньше эти FK были без правила удаления, из-за чего удаление объекта/
    # агентства с фотографиями падало с ошибкой целостности (баг 1.1).
    op.execute("ALTER TABLE apartment_photos DROP CONSTRAINT IF EXISTS apartment_photos_apartment_id_fkey")
    op.create_foreign_key(
        "apartment_photos_apartment_id_fkey", "apartment_photos", "apartments",
        ["apartment_id"], ["id"], ondelete="CASCADE",
    )
    op.execute("ALTER TABLE apartment_photos DROP CONSTRAINT IF EXISTS apartment_photos_agency_id_fkey")
    op.create_foreign_key(
        "apartment_photos_agency_id_fkey", "apartment_photos", "agencies",
        ["agency_id"], ["id"], ondelete="CASCADE",
    )
    op.execute("ALTER TABLE apartment_events DROP CONSTRAINT IF EXISTS apartment_events_apartment_id_fkey")
    op.create_foreign_key(
        "apartment_events_apartment_id_fkey", "apartment_events", "apartments",
        ["apartment_id"], ["id"], ondelete="CASCADE",
    )
    op.execute("ALTER TABLE apartment_events DROP CONSTRAINT IF EXISTS apartment_events_agency_id_fkey")
    op.create_foreign_key(
        "apartment_events_agency_id_fkey", "apartment_events", "agencies",
        ["agency_id"], ["id"], ondelete="CASCADE",
    )

    # ── 6) Триграммный поиск (ускоряет ILIKE '%...%' без полного сканирования) ─
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_apartments_name_trgm "
        "ON apartments USING gin (lower(name) gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_apartments_address_trgm "
        "ON apartments USING gin (lower(address) gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_apartments_owner_phone_trgm "
        "ON apartments USING gin (owner_phone gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_apartments_display_id_trgm "
        "ON apartments USING gin (display_id gin_trgm_ops)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        for idx in (
            "ix_apartments_display_id_trgm",
            "ix_apartments_owner_phone_trgm",
            "ix_apartments_address_trgm",
            "ix_apartments_name_trgm",
        ):
            op.execute(f"DROP INDEX IF EXISTS {idx}")

        # Возвращаем FK без ondelete.
        for table, col, ref in (
            ("apartment_events", "agency_id", "agencies"),
            ("apartment_events", "apartment_id", "apartments"),
            ("apartment_photos", "agency_id", "agencies"),
            ("apartment_photos", "apartment_id", "apartments"),
        ):
            name = f"{table}_{col}_fkey"
            op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
            op.create_foreign_key(name, table, ref, [col], ["id"])

        for name, table in (
            ("ck_apartments_currency", "apartments"),
            ("ck_apartments_furniture", "apartments"),
            ("ck_apartments_status", "apartments"),
            ("ck_users_role", "users"),
            ("ck_agencies_status", "agencies"),
        ):
            op.drop_constraint(name, table, type_="check")

    op.drop_index("ix_subscription_payments_agency_created", table_name="subscription_payments")
    op.drop_index(op.f("ix_subscription_payments_agency_id"), table_name="subscription_payments")
    op.drop_table("subscription_payments")

    op.drop_index("ix_audit_log_agency_created", table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_action"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_agency_id"), table_name="audit_log")
    op.drop_table("audit_log")

    # Восстанавливаем таблицу agents (пустую) — на случай отката.
    op.create_table(
        "agents",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("agency_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("code", sa.String(length=5), nullable=False),
        sa.Column("last_number", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["agency_id"], ["agencies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agency_id", "code", name="uq_agents_agency_code"),
    )
    op.create_index(op.f("ix_agents_agency_id"), "agents", ["agency_id"], unique=False)

    op.drop_column("agencies", "last_display_number")
