"""
Бизнес-логика управления агентствами (для суперадмина).
Создание агентства сразу назначает ему администратора.
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models.agency import Agency
from app.db.models.user import User
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


def _get_agency_or_404(db: Session, agency_id: int) -> Agency:
    agency = agency_repo.get_by_id(db, agency_id)
    if agency is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Агентство не найдено."
        )
    return agency


def rename_agency(db: Session, agency_id: int, name: Optional[str]) -> Agency:
    """Переименовать агентство (суперадмин)."""
    agency = _get_agency_or_404(db, agency_id)
    if name is not None:
        new_name = name.strip()
        if not new_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Название агентства не может быть пустым.",
            )
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

    existing = user_repo.get_by_telegram_id(db, admin_telegram_id)
    if existing is not None:
        if existing.role == "superadmin":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Нельзя назначить суперадмина администратором агентства.",
            )
        if existing.agency_id not in (None, agency_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Этот пользователь уже состоит в другом агентстве.",
            )
        existing.agency_id = agency_id
        existing.role = "agency_admin"
        existing.is_active = True
        if admin_username:
            existing.username = admin_username
    else:
        user_repo.create(
            db,
            telegram_id=admin_telegram_id,
            role="agency_admin",
            agency_id=agency_id,
            username=admin_username,
        )

    db.commit()
    db.refresh(agency)
    return agency


def update_settings(
    db: Session,
    agency_id: int,
    timezone_value: Optional[str] = None,
    default_currency: Optional[str] = None,
) -> Agency:
    """Обновить настройки агентства (часовой пояс, валюта по умолчанию)."""
    agency = _get_agency_or_404(db, agency_id)
    if timezone_value is not None:
        tz = timezone_value.strip()
        if tz:
            agency.timezone = tz
    if default_currency is not None:
        cur = default_currency.strip().upper()
        if cur:
            agency.default_currency = cur
    db.commit()
    db.refresh(agency)
    return agency
