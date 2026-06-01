"""
Бизнес-логика управления агентствами (для суперадмина).
Создание агентства сразу назначает ему администратора.
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import status
from sqlalchemy.orm import Session

from app.db.models.agency import Agency
from app.db.models.user import User
from app.core.errors import AppError
from app.core.subscription import agency_is_active
from app.repositories import agency_repo, user_repo
from app.schemas.agency import AgencyCreate
from app.services import seeding_service


def _admin_display_name(u: Optional[User]) -> Optional[str]:
    if u is None:
        return None
    if u.full_name:
        return u.full_name
    if u.username:
        return "@" + u.username
    return f"ID {u.telegram_id}"


def attach_admins(db: Session, agencies: List[Agency]) -> None:
    """
    Проставить агентствам инфо об их администраторе (для панели суперадмина):
    admin_telegram_id и admin_name. Берём первого по порядку администратора
    агентства (agency_admin). Эти атрибуты только для вывода, в БД их нет.
    """
    for agency in agencies:
        admin = None
        for member in user_repo.get_by_agency(db, agency.id):
            if member.role == "agency_admin":
                admin = member
                break
        agency.admin_telegram_id = admin.telegram_id if admin else None
        agency.admin_name = _admin_display_name(admin)


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

    # 2. Назначаем администратора агентства (он же — главный админ, is_owner).
    existing = user_repo.get_by_telegram_id(db, payload.admin_telegram_id)
    if existing is not None:
        # Нельзя превращать суперадмина в админа агентства.
        if existing.role == "superadmin":
            raise AppError(
                "cannot_assign_superadmin_as_admin", status.HTTP_400_BAD_REQUEST
            )
        existing.agency_id = agency.id
        existing.role = "agency_admin"
        existing.is_active = True
        existing.is_owner = True
        if payload.admin_username:
            existing.username = payload.admin_username
    else:
        user_repo.create(
            db,
            telegram_id=payload.admin_telegram_id,
            role="agency_admin",
            agency_id=agency.id,
            username=payload.admin_username,
            is_owner=True,
        )

    db.commit()
    db.refresh(agency)
    return agency


def update_subscription(
    db: Session,
    agency_id: int,
    action: str,
    days: int = 30,
    expires_at: Optional[datetime] = None,
) -> Agency:
    """
    Управление подпиской агентства (суперадмин):
      - extend   — продлить на N дней (и активировать);
      - set      — задать дату окончания подписки вручную (и активировать);
      - freeze   — заморозить (доступ сотрудников ограничивается);
      - activate — снова активировать.
    """
    agency = agency_repo.get_by_id(db, agency_id)
    if agency is None:
        raise AppError("agency_not_found", status.HTTP_404_NOT_FOUND)

    now = datetime.now(timezone.utc)
    was_active = agency_is_active(agency)
    if action == "extend":
        add_days = days if (days and days > 0) else 30
        # Продлеваем от текущей даты окончания (если она в будущем) или от сейчас.
        base = agency.subscription_expires_at
        if base is None or base < now:
            base = now
        agency.subscription_expires_at = base + timedelta(days=add_days)
        agency.status = "active"
        if not was_active:
            agency.activated_at = now
    elif action == "set":
        if expires_at is None:
            raise AppError(
                "subscription_end_date_required", status.HTTP_400_BAD_REQUEST
            )
        # Приводим к timezone-aware (UTC), если дата без зоны.
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        agency.subscription_expires_at = expires_at
        agency.status = "active"
        if not was_active:
            agency.activated_at = now
    elif action == "freeze":
        agency.status = "frozen"
    elif action == "activate":
        agency.status = "active"
        agency.activated_at = now
    else:
        raise AppError("unknown_action", status.HTTP_400_BAD_REQUEST)

    db.commit()
    db.refresh(agency)
    return agency


def _get_agency_or_404(db: Session, agency_id: int) -> Agency:
    agency = agency_repo.get_by_id(db, agency_id)
    if agency is None:
        raise AppError("agency_not_found", status.HTTP_404_NOT_FOUND)
    return agency


def rename_agency(db: Session, agency_id: int, name: Optional[str]) -> Agency:
    """Переименовать агентство (суперадмин)."""
    agency = _get_agency_or_404(db, agency_id)
    if name is not None:
        new_name = name.strip()
        if not new_name:
            raise AppError("agency_name_empty", status.HTTP_400_BAD_REQUEST)
        agency.name = new_name
    db.commit()
    db.refresh(agency)
    return agency


def delete_agency(db: Session, agency_id: int) -> None:
    """
    Удалить агентство со всеми его данными (объекты, команда, приглашения,
    справочники, агенты). Необратимо. Только суперадмин.
    """
    agency = _get_agency_or_404(db, agency_id)
    agency_repo.delete_with_data(db, agency)
    db.commit()


def set_agency_admin(
    db: Session, agency_id: int, admin_telegram_id: int, admin_username: Optional[str]
) -> Agency:
    """
    Назначить/сменить администратора агентства (суперадмин).

    Указанный человек (по Telegram ID) становится администратором этого
    агентства: если он уже есть в системе — привязываем к агентству и делаем
    админом; если нет — создаём. Существующие администраторы не понижаются
    автоматически (агентство может иметь нескольких админов).
    """
    agency = _get_agency_or_404(db, agency_id)

    # Главный админ в агентстве должен быть один: снимаем флаг со всех текущих.
    for member in user_repo.get_by_agency(db, agency_id):
        if member.is_owner:
            member.is_owner = False

    existing = user_repo.get_by_telegram_id(db, admin_telegram_id)
    if existing is not None:
        if existing.role == "superadmin":
            raise AppError(
                "cannot_assign_superadmin_as_admin", status.HTTP_400_BAD_REQUEST
            )
        if existing.agency_id not in (None, agency_id):
            raise AppError(
                "user_already_in_another_agency", status.HTTP_400_BAD_REQUEST
            )
        existing.agency_id = agency_id
        existing.role = "agency_admin"
        existing.is_active = True
        existing.is_owner = True
        if admin_username:
            existing.username = admin_username
    else:
        user_repo.create(
            db,
            telegram_id=admin_telegram_id,
            role="agency_admin",
            agency_id=agency_id,
            username=admin_username,
            is_owner=True,
        )

    db.commit()
    db.refresh(agency)
    return agency


def update_settings(
    db: Session,
    agency_id: int,
    project_name: Optional[str] = None,
    timezone_value: Optional[str] = None,
    default_currency: Optional[str] = None,
    contact_phone: Optional[str] = None,
    notify_new_objects: Optional[bool] = None,
) -> Agency:
    """Обновить настройки агентства (название проекта, часовой пояс, валюта, контакт)."""
    agency = _get_agency_or_404(db, agency_id)
    if project_name is not None:
        # Пустая строка очищает название проекта.
        agency.project_name = project_name.strip() or None
    if timezone_value is not None:
        tz = timezone_value.strip()
        if tz:
            agency.timezone = tz
    if default_currency is not None:
        cur = default_currency.strip().upper()
        if cur:
            agency.default_currency = cur
    if contact_phone is not None:
        # Пустая строка очищает контактный номер.
        agency.contact_phone = contact_phone.strip() or None
    if notify_new_objects is not None:
        agency.notify_new_objects = notify_new_objects
    db.commit()
    db.refresh(agency)
    return agency
