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

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # Роль ограничена известным набором (целостность на уровне БД).
        CheckConstraint(
            "role IN ('superadmin','agency_admin','agent')", name="ck_users_role"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # Идентификатор пользователя в Telegram — наш главный способ узнать человека.
    telegram_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True
    )
    username: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # NULL только у суперадмина. У остальных — id их агентства.
    agency_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("agencies.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    # Главный администратор агентства (тот, кого назначил суперадмин). Имеет
    # права над другими администраторами; повышенный из агента админ — нет.
    is_owner: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Деактивация сотрудника без удаления его истории.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Бот-пуш о новых совпадениях: off / instant / daily (Волна 8).
    match_notify: Mapped[str] = mapped_column(
        String, nullable=False, default="instant", server_default=text("'instant'")
    )
    # Версия сессии: бамп этого числа мгновенно делает недействительными все
    # ранее выданные пропуска (access+refresh) — «выйти со всех устройств» и
    # надёжный отзыв доступа при отключении/исключении сотрудника.
    session_epoch: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Последний «heartbeat»: когда пользователь в последний раз был в приложении.
    # Обновляется, пока приложение открыто; по нему считаем статус «в сети».
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
