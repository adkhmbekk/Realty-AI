"""
Таблица "agency_sheets" — связь агентства с его Google-таблицей.

Одна строка на агентство. Хранит:
  - refresh_token Google (доступ к таблице, выданный владельцем агентства);
  - id/URL созданной таблицы;
  - статус подключения и служебные метки для будущей двусторонней синхронизации.

ВАЖНО (на будущее, перед продажей в аренду): refresh_token сейчас хранится как
есть. Для продакшена его следует шифровать (ключ — в secret_dir).
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgencySheet(Base):
    __tablename__ = "agency_sheets"

    agency_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agencies.id", ondelete="CASCADE"), primary_key=True
    )
    # Google refresh-токен (доступ к таблице от имени владельца агентства).
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Созданная таблица.
    spreadsheet_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    spreadsheet_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sheet_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # connected (подключено) / disconnected (нет) / error.
    status: Mapped[str] = mapped_column(String, nullable=False, default="disconnected")
    error_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Снимок последней синхронизации: {"<id>": {field: value, ...}} — базовая точка
    # для 3-стороннего merge (понять, с какой стороны пришло изменение).
    snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # Метки двусторонней синхронизации.
    last_modified_time: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
