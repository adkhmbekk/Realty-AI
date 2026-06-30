"""
Таблица "watched_channels" — Telegram-каналы, которые агентство «слушает»:
сервер периодически проверяет их и сам добавляет новые объявления в базу.

last_post_id — id самого свежего поста, который мы уже учли. На каждом тике
берём только посты НОВЕЕ него (id > last_post_id), импортируем по порядку и
двигаем курсор вперёд. Так не пропускаем и не дублируем.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WatchedChannel(Base):
    __tablename__ = "watched_channels"
    __table_args__ = (
        UniqueConstraint("agency_id", "channel", name="uq_watched_agency_channel"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agency_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("agencies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Нормализованный username канала (без @).
    channel: Mapped[str] = mapped_column(String, nullable=False)
    # Курсор: id самого свежего учтённого поста.
    last_post_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    # Делиться авто-импортированными объектами в общей базе (MLS).
    share_mls: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # Кто включил слежение (для created_by новых объектов).
    created_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
