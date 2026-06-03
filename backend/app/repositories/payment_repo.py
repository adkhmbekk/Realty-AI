"""
Доступ к данным истории платежей/продлений подписки (subscription_payments).
Все выборки фильтруются по agency_id.
"""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.subscription_payment import SubscriptionPayment


def add(
    db: Session,
    *,
    agency_id: int,
    action: str,
    days: Optional[int] = None,
    amount: Optional[Decimal] = None,
    currency: Optional[str] = None,
    method: Optional[str] = None,
    note: Optional[str] = None,
    expires_at_after: Optional[datetime] = None,
    created_by_telegram_id: Optional[int] = None,
) -> SubscriptionPayment:
    payment = SubscriptionPayment(
        agency_id=agency_id,
        action=action,
        days=days,
        amount=amount,
        currency=currency,
        method=method,
        note=note,
        expires_at_after=expires_at_after,
        created_by_telegram_id=created_by_telegram_id,
    )
    db.add(payment)
    db.flush()
    return payment


def list_for_agency(db: Session, agency_id: int, limit: int = 100) -> List[SubscriptionPayment]:
    return list(
        db.execute(
            select(SubscriptionPayment)
            .where(SubscriptionPayment.agency_id == agency_id)
            .order_by(SubscriptionPayment.created_at.desc(), SubscriptionPayment.id.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
