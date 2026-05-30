"""
Бизнес-логика управления агентствами (для суперадмина).
Создание агентства сразу назначает ему администратора.
"""
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models.agency import Agency
from app.repositories import agency_repo, user_repo
from app.schemas.agency import AgencyCreate


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
