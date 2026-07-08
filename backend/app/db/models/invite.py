"""
Таблица "invites" — приглашения сотрудников.
Админ агентства создаёт приглашение, получает код/ссылку и передаёт сотруднику.
Сотрудник открывает приглашение — и привязывается к агентству.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func, text
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
    # Многоразовость (2026-07): сколько РАЗ по коду можно вступить (лимит) и
    # сколько раз им уже воспользовались. По умолчанию 1/0 — прежнее одноразовое
    # поведение. Приглашение «исчерпано», когда used_count >= max_uses.
    max_uses: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    used_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    # used_at / used_by_telegram_id — время и Telegram ID ПОСЛЕДНЕГО вступления
    # (для многоразового кода это последний, кто вступил).
    used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    used_by_telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
