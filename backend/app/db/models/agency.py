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
        # Допустимые статусы агентства (защита целостности на уровне БД).
        # 'pending' — создано «черновиком», ждёт активации по ссылке (нет админа,
        # подписка не запущена). После активации становится 'active'.
        CheckConstraint(
            "status IN ('trial','active','frozen','expired','pending')",
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
    # Тариф агентства. Сейчас у всех бесплатный 'start' (без даты окончания);
    # подписка отключена (см. core/subscription.agency_is_active). Платные тарифы
    # добавим позже — механизм оставлен на будущее.
    tariff: Mapped[str] = mapped_column(
        String, nullable=False, default="start", server_default=text("'start'")
    )
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
    # Телефон человека, который открыл агентство (для владельца платформы).
    # Необязательное, можно заполнить позже. Видит только суперадмин — НЕ
    # путать с contact_phone (публичный номер агентства для клиентов).
    client_phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Слать ли руководителям уведомление бота при добавлении нового объекта.
    # По умолчанию выключено, чтобы не засорять чат при большой команде.
    notify_new_objects: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # telegram_id суперадмина, который создал агентство.
    created_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    # ЛИЧНОЕ агентство владельца платформы: telegram_id суперадмина-владельца.
    # NULL — обычное клиентское агентство. Если задан — этот суперадмин может
    # «войти» в агентство как его главный админ (через acting-контекст), а
    # подписка для таких агентств не действует (всегда активно).
    owner_telegram_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    # ОБЩЕЕ агентство платформы («Realty AI»): в него могут «входить» ВСЕ владельцы
    # (суперадмины) и совместно вести общую базу МЛС. Подписка не действует
    # (всегда активно). Одно на платформу; создаётся при старте (ensure_shared_agency).
    is_shared: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # Для агентства-черновика (status='pending'): на сколько дней дать подписку
    # при активации. После активации обнуляется (NULL).
    pending_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Сквозной счётчик номеров объектов агентства (display_id «0001», «0002», …).
    # Раньше эту роль играл «служебный агент» в таблице agents; теперь счётчик
    # живёт прямо в агентстве и увеличивается атомарно (см. agency_repo).
    last_display_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    # Заморожено вместе с архивацией владельца (опция «заморозить агентства»).
    # NULL — обычное живое агентство. Если задан — агентство «в архиве»: сотрудники
    # теряют к нему доступ (не видят в своём хабе, агентские API отвечают отказом),
    # пока владельца не восстановят (тогда archived_at снимается и владение
    # переходит выбранному юзеру).
    archived_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
