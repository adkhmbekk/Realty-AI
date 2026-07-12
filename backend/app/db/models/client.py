"""
Таблица "clients" — клиенты (покупатели) агентства.

Каждый клиент принадлежит агентству и «закреплён» за агентом (created_by):
агент видит только своих клиентов, главный администратор — всех (и может
переназначить владельца, если агент уволился). Телефон клиента —
конфиденциальные данные (как owner_phone у объекта), клиентам не показывается.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agency_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("agencies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    last_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Приоритет: hot / warm / cold (или NULL — не задан). «Светофор» для агента.
    priority: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Источник: откуда пришёл клиент (Instagram, OLX, рекомендация…). Свободный текст.
    source: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Агент-владелец клиента. Личные клиенты: агент видит только своих. FK с
    # ondelete=SET NULL: при удалении агента клиент не «повисает» на несуществующем
    # id (иначе он становился невидим всем и требовал ручного переназначения).
    created_by: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # active / archived
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="active", server_default=text("'active'")
    )
    # Приглушить уведомления о новых совпадениях по этому клиенту (Волна 8).
    muted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
