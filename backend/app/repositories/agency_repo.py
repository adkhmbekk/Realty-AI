"""
Доступ к данным агентств (таблица agencies).
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.agency import Agency
from app.db.models.agent import Agent
from app.db.models.apartment import Apartment
from app.db.models.apartment_event import ApartmentEvent
from app.db.models.dictionary import Dictionary
from app.db.models.invite import Invite
from app.db.models.user import User


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
        activated_at=datetime.now(timezone.utc),
        created_by=created_by,
    )
    db.add(agency)
    db.flush()  # чтобы получить сгенерированный id
    return agency


def delete_with_data(db: Session, agency: Agency) -> None:
    """
    Полностью удалить агентство и все его данные.

    Порядок удаления важен из-за внешних ключей (create_all без ON DELETE
    CASCADE): сначала строки, которые ссылаются на других, затем — на кого
    ссылаются. Журнал действий → объекты → приглашения → агенты → справочники
    → пользователи → само агентство.
    """
    agency_id = agency.id
    db.execute(sa_delete(ApartmentEvent).where(ApartmentEvent.agency_id == agency_id))
    db.execute(sa_delete(Apartment).where(Apartment.agency_id == agency_id))
    db.execute(sa_delete(Invite).where(Invite.agency_id == agency_id))
    db.execute(sa_delete(Agent).where(Agent.agency_id == agency_id))
    db.execute(sa_delete(Dictionary).where(Dictionary.agency_id == agency_id))
    db.execute(sa_delete(User).where(User.agency_id == agency_id))
    db.delete(agency)
