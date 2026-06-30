"""
Таблица "client_activities" — лента действий по клиенту (Волна 3).

Каждая запись — одно действие агента с клиентом: звонок (call), показ (show),
встреча (meeting), сообщение (message), заметка (note), смена цены (price_change).
Хронология копится; используется для истории и (в будущем) ИИ-подсказок
(«клиент молчит N дней»).
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ClientActivity(Base):
    __tablename__ = "client_activities"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('call','show','meeting','message','note','price_change')",
            name="ck_client_activities_kind",
        ),
        Index("ix_client_activities_client_created", "client_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agency_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # call / show / meeting / message / note / price_change
    kind: Mapped[str] = mapped_column(String, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
