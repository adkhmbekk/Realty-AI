"""
Таблица "tg_login_codes" — одноразовые коды входа в нативное приложение через
отдельного Telegram-бота (@realtyloginbot).

Поток: приложение создаёт код (pending) → открывает t.me/бот?start=login_<code>
→ пользователь жмёт «Подтвердить» в боте → webhook помечает код confirmed и
привязывает telegram_id → приложение опрашивает /poll → код становится consumed
(одноразовый). Истёкшие/отменённые коды не выдают сессию.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TgLoginCode(Base):
    __tablename__ = "tg_login_codes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # Одноразовый секрет из ссылки (128 бит, hex). Уникален, ищем по нему.
    code: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    # pending → confirmed → consumed; терминальные cancelled / expired.
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending", server_default=text("'pending'")
    )
    # Заполняется при подтверждении (из callback_query.from) — чей это вход.
    telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    tg_first_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    tg_last_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Момент истечения (created_at + TTL). После него код не подтвердить и не выдать.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
