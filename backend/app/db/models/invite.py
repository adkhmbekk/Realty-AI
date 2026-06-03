"""
Таблица "invites" — приглашения сотрудников.
Админ агентства создаёт приглашение, получает код/ссылку и передаёт сотруднику.
Сотрудник открывает приглашение — и привязывается к агентству.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # Случайный уникальный код приглашения.
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    agency_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("agencies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Какую роль получит приглашённый (по умолчанию — рядовой агент).
    role: Mapped[str] = mapped_column(String, nullable=False, default="agent")
    created_by: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    used_by_telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
