"""
Схемы массового импорта из открытого Telegram-канала — Этап 3.1.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


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
    # Архивировано (помечено проданным через reply «продано/неактуально»).
    archived: int = 0
    # Курсор для следующей порции (передать как before). None — больше нет.
    next_before: Optional[int] = None
    # Упёрлись в лимит частоты бесплатного Gemini — фронтенду стоит сделать паузу.
    rate_limited: bool = False
    # Канал закончился (постов больше нет).
    done: bool


# ── Фоновое слежение за каналом (авто-импорт) ───────────────────────────────
class WatchIn(BaseModel):
    channel: str

    @field_validator("channel")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("empty_channel")
        return v


class WatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel: str
    enabled: bool
    last_post_id: int
    last_checked_at: Optional[datetime] = None
    created_at: datetime
