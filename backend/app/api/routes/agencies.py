"""
Эндпоинты управления агентствами (только суперадмин).
"""
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import require_superadmin
from app.db.models.user import User
from app.db.session import get_db
from app.repositories import agency_repo
from app.schemas.agency import AgencyCreate, AgencyOut, AgencySubscriptionUpdate
from app.services import agency_service

router = APIRouter(prefix="/agencies", tags=["agencies"])


@router.post("", response_model=AgencyOut)
def create_agency(
    body: AgencyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Создать агентство и назначить ему администратора."""
    return agency_service.create_agency_with_admin(
        db, body, creator_telegram_id=current_user.telegram_id
    )


@router.get("", response_model=List[AgencyOut])
def list_agencies(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Список всех агентств платформы."""
    return agency_repo.get_all(db)


@router.post("/{agency_id}/subscription", response_model=AgencyOut)
def update_subscription(
    agency_id: int,
    body: AgencySubscriptionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Управление подпиской агентства: продлить / заморозить / активировать."""
    return agency_service.update_subscription(db, agency_id, body.action, body.days)
