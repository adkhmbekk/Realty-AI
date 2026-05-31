"""
Таблица "apartment_events" — журнал действий по объекту недвижимости.

Фиксирует, кто и что сделал с объектом: создал, изменил, сменил статус.
Нужно для прозрачности работы команды (как в старом боте знали, кто добавил;
теперь знаем и кто менял, и кто отметил «продан»).
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ApartmentEvent(Base):
    __tablename__ = "apartment_events"
    __table_args__ = (
        Index("ix_apartment_events_apartment", "agency_id", "apartment_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agency_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agencies.id"), nullable=False, index=True
    )
    apartment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("apartments.id"), nullable=False
    )
    # Кто совершил действие (id пользователя). NULL — если автор неизвестен.
    user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    # Тип действия: created / updated / status.
    action: Mapped[str] = mapped_column(String, nullable=False)
    # Доп. детали: для updated — изменённые поля; для status — новый статус.
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
