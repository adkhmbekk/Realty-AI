"""
Таблица "dictionaries" — гибкие справочники агентства.

Заменяет захардкоженные списки из старого бота (DISTRICTS и т.п.).
Один ряд = одно значение справочника определённой категории, принадлежащее
конкретному агентству.

Примеры категорий (category):
  - "district"       — районы (Чиланзарский, Юнусабадский, ...);
  - "property_type"  — типы недвижимости (Квартира, Дом, ...);
  - "condition"      — состояние (Евроремонт, Среднее, ...);
  - "furniture"      — мебель;
  - "source"         — источник.

Каждое агентство ведёт свои справочники независимо от других.
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Dictionary(Base):
    __tablename__ = "dictionaries"
    # В пределах агентства одно и то же значение в одной категории не дублируется.
    __table_args__ = (
        UniqueConstraint(
            "agency_id", "category", "value", name="uq_dictionaries_agency_cat_value"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agency_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agencies.id"), nullable=False, index=True
    )
    # Категория справочника (district / property_type / condition / ...).
    category: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # Само значение (например "Чиланзарский").
    value: Mapped[str] = mapped_column(String, nullable=False)
    # Порядок отображения в списках/формах.
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
