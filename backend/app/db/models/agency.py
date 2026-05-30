"""
Таблица "agencies" — агентства (клиенты платформы).
Это верхний уровень изоляции: к агентству привязаны его пользователи и данные.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Agency(Base):
    __tablename__ = "agencies"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # Статус подписки агентства: trial / active / frozen / expired
    status: Mapped[str] = mapped_column(String, nullable=False, default="trial")
    subscription_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    timezone: Mapped[str] = mapped_column(String, nullable=False, default="Asia/Tashkent")
    default_currency: Mapped[str] = mapped_column(String, nullable=False, default="USD")
    # telegram_id суперадмина, который создал агентство.
    created_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
