"""Схемы синхронизации с Google Sheets."""
from typing import Optional

from pydantic import BaseModel, field_validator


class SheetConnectOut(BaseModel):
    # Ссылка на экран согласия Google (открыть во внешнем браузере).
    auth_url: str


class SheetStatusOut(BaseModel):
    connected: bool          # есть refresh-токен (доступ выдан)
    status: str              # connected / disconnected / error
    has_spreadsheet: bool    # таблица уже создана
    spreadsheet_url: Optional[str] = None
    sheet_title: Optional[str] = None
    error_note: Optional[str] = None


class SheetCreateIn(BaseModel):
    # Название создаваемой таблицы.
    title: str = "Realty AI — База объектов"

    @field_validator("title")
    @classmethod
    def _clean_title(cls, value: str) -> str:
        value = (value or "").strip()
        return value or "Realty AI — База объектов"
