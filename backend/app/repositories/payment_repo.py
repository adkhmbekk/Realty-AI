"""
Доступ к данным истории платежей/продлений подписки (subscription_payments).
Все выборки фильтруются по agency_id.
"""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import func, select
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


def totals_by_currency(db: Session, *, since: Optional[datetime] = None):
    """
    Суммарные поступления по валютам (по всем агентствам).
    Возвращает список (currency, сумма, количество записей с суммой).
    since — если задано, учитываются только платежи с этой даты (например, месяц).
    """
    conds = [SubscriptionPayment.amount > 0, SubscriptionPayment.currency.is_not(None)]
    if since is not None:
        conds.append(SubscriptionPayment.created_at >= since)
    rows = db.execute(
        select(
            SubscriptionPayment.currency,
            func.sum(SubscriptionPayment.amount),
            func.count(),
        )
        .where(*conds)
        .group_by(SubscriptionPayment.currency)
    ).all()
    return [(row[0], row[1], int(row[2])) for row in rows]


def count_all(db: Session) -> int:
    """Всего записей в истории платежей (по всем агентствам)."""
    return db.execute(
        select(func.count()).select_from(SubscriptionPayment)
    ).scalar_one()
