"""
Бизнес-логика управления агентствами (для суперадмина).
Создание агентства сразу назначает ему администратора.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import status
from sqlalchemy.orm import Session

from app.db.models.agency import Agency
from app.db.models.user import User
from app.core.errors import AppError
from app.core.subscription import agency_is_active
from app.repositories import agency_repo, audit_repo, payment_repo, user_repo
from app.schemas.agency import AgencyCreate
from app.services import photo_service, seeding_service


def _admin_display_name(u: Optional[User]) -> Optional[str]:
    if u is None:
        return None
    if u.full_name:
        return u.full_name
    if u.username:
        return "@" + u.username
    return f"ID {u.telegram_id}"


def _actor_fields(actor: Optional[User]) -> dict:
    """Поля автора действия для журнала аудита (из текущего суперадмина)."""
    if actor is None:
        return {}
    return {
        "actor_user_id": actor.id,
        "actor_telegram_id": actor.telegram_id,
        "actor_name": _admin_display_name(actor),
    }


def attach_admins(db: Session, agencies: List[Agency]) -> None:
    """
    Проставить агентствам инфо об их администраторе (для панели суперадмина):
    admin_telegram_id и admin_name. Берём первого по порядку администратора
    агентства (agency_admin). Эти атрибуты только для вывода, в БД их нет.
    """
    for agency in agencies:
        # Личное агентство: «админ» — сам владелец платформы (отдельной строки
        # участника у него нет, он работает через acting-контекст).
        if agency.owner_telegram_id is not None:
            owner = user_repo.get_by_telegram_id(db, agency.owner_telegram_id)
            agency.admin_telegram_id = agency.owner_telegram_id
            agency.admin_name = _admin_display_name(owner)
            continue
        admin = None
        for member in user_repo.get_by_agency(db, agency.id):
            if member.role == "agency_admin":
                admin = member
                break
        agency.admin_telegram_id = admin.telegram_id if admin else None
        agency.admin_name = _admin_display_name(admin)


def create_agency_with_admin(
    db: Session, payload: AgencyCreate, actor: Optional[User] = None
) -> Agency:
    creator_telegram_id = actor.telegram_id if actor else None

    # 0. Проверяем кандидата в админы ДО создания агентства: нельзя забрать
    # человека из другого агентства (иначе то агентство останется без него /
    # без управления). Эта же проверка есть в set_agency_admin.
    existing = user_repo.get_by_telegram_id(db, payload.admin_telegram_id)
    if existing is not None:
        if existing.role == "superadmin":
            raise AppError(
                "cannot_assign_superadmin_as_admin", status.HTTP_400_BAD_REQUEST
            )
        if existing.agency_id is not None:
            raise AppError(
                "user_already_in_another_agency", status.HTTP_400_BAD_REQUEST
            )

    # 1. Создаём агентство с открытой подпиской.
    agency = agency_repo.create(
        db,
        name=payload.name,
        created_by=creator_telegram_id,
        subscription_days=payload.subscription_days,
    )

    # 1.1. Сразу наполняем агентство значениями по умолчанию (районы, типы).
    seeding_service.seed_agency_defaults(db, agency.id)

    # 2. Назначаем администратора агентства (он же — главный админ, is_owner).
    if existing is not None:
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

    audit_repo.add(
        db,
        action="agency_created",
        agency_id=agency.id,
        target=agency.name,
        note=f"admin telegram_id={payload.admin_telegram_id}, "
             f"подписка на {payload.subscription_days} дн.",
        **_actor_fields(actor),
    )

    db.commit()
    db.refresh(agency)
    return agency


def list_personal_agencies(db: Session, owner_telegram_id: int) -> List[Agency]:
    """Личные агентства владельца платформы (где owner_telegram_id == его id)."""
    return agency_repo.get_by_owner(db, owner_telegram_id)


def create_personal_agency(db: Session, name: str, owner: User) -> Agency:
    """
    Создать ЛИЧНОЕ агентство владельца платформы (суперадмина). В отличие от
    обычного: внешний админ не назначается — владелец сам работает в нём как
    главный админ через acting-контекст; подписка не действует (всегда активно).
    Помечается agencies.owner_telegram_id = telegram_id владельца.
    """
    clean = (name or "").strip()
    if not clean:
        raise AppError("personal_agency_name_required", status.HTTP_400_BAD_REQUEST)

    # Срок подписки тут роли не играет (личное всегда активно), но колонки
    # заполняем валидно через общий конструктор.
    agency = agency_repo.create(
        db, name=clean, created_by=owner.telegram_id, subscription_days=3650
    )
    agency.owner_telegram_id = owner.telegram_id

    # Наполняем значениями по умолчанию (районы, типы), как у обычного агентства.
    seeding_service.seed_agency_defaults(db, agency.id)

    audit_repo.add(
        db,
        action="agency_created",
        agency_id=agency.id,
        target=agency.name,
        note="личное агентство владельца платформы",
        **_actor_fields(owner),
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
    *,
    amount: Optional[float] = None,
    currency: Optional[str] = None,
    method: Optional[str] = None,
    note: Optional[str] = None,
    actor: Optional[User] = None,
) -> Agency:
    """
    Управление подпиской агентства (суперадмин):
      - extend   — продлить на N дней (и активировать);
      - set      — задать дату окончания подписки вручную (и активировать);
      - freeze   — заморозить (доступ сотрудников ограничивается);
      - activate — снова активировать (если срок истёк/не задан — продлеваем
                   от текущего момента на `days` дней, чтобы доступ реально
                   восстановился, а не остался заблокированным).
    Для extend/set фиксируем запись в истории платежей.
    """
    agency = agency_repo.get_by_id(db, agency_id)
    if agency is None:
        raise AppError("agency_not_found", status.HTTP_404_NOT_FOUND)

    now = datetime.now(timezone.utc)
    was_active = agency_is_active(agency)
    record_payment = False
    payment_days: Optional[int] = None

    if action == "extend":
        # Честный учёт выручки: при продлении сумма указывается явно (0 — если
        # бесплатно), валюта обязательна при ненулевой сумме (QW23 / M19).
        if amount is None:
            raise AppError("subscription_amount_required", status.HTTP_400_BAD_REQUEST)
        if amount > 0 and not (currency and currency.strip()):
            raise AppError("subscription_currency_required", status.HTTP_400_BAD_REQUEST)
        add_days = days if (days and days > 0) else 30
        # Продлеваем от текущей даты окончания (если она в будущем) или от сейчас.
        base = agency.subscription_expires_at
        if base is None or base < now:
            base = now
        agency.subscription_expires_at = base + timedelta(days=add_days)
        agency.status = "active"
        agency.activated_at = now if not was_active else agency.activated_at
        record_payment = True
        payment_days = add_days
    elif action == "set":
        if expires_at is None:
            raise AppError(
                "subscription_end_date_required", status.HTTP_400_BAD_REQUEST
            )
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        agency.subscription_expires_at = expires_at
        agency.status = "active"
        agency.activated_at = now if not was_active else agency.activated_at
        # Ручная правка даты — не оплата: платёж фиксируем только при явной
        # сумме, иначе в истории выручки появлялись записи без суммы/валюты.
        if amount is not None:
            if amount > 0 and not (currency and currency.strip()):
                raise AppError(
                    "subscription_currency_required", status.HTTP_400_BAD_REQUEST
                )
            record_payment = True
    elif action == "freeze":
        agency.status = "frozen"
    elif action == "activate":
        # Активация должна РЕАЛЬНО давать доступ: если срок не задан или истёк —
        # продлеваем от текущего момента на `days` дней (по умолчанию 30).
        add_days = days if (days and days > 0) else 30
        if agency.subscription_expires_at is None or agency.subscription_expires_at < now:
            agency.subscription_expires_at = now + timedelta(days=add_days)
            record_payment = True
            payment_days = add_days
        agency.status = "active"
        agency.activated_at = now
    else:
        raise AppError("unknown_action", status.HTTP_400_BAD_REQUEST)

    if record_payment:
        payment_repo.add(
            db,
            agency_id=agency.id,
            action="extend" if action != "set" else "set",
            days=payment_days,
            amount=Decimal(str(amount)) if amount is not None else None,
            currency=(currency.strip().upper() if currency else None),
            method=(method.strip() if method else None),
            note=(note.strip() if note else None),
            expires_at_after=agency.subscription_expires_at,
            created_by_telegram_id=actor.telegram_id if actor else None,
        )

    audit_repo.add(
        db,
        action=f"subscription_{action}",
        agency_id=agency.id,
        target=agency.name,
        note=(f"до {agency.subscription_expires_at:%Y-%m-%d}"
              if agency.subscription_expires_at else None),
        **_actor_fields(actor),
    )

    db.commit()
    db.refresh(agency)
    return agency


def _get_agency_or_404(db: Session, agency_id: int) -> Agency:
    agency = agency_repo.get_by_id(db, agency_id)
    if agency is None:
        raise AppError("agency_not_found", status.HTTP_404_NOT_FOUND)
    return agency


def rename_agency(
    db: Session, agency_id: int, name: Optional[str], actor: Optional[User] = None
) -> Agency:
    """Переименовать агентство (суперадмин)."""
    agency = _get_agency_or_404(db, agency_id)
    if name is not None:
        new_name = name.strip()
        if not new_name:
            raise AppError("agency_name_empty", status.HTTP_400_BAD_REQUEST)
        old = agency.name
        agency.name = new_name
        audit_repo.add(
            db, action="agency_renamed", agency_id=agency.id,
            target=new_name, note=f"было: {old}", **_actor_fields(actor),
        )
    db.commit()
    db.refresh(agency)
    return agency


def delete_agency(db: Session, agency_id: int, actor: Optional[User] = None) -> None:
    """
    Удалить агентство со всеми его данными (объекты, фото, команда, приглашения,
    справочники, история платежей). Необратимо. Только суперадмин.
    """
    agency = _get_agency_or_404(db, agency_id)
    name = agency.name
    # 1. Сначала удаляем фотографии (строки + файлы с диска) — иначе они держат
    # объекты ссылкой и удаление падало бы с ошибкой целостности.
    photo_service.purge_agency(db, agency.id)
    # 2. Затем удаляем само агентство и все его данные.
    agency_repo.delete_with_data(db, agency)
    # 3. Запись в журнал аудита (agency_id уже не существует — пишем в note).
    audit_repo.add(
        db, action="agency_deleted", agency_id=None,
        target=name, note=f"agency_id={agency_id}", **_actor_fields(actor),
    )
    db.commit()


def set_agency_admin(
    db: Session,
    agency_id: int,
    admin_telegram_id: int,
    admin_username: Optional[str],
    actor: Optional[User] = None,
) -> Agency:
    """
    Назначить/сменить администратора агентства (суперадмин).
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

    audit_repo.add(
        db, action="agency_admin_changed", agency_id=agency.id,
        target=f"telegram_id={admin_telegram_id}", **_actor_fields(actor),
    )

    db.commit()
    db.refresh(agency)
    return agency


