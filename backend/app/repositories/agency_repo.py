"""
Доступ к данным агентств (таблица agencies).
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.agency import Agency


def get_by_id(db: Session, agency_id: int) -> Optional[Agency]:
    return db.get(Agency, agency_id)


def get_all(db: Session) -> List[Agency]:
    return list(
        db.execute(select(Agency).order_by(Agency.created_at.desc())).scalars().all()
    )


def create(
    db: Session,
    name: str,
    created_by: Optional[int],
    subscription_days: int,
) -> Agency:
    expires_at = datetime.now(timezone.utc) + timedelta(days=subscription_days)
    agency = Agency(
        name=name,
        status="active",
        subscription_expires_at=expires_at,
        created_by=created_by,
    )
    db.add(agency)
    db.flush()  # чтобы получить сгенерированный id
    return agency
