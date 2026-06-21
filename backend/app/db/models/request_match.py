"""
Таблица "request_matches" — найденные совпадения «заявка клиента ↔ объект».

Уникальность (request_id, apartment_id) гарантирует, что одно совпадение не
создаётся дважды — повторный подбор или массовый импорт не плодят дубли
уведомлений. status: new (новое, не просмотрено) → seen (просмотрено) →
offered (предложено клиенту) / dismissed (отклонено).
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RequestMatch(Base):
    __tablename__ = "request_matches"
    __table_args__ = (
        UniqueConstraint("request_id", "apartment_id", name="uq_match_request_apartment"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agency_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("agencies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    request_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("client_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    apartment_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("apartments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # new / seen / offered / dismissed
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="new", server_default=text("'new'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
