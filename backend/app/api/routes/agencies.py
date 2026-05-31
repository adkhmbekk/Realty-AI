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
from app.schemas.agency import (
    AgencyAdminUpdate,
    AgencyCreate,
    AgencyOut,
    AgencySubscriptionUpdate,
    AgencyUpdate,
)
from app.services import agency_service

router = APIRouter(prefix="/agencies", tags=["agencies"])


@router.post("", response_model=AgencyOut)
def create_agency(
    body: AgencyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Создать агентство и назначить ему администратора."""
    agency = agency_service.create_agency_with_admin(
        db, body, creator_telegram_id=current_user.telegram_id
    )
    agency_service.attach_admins(db, [agency])
    return agency


@router.get("", response_model=List[AgencyOut])
def list_agencies(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Список всех агентств платформы (с инфо об администраторе)."""
    agencies = agency_repo.get_all(db)
    agency_service.attach_admins(db, agencies)
    return agencies


@router.patch("/{agency_id}", response_model=AgencyOut)
def update_agency(
    agency_id: int,
    body: AgencyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Переименовать агентство."""
    agency = agency_service.rename_agency(db, agency_id, body.name)
    agency_service.attach_admins(db, [agency])
    return agency


@router.delete("/{agency_id}", status_code=204)
def delete_agency(
    agency_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Удалить агентство со всеми его данными (необратимо)."""
    agency_service.delete_agency(db, agency_id)


@router.post("/{agency_id}/admin", response_model=AgencyOut)
def set_agency_admin(
    agency_id: int,
    body: AgencyAdminUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Назначить/сменить администратора агентства."""
    agency = agency_service.set_agency_admin(
        db, agency_id, body.admin_telegram_id, body.admin_username
    )
    agency_service.attach_admins(db, [agency])
    return agency


@router.post("/{agency_id}/subscription", response_model=AgencyOut)
def update_subscription(
    agency_id: int,
    body: AgencySubscriptionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Управление подпиской агентства: продлить / заморозить / активировать."""
    agency = agency_service.update_subscription(db, agency_id, body.action, body.days)
    agency_service.attach_admins(db, [agency])
    return agency