def list_payments(db: Session, agency_id: int) -> list:
    """История платежей/продлений подписки агентства (для суперадмина)."""
    _get_agency_or_404(db, agency_id)
    return payment_repo.list_for_agency(db, agency_id)


def payments_summary(db: Session) -> dict:
    """
    Свод по платежам для владельца платформы: итоги по валютам за всё время и
    за текущий месяц, плюс общее число записей. Суммы группируются по валюте,
    так как складывать разные валюты в одно число нельзя.
    """
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def _fmt(rows):
        return [
            {
                "currency": cur or "—",
                "amount": float(total) if total is not None else 0.0,
                "count": cnt,
            }
            for cur, total, cnt in rows
        ]

    return {
        "all_time": _fmt(payment_repo.totals_by_currency(db)),
        "this_month": _fmt(payment_repo.totals_by_currency(db, since=month_start)),
        "total_records": payment_repo.count_all(db),
    }


def list_audit(db: Session, agency_id: int) -> list:
    """Журнал действий по агентству (для суперадмина)."""
    _get_agency_or_404(db, agency_id)
    return audit_repo.list_for_agency(db, agency_id)


def update_settings(
    db: Session,
    agency_id: int,
    project_name: Optional[str] = None,
    timezone_value: Optional[str] = None,
    default_currency: Optional[str] = None,
    contact_phone: Optional[str] = None,
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
    db.commit()
    db.refresh(agency)
    return agency
