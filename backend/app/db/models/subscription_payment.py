"""
Таблица "subscription_payments" — история платежей/продлений подписки агентства.

Каждое изменение оплаченного периода (продление на N дней или установка даты
вручную суперадмином) фиксируется отдельной строкой: что сделали, на сколько
дней, какая сумма/валюта/способ оплаты и какой стала дата окончания подписки.

Зачем: учёт денег и разбор споров «когда и сколько заплатили». Раньше у
агентства хранилась только текущая дата окончания — без истории.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SubscriptionPayment(Base):
    __tablename__ = "subscription_payments"
    __table_args__ = (
        Index("ix_subscription_payments_agency_created", "agency_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agency_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("agencies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Что сделали: "extend" (продлить на N дней) или "set" (задать дату вручную).
    action: Mapped[str] = mapped_column(String, nullable=False)
    # На сколько дней продлили (для action="extend").
    days: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    # Сумма платежа (необязательно — суперадмин может не указывать).
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Способ оплаты (наличные / перевод / Payme / Click и т.п.) — свободный текст.
    method: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Какой стала дата окончания подписки ПОСЛЕ этой операции.
    expires_at_after: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Telegram ID суперадмина, который провёл операцию.
    created_by_telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
