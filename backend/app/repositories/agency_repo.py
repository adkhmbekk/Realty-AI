"""
Доступ к данным агентств (таблица agencies).
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import delete as sa_delete
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models.agency import Agency
from app.db.models.apartment import Apartment
from app.db.models.apartment_event import ApartmentEvent
from app.db.models.apartment_photo import ApartmentPhoto
from app.db.models.dictionary import Dictionary
from app.db.models.invite import Invite
from app.db.models.subscription_payment import SubscriptionPayment


def get_by_id(db: Session, agency_id: int) -> Optional[Agency]:
    return db.get(Agency, agency_id)


def get_all(db: Session) -> List[Agency]:
    return list(
        db.execute(select(Agency).order_by(Agency.created_at.desc())).scalars().all()
    )


def get_clients(db: Session) -> List[Agency]:
    """
    Только КЛИЕНТСКИЕ агентства платформы (owner_telegram_id IS NULL) — те, с
    кого взимается плата. Личные агентства владельцев сюда НЕ входят: они живут
    отдельно (см. get_by_owner), чтобы не мешаться в платформенном списке.
    """
    return list(
        db.execute(
            select(Agency)
            .where(Agency.owner_telegram_id.is_(None), Agency.is_shared.is_(False))
            .order_by(Agency.created_at.desc())
        )
        .scalars()
        .all()
    )


def get_by_owner(db: Session, owner_telegram_id: int) -> List[Agency]:
    """Личные агентства владельца платформы (по agencies.owner_telegram_id)."""
    return list(
        db.execute(
            select(Agency)
            .where(Agency.owner_telegram_id == owner_telegram_id)
            .order_by(Agency.created_at.desc())
        )
        .scalars()
        .all()
    )


def get_shared(db: Session) -> List[Agency]:
    """Общие агентства платформы (is_shared=True): в них могут «входить» ВСЕ
    владельцы (суперадмины). Обычно одно — «Realty AI»."""
    return list(
        db.execute(
            select(Agency)
            .where(Agency.is_shared.is_(True))
            .order_by(Agency.created_at.desc())
        )
        .scalars()
        .all()
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


def create_pending(
    db: Session, name: str, created_by: Optional[int], subscription_days: int
) -> Agency:
    """Создать агентство-черновик (ожидает активации по ссылке): без админа и
    без запущенной подписки. Срок подписки запоминаем в pending_days и применяем
    в момент активации."""
    agency = Agency(
        name=name,
        status="pending",
        subscription_expires_at=None,
        activated_at=None,
        pending_days=subscription_days,
        created_by=created_by,
    )
    db.add(agency)
    db.flush()
    return agency


def next_display_number(db: Session, agency_id: int) -> Optional[int]:
    """
    Атомарно увеличить сквозной счётчик номеров агентства и вернуть новый номер.

    Один SQL-оператор UPDATE ... RETURNING исключает гонки: два одновременных
    создания объектов получат разные номера. Возвращает None, если агентства
    не существует.
    """
    stmt = (
        update(Agency)
        .where(Agency.id == agency_id)
        .values(last_display_number=Agency.last_display_number + 1)
        .returning(Agency.last_display_number)
        .execution_options(synchronize_session=False)
    )
    return db.execute(stmt).scalar_one_or_none()


def delete_with_data(db: Session, agency: Agency) -> None:
    """
    Полностью удалить агентство и все его данные.

    Порядок удаления учитывает внешние ключи. ВАЖНО: сначала удаляем
    apartment_photos (иначе они держат objekты ссылкой) и журнал действий, затем
    объекты, приглашения, справочники, историю платежей, пользователей и само
    агентство. Файлы фотографий с диска удаляются отдельно (см.
    photo_service.purge_agency, вызывается до этого метода в agency_service).
    """
    agency_id = agency.id
    db.execute(sa_delete(ApartmentPhoto).where(ApartmentPhoto.agency_id == agency_id))
    db.execute(sa_delete(ApartmentEvent).where(ApartmentEvent.agency_id == agency_id))
    db.execute(sa_delete(Apartment).where(Apartment.agency_id == agency_id))
    db.execute(sa_delete(Invite).where(Invite.agency_id == agency_id))
    db.execute(sa_delete(Dictionary).where(Dictionary.agency_id == agency_id))
    db.execute(
        sa_delete(SubscriptionPayment).where(SubscriptionPayment.agency_id == agency_id)
    )
    # СОТРУДНИКОВ здесь НЕ удаляем — это стирало бы их аккаунты и членства в ДРУГИХ
    # агентствах по каскаду (утечка данных между тенантами). Вызывающий заранее
    # переселяет/отвязывает их (agency_service._relocate_agency_members); FK
    # users.agency_id (SET NULL) отвяжет любую пропущенную строку. Членства в этом
    # агентстве уходят каскадом вместе с агентством.
    db.delete(agency)
