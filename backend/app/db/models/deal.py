"""
Таблица "deals" — сделки и комиссия (Волна 5).

Сделка связывает клиента (покупателя) и объект, проходит воронку этапов
(new→interested→shown→price_agreed→deposit→contract→sold, плюс cancelled).
Хранит цену, комиссию и ответственного агента (для расчёта по сотрудникам), а
также чьё агентство выставило объект (seller_agency_id) — задел под кросс-
агентскую сделку (Волна 9). Сейчас сделки внутри одного агентства (#19).
«Деньги» считаются с этапа «задаток» (#22) — это используется в аналитике.
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
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Этапы воронки сделки (#17) + терминальный cancelled (сделка сорвалась).
DEAL_STAGES = (
    "new", "interested", "shown", "price_agreed", "deposit", "contract", "sold", "cancelled",
)
# С какого этапа сделка считается «принесла деньги» (#22 — на задатке).
DEAL_REVENUE_STAGES = ("deposit", "contract", "sold")


class Deal(Base):
    __tablename__ = "deals"
    __table_args__ = (
        CheckConstraint(
            "stage IN ('new','interested','shown','price_agreed','deposit','contract','sold','cancelled')",
            name="ck_deals_stage",
        ),
        Index("ix_deals_agency_stage", "agency_id", "stage"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agency_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    apartment_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("apartments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    stage: Mapped[str] = mapped_column(
        String, nullable=False, default="new", server_default=text("'new'")
    )
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    commission: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    commission_currency: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Ответственный агент (для комиссии по сотрудникам, #23).
    agent_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    # Чьё агентство выставило объект (#20). Внутри агентства = agency_id.
    seller_agency_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Когда сделка закрыта (этап sold). NULL — ещё в работе.
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
