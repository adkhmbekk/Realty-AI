"""
Эндпоинты настроек собственного агентства.

Читать настройки может любой сотрудник агентства (например, чтобы форма
объекта подставляла валюту по умолчанию). Менять — только администратор
агентства. Агентство берётся из пропуска текущего пользователя (изоляция).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import require_agency_admin, require_agency_member
from app.db.models.user import User
from app.db.session import get_db
from app.repositories import agency_repo
from app.schemas.agency import AgencySettingsOut, AgencySettingsUpdate
from app.services import agency_service

router = APIRouter(prefix="/agency", tags=["agency-settings"])


@router.get("/settings", response_model=AgencySettingsOut)
def get_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Текущие настройки своего агентства (валюта по умолчанию, часовой пояс)."""
    return agency_repo.get_by_id(db, current_user.agency_id)


@router.patch("/settings", response_model=AgencySettingsOut)
def update_settings(
    body: AgencySettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_admin),
):
    """Изменить настройки агентства (только администратор)."""
    return agency_service.update_settings(
        db,
        current_user.agency_id,
        project_name=body.project_name,
        timezone_value=body.timezone,
        default_currency=body.default_currency,
        contact_phone=body.contact_phone,
    )
