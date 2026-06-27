"""
Эндпоинты управления агентствами (только суперадмин).
"""
from typing import List

from fastapi import APIRouter, Depends, status

from sqlalchemy.orm import Session

from app.core.dependencies import require_superadmin
from app.core.errors import AppError
from app.db.models.user import User
from app.db.session import get_db
from app.repositories import agency_repo
from app.schemas.agency import (
    AgencyActivityOut,
    AgencyAdminUpdate,
    AgencyAuditOut,
    AgencyCreate,
    AgencyOut,
    AgencyPaymentOut,
    AgencyUsageOut,
    PaymentsSummaryOut,
    AgencySubscriptionUpdate,
    AgencyUpdate,
    PersonalAgencyCreate,
)
from app.schemas.auth import AuthResponse
from app.services import agency_service, agency_usage_service, auth_service

router = APIRouter(prefix="/agencies", tags=["agencies"])


@router.post("", response_model=AgencyOut)
def create_agency(
    body: AgencyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Создать агентство и назначить ему администратора."""
    agency = agency_service.create_agency_with_admin(db, body, actor=current_user)
    agency_service.attach_admins(db, [agency])
    return agency


@router.get("", response_model=List[AgencyOut])
def list_agencies(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Список КЛИЕНТСКИХ агентств платформы (личные агентства владельцев сюда
    не входят — они в /agencies/mine)."""
    agencies = agency_repo.get_clients(db)
    agency_service.attach_admins(db, agencies)
    return agencies


# ВНИМАНИЕ: /usage объявлен ДО /{agency_id}/..., чтобы слово не приняли за id.
@router.get("/usage", response_model=List[AgencyUsageOut])
def agencies_usage(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Сводка использования по всем клиентским агентствам (для «светофора» в списке)."""
    return agency_usage_service.usage_list(db)


# ── Личные агентства владельца платформы ────────────────────────────────────
# ВНИМАНИЕ: /mine объявлены ДО /{agency_id}/..., иначе "mine" примут за id.

@router.get("/mine", response_model=List[AgencyOut])
def my_agencies(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Список ЛИЧНЫХ агентств текущего владельца платформы."""
    agencies = agency_service.list_personal_agencies(db, current_user.telegram_id)
    agency_service.attach_admins(db, agencies)
    return agencies


@router.post("/mine", response_model=AgencyOut)
def create_my_agency(
    body: PersonalAgencyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Создать личное агентство (владелец сам станет его главным админом)."""
    agency = agency_service.create_personal_agency(db, body.name, current_user)
    agency_service.attach_admins(db, [agency])
    return agency


@router.post("/{agency_id}/enter", response_model=AuthResponse)
def enter_agency(
    agency_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """
    «Войти» в своё личное агентство: выдать сессию главного админа этого
    агентства (acting-контекст). Войти можно только в агентство, которым
    владеешь (owner_telegram_id == telegram_id).
    """
    agency = agency_repo.get_by_id(db, agency_id)
    if agency is None or agency.owner_telegram_id != current_user.telegram_id:
        raise AppError("agency_not_owned", status.HTTP_403_FORBIDDEN)
    return auth_service.build_auth_response(
        db, current_user, act_as_agency_id=agency_id
    )


@router.patch("/{agency_id}", response_model=AgencyOut)
def update_agency(
    agency_id: int,
    body: AgencyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Переименовать агентство."""
    agency = agency_service.rename_agency(db, agency_id, body.name, actor=current_user)
    agency_service.attach_admins(db, [agency])
    return agency


@router.delete("/{agency_id}", status_code=204)
def delete_agency(
    agency_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Удалить агентство со всеми его данными (необратимо)."""
    agency_service.delete_agency(db, agency_id, actor=current_user)


@router.post("/{agency_id}/admin", response_model=AgencyOut)
def set_agency_admin(
    agency_id: int,
    body: AgencyAdminUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Назначить/сменить администратора агентства."""
    agency = agency_service.set_agency_admin(
        db, agency_id, body.admin_telegram_id, body.admin_username, actor=current_user
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
    """Управление подпиской агентства: продлить / задать дату / заморозить / активировать."""
    agency = agency_service.update_subscription(
        db,
        agency_id,
        body.action,
        body.days,
        body.expires_at,
        amount=body.amount,
        currency=body.currency,
        method=body.method,
        note=body.note,
        actor=current_user,
    )
    agency_service.attach_admins(db, [agency])
    return agency


# ВНИМАНИЕ: /payments/summary объявлен ДО /{agency_id}/payments.
@router.get("/payments/summary", response_model=PaymentsSummaryOut)
def payments_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Свод платежей по всем агентствам: итоги по валютам (всего и за месяц)."""
    return agency_service.payments_summary(db)


@router.get("/{agency_id}/payments", response_model=List[AgencyPaymentOut])
def list_payments(
    agency_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """История платежей/продлений подписки агентства."""
    return agency_service.list_payments(db, agency_id)


@router.get("/{agency_id}/audit", response_model=List[AgencyAuditOut])
def list_audit(
    agency_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Журнал действий по агентству (вход, приглашения, роли, подписка и т.д.)."""
    return agency_service.list_audit(db, agency_id)


@router.get("/{agency_id}/activity", response_model=AgencyActivityOut)
def agency_activity(
    agency_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Подробный отчёт об активности агентства: объекты по дням, как добавляют,
    активность команды, по сотрудникам."""
    return agency_usage_service.activity(db, agency_id)
