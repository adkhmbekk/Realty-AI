"""
Доступ к данным журнала действий по объектам (таблица apartment_events).
Все запросы изолированы по agency_id.
"""
from typing import List, Optional

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.apartment_event import ApartmentEvent


def add_event(
    db: Session,
    agency_id: int,
    apartment_id: int,
    user_id: Optional[int],
    action: str,
    note: Optional[str] = None,
) -> ApartmentEvent:
    event = ApartmentEvent(
        agency_id=agency_id,
        apartment_id=apartment_id,
        user_id=user_id,
        action=action,
        note=note,
    )
    db.add(event)
    return event


def list_for_apartment(
    db: Session, agency_id: int, apartment_id: int, limit: int = 50
) -> List[ApartmentEvent]:
    return list(
        db.execute(
            select(ApartmentEvent)
            .where(
                ApartmentEvent.agency_id == agency_id,
                ApartmentEvent.apartment_id == apartment_id,
            )
            .order_by(ApartmentEvent.created_at.desc(), ApartmentEvent.id.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )


def delete_for_apartment(db: Session, apartment_id: int) -> None:
    db.execute(
        sa_delete(ApartmentEvent).where(ApartmentEvent.apartment_id == apartment_id)
    )


def delete_for_agency(db: Session, agency_id: int) -> None:
    db.execute(sa_delete(ApartmentEvent).where(ApartmentEvent.agency_id == agency_id))
