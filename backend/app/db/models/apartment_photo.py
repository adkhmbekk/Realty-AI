"""
Таблица "apartment_photos" — фотографии объектов недвижимости.

Сами файлы лежат на диске (Docker-том), а в базе хранится метаинформация:
к какому объекту относится фото, ключ файла в хранилище, тип содержимого
и порядок показа. Изоляция по agency_id — как и у всех рабочих таблиц.
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ApartmentPhoto(Base):
    __tablename__ = "apartment_photos"
    __table_args__ = (
        Index("ix_apartment_photos_apartment", "agency_id", "apartment_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agency_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agencies.id"), nullable=False, index=True
    )
    apartment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("apartments.id"), nullable=False
    )
    # Случайный ключ файла в хранилище (он же часть публичной ссылки).
    storage_key: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    # MIME-тип (image/jpeg, image/png, ...). Нужен для корректной отдачи.
    content_type: Mapped[str] = mapped_column(String, nullable=False, default="image/jpeg")
    # Порядок показа в галерее.
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
