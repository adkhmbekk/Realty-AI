"""
Таблица "phone_otp_codes" — одноразовые SMS-коды входа по номеру телефона.

Поток: приложение просит код (/auth/phone/request) → шлём SMS с 6-значным кодом
(TTL ~5 минут) → пользователь вводит код (/auth/phone/verify) → выдаём сессию
(вход в существующий аккаунт по номеру или создание нового личного). Код
одноразовый (pending → consumed); неверные вводы считаем в attempts — после
лимита код гасится (защита от перебора).
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PhoneOtpCode(Base):
    __tablename__ = "phone_otp_codes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # Нормализованный номер (+цифры, E.164) — по нему ищем актуальный код.
    phone: Mapped[str] = mapped_column(String, index=True, nullable=False)
    # 6-значный код из SMS. НЕ уникален глобально (уникальность в рамках номера
    # обеспечивает логика: старые pending-коды гасятся при выдаче нового).
    code: Mapped[str] = mapped_column(String, nullable=False)
    # pending → consumed; терминальный expired (истёк / перебор попыток / замещён).
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending", server_default=text("'pending'")
    )
    # Счётчик НЕВЕРНЫХ вводов кода (защита от перебора: после лимита код гасится).
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Момент истечения (created_at + TTL). После него код не принимается.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
