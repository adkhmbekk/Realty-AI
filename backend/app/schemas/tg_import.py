"""
Схемы массового импорта из открытого Telegram-канала — Этап 3.1.
"""
from typing import Optional

from pydantic import BaseModel, field_validator


class TelegramScanIn(BaseModel):
    # Ссылка/username канала: @name, t.me/name, https://t.me/s/name или просто name.
    channel: str
    # Курсор пагинации: id самого старого поста предыдущей страницы (None — с начала).
    before: Optional[int] = None

    @field_validator("channel")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("empty_channel")
        return v


class TelegramScanOut(BaseModel):
    channel: str
    # Создано объектов в этой порции.
    created: int
    # Пропущено (дубли, без текста, не объявления).
    skipped: int
    # Ошибок ИИ-разбора (не считая лимита частоты).
    failed: int
    # Курсор для следующей порции (передать как before). None — больше нет.
    next_before: Optional[int] = None
    # Упёрлись в лимит частоты бесплатного Gemini — фронтенду стоит сделать паузу.
    rate_limited: bool = False
    # Канал закончился (постов больше нет).
    done: bool
