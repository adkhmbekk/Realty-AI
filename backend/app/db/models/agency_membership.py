"""
Таблица "agency_memberships" — членство пользователя в агентстве с ролью.

Основа многоролевости (2026-07): один человек может состоять в НЕСКОЛЬКИХ
агентствах с разными ролями (например, агент в одном агентстве и владелец
другого). Это источник правды «кто, где и в какой роли».

Совместимость: существующие поля User.agency_id / role / is_owner ОСТАЮТСЯ как
«домашнее» (текущее активное) членство — ничего в существующем коде не ломается.
Переключение между агентствами = смена активного членства (см. acting-контекст
в core/dependencies).

Уникальность (user_id, agency_id): у человека не больше одного членства в
конкретном агентстве.
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgencyMembership(Base):
    __tablename__ = "agency_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "agency_id", name="uq_membership_user_agency"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agency_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("agencies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Роль в ЭТОМ агентстве: agency_admin / agent.
    role: Mapped[str] = mapped_column(String, nullable=False)
    # Главный администратор (владелец) этого агентства.
    is_owner: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # Активно ли членство (можно временно отключить, не удаляя строку).
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
