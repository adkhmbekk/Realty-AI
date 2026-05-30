"""
Бизнес-логика управления агентствами (для суперадмина).
Создание агентства сразу назначает ему администратора.
"""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models.agency import Agency
from app.repositories import agency_repo, user_repo
from app.schemas.agency import AgencyCreate
from app.services import seeding_service


def create_agency_with_admin(
    db: Session, payload: AgencyCreate, creator_telegram_id: int
) -> Agency:
    # 1. Создаём агентство с открытой подпиской.
    agency = agency_repo.create(
        db,
        name=payload.name,
        created_by=creator_telegram_id,
        subscription_days=payload.subscription_days,
    )

    # 1.1. Сразу наполняем агентство значениями по умолчанию (районы, типы,
    # запасной агент) — чтобы оно было готово к работе сразу после создания.
    seeding_service.seed_agency_defaults(db, agency.id)

    # 2. Назначаем администратора агентства.
    existing = user_repo.get_by_telegram_id(db, payload.admin_telegram_id)
    if existing is not None:
        # Нельзя превращать суперадмина в админа агентства.
        if existing.role == "superadmin":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Нельзя назначить суперадмина администратором агентства.",
            )
        existing.agency_id = agency.id
        existing.role = "agency_admin"
        existing.is_active = True
        if payload.admin_username:
            existing.username = payload.admin_username
    else:
        user_repo.create(
            db,
            telegram_id=payload.admin_telegram_id,
            role="agency_admin",
            agency_id=agency.id,
            username=payload.admin_username,
        )

    db.commit()
    db.refresh(agency)
    return agency


def update_subscription(
    db: Session, agency_id: int, action: str, days: int = 30
) -> Agency:
    """
    Управление подпиской агентства (суперадмин):
      - extend   — продлить на N дней (и активировать);
      - freeze   — заморозить (доступ сотрудников ограничивается);
      - activate — снова активировать.
    """
    agency = agency_repo.get_by_id(db, agency_id)
    if agency is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Агентство не найдено."
        )

    now = datetime.now(timezone.utc)
    if action == "extend":
        add_days = days if (days and days > 0) else 30
        # Продлеваем от текущей даты окончания (если она в будущем) или от сейчас.
        base = agency.subscription_expires_at
        if base is None or base < now:
            base = now
        agency.subscription_expires_at = base + timedelta(days=add_days)
        agency.status = "active"
    elif action == "freeze":
        agency.status = "frozen"
    elif action == "activate":
        agency.status = "active"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Неизвестное действие."
        )

    db.commit()
    db.refresh(agency)
    return agency
