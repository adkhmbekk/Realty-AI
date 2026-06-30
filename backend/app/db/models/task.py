"""
Таблица "tasks" — задачи по клиенту (Волна 4).

Задача привязана к клиенту: «позвонить», «показ», «отправить предложение».
kind: manual (создал агент) / auto (создал планировщик — «клиент молчит N дней»).
status: open → done. deadline — срок (день, может быть пустым).
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("status IN ('open','done')", name="ck_tasks_status"),
        CheckConstraint("kind IN ('manual','auto')", name="ck_tasks_kind"),
        Index("ix_tasks_agency_status", "agency_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agency_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # open / done
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="open", server_default=text("'open'")
    )
    # manual (агент) / auto (планировщик «молчит N дней»)
    kind: Mapped[str] = mapped_column(
        String, nullable=False, default="manual", server_default=text("'manual'")
    )
    created_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    done_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
