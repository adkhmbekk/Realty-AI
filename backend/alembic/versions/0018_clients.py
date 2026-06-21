"""clients, client_requests, request_matches: клиентская база + авто-подбор

Клиентская база (покупатели), их заявки («что ищет») и найденные совпадения
«заявка ↔ объект». Заявка по сути — сохранённый поиск; подбор сверяет новые
объекты с активными заявками и создаёт совпадения (уникальность пары
request/apartment не плодит дубли).

Revision ID: 0018_clients
Revises: 0017_widen_payment_amount
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0018_clients"
down_revision: Union[str, Sequence[str], None] = "0017_widen_payment_amount"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("agency_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("last_name", sa.String(), nullable=True),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["agency_id"], ["agencies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_clients_agency_id"), "clients", ["agency_id"], unique=False)
    op.create_index(op.f("ix_clients_created_by"), "clients", ["created_by"], unique=False)

    op.create_table(
        "client_requests",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("agency_id", sa.BigInteger(), nullable=False),
        sa.Column("client_id", sa.BigInteger(), nullable=False),
        sa.Column("types", sa.JSON(), nullable=True),
        sa.Column("districts", sa.JSON(), nullable=True),
        sa.Column("rooms_min", sa.Integer(), nullable=True),
        sa.Column("rooms_max", sa.Integer(), nullable=True),
        sa.Column("floor_min", sa.Integer(), nullable=True),
        sa.Column("floor_max", sa.Integer(), nullable=True),
        sa.Column("land_area_min", sa.Numeric(10, 2), nullable=True),
        sa.Column("land_area_max", sa.Numeric(10, 2), nullable=True),
        sa.Column("price_min", sa.Numeric(18, 2), nullable=True),
        sa.Column("price_max", sa.Numeric(18, 2), nullable=True),
        sa.Column("currency", sa.String(), nullable=True),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["agency_id"], ["agencies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_client_requests_agency_id"), "client_requests", ["agency_id"], unique=False)
    op.create_index(op.f("ix_client_requests_client_id"), "client_requests", ["client_id"], unique=False)

    op.create_table(
        "request_matches",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("agency_id", sa.BigInteger(), nullable=False),
        sa.Column("request_id", sa.BigInteger(), nullable=False),
        sa.Column("apartment_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="new"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["agency_id"], ["agencies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["request_id"], ["client_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["apartment_id"], ["apartments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id", "apartment_id", name="uq_match_request_apartment"),
    )
    op.create_index(op.f("ix_request_matches_agency_id"), "request_matches", ["agency_id"], unique=False)
    op.create_index(op.f("ix_request_matches_request_id"), "request_matches", ["request_id"], unique=False)
    op.create_index(op.f("ix_request_matches_apartment_id"), "request_matches", ["apartment_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_request_matches_apartment_id"), table_name="request_matches")
    op.drop_index(op.f("ix_request_matches_request_id"), table_name="request_matches")
    op.drop_index(op.f("ix_request_matches_agency_id"), table_name="request_matches")
    op.drop_table("request_matches")
    op.drop_index(op.f("ix_client_requests_client_id"), table_name="client_requests")
    op.drop_index(op.f("ix_client_requests_agency_id"), table_name="client_requests")
    op.drop_table("client_requests")
    op.drop_index(op.f("ix_clients_created_by"), table_name="clients")
    op.drop_index(op.f("ix_clients_agency_id"), table_name="clients")
    op.drop_table("clients")
