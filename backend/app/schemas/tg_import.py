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
    # Создано объектов на этой странице.
    created: int
    # Пропущено (дубли, без текста, не объявления, ошибки).
    skipped: int
    # Сколько постов было на странице.
    scanned: int
    # Курсор для следующей страницы (передать как before). None — больше нет.
    next_before: Optional[int] = None
    # Канал закончился (постов больше нет).
    done: bool
