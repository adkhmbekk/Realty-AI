"""
Таблица "users" — все пользователи системы.
Заменяет старый allowed_users: теперь у пользователя есть роль и привязка
к агентству.

Роли:
  - superadmin    — владелец платформы (agency_id = NULL);
  - agency_admin  — администратор агентства;
  - agent         — рядовой сотрудник агентства.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # Идентификатор пользователя в Telegram — наш главный способ узнать человека.
    telegram_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True
    )
    username: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # NULL только у суперадмина. У остальных — id их агентства.
    agency_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("agencies.id"), nullable=True, index=True
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    # Деактивация сотрудника без удаления его истории.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
