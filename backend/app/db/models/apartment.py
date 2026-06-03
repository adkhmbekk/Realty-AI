"""
Таблица "apartments" — объекты недвижимости (ядро ценности продукта).

ЕДИНАЯ таблица со статусом вместо отдельной таблицы-архива. Это упрощает
поиск и исключает дублирование данных.

Ключевые свойства:
  - суррогатный первичный ключ id (BIGSERIAL), глобально уникальный;
  - display_id ("0001") — сквозной человекочитаемый номер, уникален В ПРЕДЕЛАХ
    агентства (счётчик хранится в agencies.last_display_number);
  - agency_id — принадлежность агентству (изоляция данных);
  - status: active (в продаже) / deposit (задаток) / sold (продан);
  - цена price + валюта currency.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
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
        # Целостность значений на уровне БД (нельзя записать «кривой» статус).
        CheckConstraint(
            "status IN ('active','deposit','sold')", name="ck_apartments_status"
        ),
        CheckConstraint(
            "furniture_appliances IS NULL OR furniture_appliances IN "
            "('furniture_and_appliances','furniture_only','appliances_only','none')",
            name="ck_apartments_furniture",
        ),
        CheckConstraint(
            "length(currency) BETWEEN 1 AND 8", name="ck_apartments_currency"
        ),
        # Индексы под фильтры поиска.
        Index("ix_apartments_agency_status", "agency_id", "status"),
        Index("ix_apartments_agency_district", "agency_id", "district"),
        Index("ix_apartments_agency_type", "agency_id", "type"),
        Index("ix_apartments_agency_rooms", "agency_id", "rooms"),
        Index("ix_apartments_agency_price", "agency_id", "price"),
        Index("ix_apartments_agency_created", "agency_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agency_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("agencies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Человекочитаемый ID, например "0001".
    display_id: Mapped[str] = mapped_column(String, nullable=False)
    # Статус объекта: active (в продаже) / deposit (задаток) / sold (продан).
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")

    name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Номер собственника (конфиденциально — не показывается при шаринге).
    owner_phone: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    district: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rooms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    floor: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_floors: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    area: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2), nullable=True)
    condition: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Мебель и техника: furniture_and_appliances / furniture_only / appliances_only / none
    furniture_appliances: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String, nullable=False, default="USD")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Внутренний комментарий (виден только команде, не отправляется при шаринге).
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Ссылка на фото объекта.
    photo_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Ссылка на источник (OLX, Telegram и т.д.).
    source_link: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # id пользователя, который создал объект (для аудита).
    created_by: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Когда объект снят с продажи (продан). NULL — пока активен.
    archived_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
