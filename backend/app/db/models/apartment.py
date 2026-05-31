"""
Таблица "apartments" — объекты недвижимости (ядро ценности продукта).

Решение из ТЗ (раздел 8.7): ЕДИНАЯ таблица со статусом вместо отдельной
таблицы-архива (как было в старом боте: apartments + apartments_archive).
Это упрощает поиск и исключает дублирование данных.

Ключевые отличия от старого бота:
  - суррогатный первичный ключ id (BIGSERIAL), глобально уникальный;
  - display_id ("SAR-0001") — человекочитаемый ID, уникален В ПРЕДЕЛАХ агентства;
  - agency_id — принадлежность агентству (изоляция данных);
  - status: active / archived / sold (вместо перекладывания строк между таблицами);
  - цена price + валюта currency (раньше было только price_usd).
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Apartment(Base):
    __tablename__ = "apartments"
    __table_args__ = (
        # Человекочитаемый ID уникален в пределах агентства.
        UniqueConstraint("agency_id", "display_id", name="uq_apartments_agency_display"),
        # Индексы под фильтры поиска (раздел 8.7 ТЗ).
        Index("ix_apartments_agency_status", "agency_id", "status"),
        Index("ix_apartments_agency_district", "agency_id", "district"),
        Index("ix_apartments_agency_type", "agency_id", "type"),
        Index("ix_apartments_agency_rooms", "agency_id", "rooms"),
        Index("ix_apartments_agency_price", "agency_id", "price"),
        Index("ix_apartments_agency_created", "agency_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agency_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agencies.id"), nullable=False, index=True
    )
    # Человекочитаемый ID, например "SAR-0001".
    display_id: Mapped[str] = mapped_column(String, nullable=False)
    # Статус объекта: active (в продаже) / archived (в архиве) / sold (продан).
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")

    name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Агент-источник объекта (из справочника agents этого агентства).
    agent_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("agents.id"), nullable=True
    )
    phone: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    district: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rooms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    floor: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_floors: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    area: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2), nullable=True)
    condition: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    furniture: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    appliances: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String, nullable=False, default="USD")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # telegram_id/id того, кто создал (для аудита). Храним id пользователя.
    created_by: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Когда объект переведён в архив (или продан). NULL — пока активен.
    archived_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
