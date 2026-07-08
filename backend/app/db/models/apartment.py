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
    Boolean,
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Apartment(Base):
    __tablename__ = "apartments"
    __table_args__ = (
        # Человекочитаемый ID уникален в пределах агентства.
        UniqueConstraint("agency_id", "display_id", name="uq_apartments_agency_display"),
        # Целостность значений на уровне БД (нельзя записать «кривой» статус).
        # 'rented' («Сдан») — терминальный статус для аренды (как 'sold' для продажи).
        CheckConstraint(
            "status IN ('active','deposit','sold','rented')", name="ck_apartments_status"
        ),
        # Тип сделки: продажа или аренда (по умолчанию продажа).
        CheckConstraint(
            "deal_type IN ('sale','rent')", name="ck_apartments_deal_type"
        ),
        # Срок аренды: месяц/сутки (или NULL — для продажи).
        CheckConstraint(
            "rent_period IS NULL OR rent_period IN ('month','day')",
            name="ck_apartments_rent_period",
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
        Index("ix_apartments_agency_deal", "agency_id", "deal_type"),
        Index("ix_apartments_agency_rooms", "agency_id", "rooms"),
        Index("ix_apartments_agency_price", "agency_id", "price"),
        Index("ix_apartments_agency_created", "agency_id", "created_at"),
        Index("ix_apartments_agency_created_by", "agency_id", "created_by"),
        Index("ix_apartments_agency_deleted", "agency_id", "deleted_at"),
        # Общая база (MLS): список по ВСЕМ агентствам (без фильтра agency_id),
        # новые сверху. ix_apartments_shared_mls (создан миграцией 0029) добавлен
        # в модель для устранения дрейфа модель↔БД (L6). Частичный индекс
        # ix_apartments_mls_pool покрывает предикат shared_mls + сортировку по
        # created_at → без seq-scan+sort на экране «Общая база» (M5).
        Index("ix_apartments_shared_mls", "shared_mls"),
        Index(
            "ix_apartments_mls_pool", "created_at",
            postgresql_where=text("shared_mls AND deleted_at IS NULL"),
        ),
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
    # Статус объекта. Продажа: active (в продаже) / deposit (задаток) / sold (продан).
    # Аренда: active (свободна) / deposit (бронь) / rented (сдан).
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    # Тип сделки: 'sale' (продажа) или 'rent' (аренда). По умолчанию — продажа.
    deal_type: Mapped[str] = mapped_column(
        String, nullable=False, default="sale", server_default="sale"
    )
    # Срок аренды: 'month' (за месяц) / 'day' (за сутки). Для продажи — NULL.
    rent_period: Mapped[Optional[str]] = mapped_column(String, nullable=True)

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
    # Площадь участка в сотках (для типа «Участок»; для квартир/домов — NULL).
    land_area: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    condition: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Мебель и техника: furniture_and_appliances / furniture_only / appliances_only / none
    furniture_appliances: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Numeric(18, 2): цены в сумах бывают в десятки млрд — 12,2 (предел ~10 млрд)
    # переполнялся и ронял импорт (numeric field overflow).
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String, nullable=False, default="USD")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Внутренний комментарий (виден только команде, не отправляется при шаринге).
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Ссылка на фото объекта.
    photo_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Ссылка на источник (OLX, Telegram и т.д.).
    source_link: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Источник объявления — НАЗВАНИЕ канала/площадки (например «@realty_tashkent»).
    # Внутреннее поле: видно команде, но НЕ уходит клиенту при «поделиться».
    source: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Как объект попал в базу (для наблюдения владельца платформы):
    # manual (вручную) / link (импорт по ссылке) / bulk (массовый импорт из канала) /
    # auto (авто-импорт из отслеживаемого канала).
    added_via: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Поделиться объектом в общей базе (MLS) с другими агентствами платформы.
    # По умолчанию — нет; включается агентом галочкой (Волна 9).
    shared_mls: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

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
    # Когда объект перемещён в архив («корзину») — мягкое удаление. NULL — в базе.
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
