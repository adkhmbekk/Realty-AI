"""
Таблица "agencies" — агентства (клиенты платформы).
Это верхний уровень изоляции: к агентству привязаны его пользователи и данные.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Agency(Base):
    __tablename__ = "agencies"
    __table_args__ = (
        # Допустимые статусы подписки агентства (защита целостности на уровне БД).
        CheckConstraint(
            "status IN ('trial','active','frozen','expired')",
            name="ck_agencies_status",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # name — внутреннее имя, которое задаёт суперадмин (обычно имя человека,
    # с которым он договорился об аренде проекта).
    name: Mapped[str] = mapped_column(String, nullable=False)
    # project_name — публичное название проекта, которое задаёт сам админ
    # агентства (как он хочет назвать свой сервис). Может быть пустым.
    project_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Статус подписки агентства: trial / active / frozen / expired
    status: Mapped[str] = mapped_column(String, nullable=False, default="trial")
    subscription_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Когда владельцу в последний раз отправили предупреждение об окончании
    # подписки (чтобы не дублировать его слишком часто).
    subscription_warned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Когда агентству в последний раз предоставили доступ (активация подписки).
    activated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    timezone: Mapped[str] = mapped_column(String, nullable=False, default="Asia/Tashkent")
    default_currency: Mapped[str] = mapped_column(String, nullable=False, default="USD")
    # Контактный телефон агентства (номер главного админа). Подставляется
    # вместо номера собственника, когда сотрудник делится объектом с клиентом.
    contact_phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Слать ли руководителям уведомление бота при добавлении нового объекта.
    # По умолчанию выключено, чтобы не засорять чат при большой команде.
    notify_new_objects: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # telegram_id суперадмина, который создал агентство.
    created_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    # Сквозной счётчик номеров объектов агентства (display_id «0001», «0002», …).
    # Раньше эту роль играл «служебный агент» в таблице agents; теперь счётчик
    # живёт прямо в агентстве и увеличивается атомарно (см. agency_repo).
    last_display_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
