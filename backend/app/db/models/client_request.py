"""
Таблица "client_requests" — заявки клиента («что ищет»). У клиента может быть
несколько заявок. Критерии зеркалят фильтры поиска объектов: заявка — это по
сути сохранённый поиск, по которому идёт авто-подбор объектов.

types/districts хранятся как JSON-списки (можно несколько типов/районов, как в
поиске). Числовые критерии — диапазоны «от/до». Пустая заявка (без критериев) не
допускается — иначе она «совпадала» бы со всем подряд.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ClientRequest(Base):
    __tablename__ = "client_requests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agency_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("agencies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Тип сделки заявки: 'sale' (хочет купить) или 'rent' (хочет снять). По
    # умолчанию — продажа. Подбор сверяет тип: покупателю не предлагаем аренду.
    deal_type: Mapped[str] = mapped_column(
        String, nullable=False, default="sale", server_default=text("'sale'")
    )
    # Критерии — зеркало фильтров поиска объектов.
    types: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    districts: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    rooms_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rooms_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    floor_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    floor_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    land_area_min: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    land_area_max: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    # Площадь квартиры/дома в м² («квадратура») — зеркало apartments.area.
    area_min: Mapped[Optional[float]] = mapped_column(Numeric(8, 2), nullable=True)
    area_max: Mapped[Optional[float]] = mapped_column(Numeric(8, 2), nullable=True)
    price_min: Mapped[Optional[float]] = mapped_column(Numeric(18, 2), nullable=True)
    price_max: Mapped[Optional[float]] = mapped_column(Numeric(18, 2), nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Свободная заметка («хочет светлую, не первый этаж»).
    note: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # active / fulfilled / cancelled
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="active", server_default=text("'active'")
    )
    created_by: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
