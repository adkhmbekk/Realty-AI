"""
Бизнес-логика объектов недвижимости (ядро ценности продукта).

Здесь живут правила домена:
  - генерация человекочитаемого ID (display_id) из счётчика агентства;
  - создание/редактирование объекта (редактирование — только по белому списку);
  - перевод в архив / восстановление / пометка «продан»;
  - поиск с фильтрами;
  - журнал действий (кто создал/изменил/сменил статус);
  - формирование карточки для «поделиться» (без номера собственника и
    комментария, с подстановкой контактного номера главного админа агентства).

Изоляция по агентству обеспечивается тем, что все вызовы репозитория получают
agency_id текущего пользователя (а сам agency_id берётся из сессии, не с фронта).
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, Sequence, Tuple

import secrets

from fastapi import status
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import AppError
from app.db.models.apartment import Apartment
from app.repositories import (
    agency_repo,
    apartment_event_repo,
    apartment_repo,
    user_repo,
)
from app.schemas.apartment import ApartmentCreate, ApartmentUpdate
from app.services import photo_service, telegram_service

# Допустимые статусы объекта.
STATUS_ACTIVE = "active"
STATUS_DEPOSIT = "deposit"     # задаток/бронь — объект «придержан»
STATUS_SOLD = "sold"
STATUS_RENTED = "rented"       # сдан в аренду (терминальный статус аренды)
VALID_STATUSES = (STATUS_ACTIVE, STATUS_DEPOSIT, STATUS_SOLD, STATUS_RENTED)
# Статусы, при которых объект считается снятым (фиксируем дату): продан или сдан.
# Для аренды это не навсегда — статус можно вернуть в active, дата сбросится.
_CLOSED_STATUSES = (STATUS_SOLD, STATUS_RENTED)


def _status_allowed_for_deal(deal_type: Optional[str], status_value: str) -> bool:
    """Совместимость статуса и типа сделки: 'sold' — только у продажи, 'rented' —
    только у аренды (active/deposit допустимы для обоих). Чтобы нельзя было,
    например, пометить продажу «сдан» или аренду «продан»."""
    dt = deal_type or "sale"
    if status_value == STATUS_SOLD:
        return dt == "sale"
    if status_value == STATUS_RENTED:
        return dt == "rent"
    return True

# Типы «Земля» и «Участок» (исторический список).
LAND_TYPES = ("Земля", "Участок")
# Типы с земельным участком (дом тоже): «Этаж» не показываем; «Этажность» и
# «Соток» — показываем. Зеркало фронта (hasLandArea).
LAND_AREA_TYPES = ("Дом", "Земля", "Участок")

# Поля, изменение которых отражаем в журнале (в порядке формы).
_TRACKED_FIELDS = (
    "deal_type", "rent_period",
    "name", "type", "district", "address", "rooms", "floor", "total_floors",
    "area", "land_area", "condition", "furniture_appliances", "price", "currency",
    "owner_phone", "description", "comment", "photo_url", "source_link",
)

# Человекочитаемые подписи для поля «мебель и техника».
FURNITURE_APPLIANCES_LABELS = {
    "furniture_and_appliances": "Мебель и техника",
    "furniture_only": "Только мебель",
    "appliances_only": "Только техника",
    "none": "Без мебели и техники",
}


def _next_display_id(db: Session, agency_id: int) -> str:
    """
    Сгенерировать сквозной номер объекта агентства, например «0001».
    Номер берётся из атомарного счётчика агентства (agencies.last_display_number).
    """
    number = agency_repo.next_display_number(db, agency_id)
    if number is None:
        raise AppError("display_id_generation_failed", status.HTTP_400_BAD_REQUEST)
    return f"{number:04d}"


def _display_name(u) -> Optional[str]:
    """Человекочитаемое имя сотрудника."""
    if u is None:
        return None
    if u.full_name:
        return u.full_name
    if u.username:
        return "@" + u.username
    return f"ID {u.telegram_id}"


def _attach_creators(db: Session, apartments) -> None:
    """Проставить объектам имя создателя (created_by_name) для отображения."""
    ids = {a.created_by for a in apartments if a.created_by is not None}
    names = {}
    if ids:
        for u in user_repo.get_by_ids(db, ids):
            names[u.id] = _display_name(u)
    for a in apartments:
        a.created_by_name = names.get(a.created_by)


def _values_differ(old, new) -> bool:
    """Сравнение значений с учётом Decimal/float и None (для журнала изменений)."""
    if old is None and new is None:
        return False
    if old is None or new is None:
        return True
    if isinstance(old, Decimal) or isinstance(new, Decimal):
        try:
            return Decimal(str(old)) != Decimal(str(new))
        except Exception:  # noqa: BLE001
            return str(old) != str(new)
    return str(old) != str(new)


def create_apartment(
    db: Session, agency_id: int, created_by: Optional[int], payload: ApartmentCreate
) -> Apartment:
    # Запрет на полностью пустой объект: должно быть заполнено хотя бы одно
    # значимое поле (иначе база засоряется «пустышками» без какой-либо пользы).
    meaningful = (
        payload.name, payload.district, payload.address, payload.type,
        payload.rooms, payload.floor, payload.total_floors, payload.area,
        payload.land_area, payload.price, payload.owner_phone, payload.condition,
        payload.description, payload.photo_url, payload.source_link,
    )
    if not any(v not in (None, "") for v in meaningful):
        raise AppError("empty_apartment", status.HTTP_400_BAD_REQUEST)

    display_id = _next_display_id(db, agency_id)

    new_status = payload.status or STATUS_ACTIVE
    # Тип сделки: по умолчанию продажа. У продажи срока аренды быть не может.
    deal_type = payload.deal_type or "sale"
    rent_period = payload.rent_period if deal_type == "rent" else None
    # Статус должен соответствовать типу сделки (нельзя создать «продан» в аренде).
    if not _status_allowed_for_deal(deal_type, new_status):
        raise AppError("invalid_apartment_status", status.HTTP_400_BAD_REQUEST)
    apartment = Apartment(
        agency_id=agency_id,
        display_id=display_id,
        status=new_status,
        deal_type=deal_type,
        rent_period=rent_period,
        created_by=created_by,
        name=payload.name,
        owner_phone=payload.owner_phone,
        district=payload.district,
        address=payload.address,
        type=payload.type,
        rooms=payload.rooms,
        floor=payload.floor,
        total_floors=payload.total_floors,
        area=payload.area,
        land_area=payload.land_area,
        condition=payload.condition,
        furniture_appliances=payload.furniture_appliances,
        price=payload.price,
        currency=payload.currency or "USD",
        description=payload.description,
        comment=payload.comment,
        photo_url=payload.photo_url,
        source_link=payload.source_link,
        source=payload.source,
        archived_at=datetime.now(timezone.utc) if new_status in _CLOSED_STATUSES else None,
    )
    apartment_repo.create(db, apartment)
    apartment_event_repo.add_event(db, agency_id, apartment.id, created_by, "created")
    db.commit()
    db.refresh(apartment)
    _attach_creators(db, [apartment])
    return apartment


def get_apartment(db: Session, agency_id: int, apartment_id: int) -> Apartment:
    apartment = apartment_repo.get_by_id(db, agency_id, apartment_id)
    if apartment is None:
        raise AppError("apartment_not_found", status.HTTP_404_NOT_FOUND)
    _attach_creators(db, [apartment])
    return apartment


def search_apartments(
    db: Session,
    agency_id: int,
    *,
    status_filter: Optional[str] = STATUS_ACTIVE,
    districts: Optional[Sequence[str]] = None,
    types: Optional[Sequence[str]] = None,
    deal_type: Optional[str] = None,
    rooms: Optional[Sequence[int]] = None,
    floor_min: Optional[int] = None,
    floor_max: Optional[int] = None,
    land_area_min: Optional[float] = None,
    land_area_max: Optional[float] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    currency: Optional[str] = None,
    q: Optional[str] = None,
    rooms_min: Optional[int] = None,
    rooms_max: Optional[int] = None,
    created_by: Optional[int] = None,
    archived: bool = False,
    created_from=None,
    created_to=None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[list, int]:
    items, total = apartment_repo.search(
        db,
        agency_id,
        status=status_filter,
        districts=districts,
        types=types,
        deal_type=deal_type,
        rooms=rooms,
        floor_min=floor_min,
        floor_max=floor_max,
        land_area_min=land_area_min,
        land_area_max=land_area_max,
        price_min=price_min,
        price_max=price_max,
        currency=currency,
        q=q,
        rooms_min=rooms_min,
        rooms_max=rooms_max,
        created_by=created_by,
        archived=archived,
        created_from=created_from,
        created_to=created_to,
        limit=limit,
        offset=offset,
    )
    _attach_creators(db, items)
    return items, total


def update_apartment(
    db: Session,
    agency_id: int,
    apartment_id: int,
    payload: ApartmentUpdate,
    actor_id: Optional[int] = None,
) -> Apartment:
    apartment = get_apartment(db, agency_id, apartment_id)

    # exclude_unset=True → меняем только присланные поля (белый список схемы).
    changes = payload.model_dump(exclude_unset=True)
    if "currency" in changes and not changes["currency"]:
        changes.pop("currency")

    # Применяем только реально изменившиеся поля и копим их для журнала.
    changed = []
    for field, value in changes.items():
        if _values_differ(getattr(apartment, field, None), value):
            setattr(apartment, field, value)
            if field in _TRACKED_FIELDS:
                changed.append(field)

    if changed:
        apartment_event_repo.add_event(
            db, agency_id, apartment.id, actor_id, "updated", ",".join(changed)
        )

    db.commit()
    db.refresh(apartment)
    _attach_creators(db, [apartment])
    return apartment


def set_status(
    db: Session,
    agency_id: int,
    apartment_id: int,
    new_status: str,
    actor_id: Optional[int] = None,
) -> Apartment:
    """Сменить статус объекта (active / deposit / sold)."""
    if new_status not in VALID_STATUSES:
        raise AppError("invalid_apartment_status", status.HTTP_400_BAD_REQUEST)
    apartment = get_apartment(db, agency_id, apartment_id)
    # Статус должен соответствовать типу сделки (продажа↔sold, аренда↔rented).
    if not _status_allowed_for_deal(apartment.deal_type, new_status):
        raise AppError("invalid_apartment_status", status.HTTP_400_BAD_REQUEST)
    if apartment.status != new_status:
        apartment.status = new_status
        # Фиксируем дату снятия с продажи для архива/продажи; иначе сбрасываем.
        apartment.archived_at = (
            datetime.now(timezone.utc) if new_status in _CLOSED_STATUSES else None
        )
        apartment_event_repo.add_event(
            db, agency_id, apartment.id, actor_id, "status", new_status
        )
    db.commit()
    db.refresh(apartment)
    _attach_creators(db, [apartment])
    return apartment


def delete_apartment(db: Session, agency_id: int, apartment_id: int) -> None:
    """«Удалить» = переместить в архив (мягкое удаление). Только владелец агентства."""
    apartment = get_apartment(db, agency_id, apartment_id)
    if apartment.deleted_at is None:
        apartment.deleted_at = datetime.now(timezone.utc)
        db.commit()


def restore_apartment(db: Session, agency_id: int, apartment_id: int) -> None:
    """Вернуть объект из архива обратно в базу. Только владелец агентства."""
    apartment = get_apartment(db, agency_id, apartment_id)
    if apartment.deleted_at is not None:
        apartment.deleted_at = None
        db.commit()


def list_archived_apartments(db: Session, agency_id: int, *, limit: int = 50, offset: int = 0,
                             created_from=None, created_to=None):
    """Список объектов в архиве агентства (видят все сотрудники)."""
    return apartment_repo.list_archived(
        db, agency_id, limit=limit, offset=offset,
        created_from=created_from, created_to=created_to,
    )


def purge_apartment(db: Session, agency_id: int, apartment_id: int) -> None:
    """Удалить объект НАВСЕГДА (фото, журнал, строку). Необратимо. Только владелец."""
    apartment = get_apartment(db, agency_id, apartment_id)
    photo_service.purge_apartment(db, agency_id, apartment.id)
    apartment_event_repo.delete_for_apartment(db, apartment.id)
    db.delete(apartment)
    db.commit()


def get_stats(db: Session, agency_id: int) -> dict:
    """Мини-статистика по объектам агентства: счётчики по статусам."""
    counts = apartment_repo.count_by_status(db, agency_id)
    active = counts.get(STATUS_ACTIVE, 0)
    deposit = counts.get(STATUS_DEPOSIT, 0)
    sold = counts.get(STATUS_SOLD, 0)
    rented = counts.get(STATUS_RENTED, 0)
    total = active + deposit + sold + rented
    return {
        "active": active,
        "deposit": deposit,
        "sold": sold,
        "rented": rented,
        "total": total,
    }


def _agency_contact_phone(db: Session, agency_id: int) -> Optional[str]:
    """
    Контактный телефон для отправки клиентам.

    Приоритет: телефон, указанный в настройках агентства (contact_phone).
    Если не задан — None (тогда в карточке контакт не выводится).
    """
    agency = agency_repo.get_by_id(db, agency_id)
    if agency is not None and getattr(agency, "contact_phone", None):
        return agency.contact_phone
    return None


def _agency_contact_username(db: Session, agency_id: int) -> Optional[str]:
    """
    Telegram-логин владельца агентства (@username) для связи клиентов.

    Берётся у главного администратора (владельца). Если у него не задан
    username в Telegram — возвращаем None (тогда в карточке покажем только телефон).
    """
    owner = user_repo.get_owner(db, agency_id)
    if owner is not None and getattr(owner, "username", None):
        return "@" + owner.username
    return None


# Суффикс цены для аренды (карточка «Поделиться»): «/мес» или «/сутки».
_RENT_SUFFIX = {"month": "/мес", "day": "/сутки"}


def _format_price(apartment: Apartment) -> Optional[str]:
    if apartment.price is None:
        return None
    # Цена без лишних нулей: 50000.00 → 50000.
    price = apartment.price
    try:
        price_int = int(price)
        price_str = f"{price_int:,}".replace(",", " ") if price == price_int else f"{price}"
    except Exception:  # noqa: BLE001
        price_str = str(price)
    out = f"{price_str} {apartment.currency}".strip()
    # Для аренды добавляем период (за месяц/сутки), чтобы клиент не путал со сделкой.
    if getattr(apartment, "deal_type", "sale") == "rent":
        out += _RENT_SUFFIX.get(apartment.rent_period or "month", "/мес")
    return out


def build_share_card(db: Session, agency_id: int, apartment_id: int) -> dict:
    """
    Подготовить карточку объекта для отправки третьим лицам.

    ВАЖНО: номер собственника (owner_phone) и внутренний комментарий (comment)
    НЕ включаются. Вместо номера собственника подставляется контактный номер
    главного администратора агентства (contact_phone из настроек агентства).
    """
    apartment = get_apartment(db, agency_id, apartment_id)
    contact_phone = _agency_contact_phone(db, agency_id)
    contact_username = _agency_contact_username(db, agency_id)

    # Собираем текстовое представление карточки (без конфиденциальных полей).
    # Порядок: [наименование, если задано вручную] → описание → остальные данные.
    # У каждой строки — подходящий эмодзи в начале.
    lines = []
    if apartment.name:
        lines.append(f"🏠 {apartment.name}")
    lines.append(f"№ {apartment.display_id}")
    # Для аренды явно помечаем тип сделки и период (продажа — по умолчанию).
    if getattr(apartment, "deal_type", "sale") == "rent":
        period = "за сутки" if apartment.rent_period == "day" else "за месяц"
        lines.append(f"🤝 Аренда ({period})")

    # Описание — сразу после наименования (или первым, если наименования нет).
    if apartment.description:
        lines.append("")
        lines.append(f"📝 {apartment.description}")

    # Остальные данные по порядку.
    details = []
    if apartment.type:
        details.append(f"🏗 Тип: {apartment.type}")
    if apartment.district:
        details.append(f"📍 Район: {apartment.district}")
    if apartment.address:
        details.append(f"🗺 Адрес: {apartment.address}")
    if apartment.rooms is not None:
        details.append(f"🚪 Комнат: {apartment.rooms}")
    # Дом/участок/земля: «Соток» вместо «Этажа»; «Этажность» — для всех типов.
    if apartment.type in LAND_AREA_TYPES:
        if apartment.land_area is not None:
            details.append(f"🌳 Соток: {apartment.land_area}")
    else:
        if apartment.floor is not None:
            details.append(f"🏢 Этаж: {apartment.floor}")
    if apartment.total_floors is not None:
        details.append(f"🏢 Этажность: {apartment.total_floors}")
    if apartment.area is not None:
        details.append(f"📐 Площадь: {apartment.area} м²")
    if apartment.condition:
        details.append(f"🔧 Состояние: {apartment.condition}")
    if apartment.furniture_appliances:
        label = FURNITURE_APPLIANCES_LABELS.get(
            apartment.furniture_appliances, apartment.furniture_appliances
        )
        details.append(f"🛋 Мебель/техника: {label}")
    price_str = _format_price(apartment)
    if price_str:
        details.append(f"💵 Цена: {price_str}")
    if details:
        lines.append("")
        lines.extend(details)

    if contact_phone:
        lines.append("")
        lines.append(f"☎️ Контакт: {contact_phone}")
    if contact_username:
        # @username владельца агентства — кликабельный логин в Telegram.
        if not contact_phone:
            lines.append("")
        lines.append(f"✈️ Telegram: {contact_username}")

    share_text = "\n".join(lines)

    return {
        "display_id": apartment.display_id,
        "status": apartment.status,
        "deal_type": apartment.deal_type,
        "rent_period": apartment.rent_period,
        "name": apartment.name,
        "district": apartment.district,
        "address": apartment.address,
        "type": apartment.type,
        "rooms": apartment.rooms,
        "floor": apartment.floor,
        "total_floors": apartment.total_floors,
        "area": float(apartment.area) if apartment.area is not None else None,
        "land_area": float(apartment.land_area) if apartment.land_area is not None else None,
        "condition": apartment.condition,
        "furniture_appliances": apartment.furniture_appliances,
        "price": float(apartment.price) if apartment.price is not None else None,
        "currency": apartment.currency,
        "description": apartment.description,
        "photo_url": apartment.photo_url,
        "source_link": apartment.source_link,
        "contact_phone": contact_phone,
        "contact_username": contact_username,
        "share_text": share_text,
    }


def list_events(db: Session, agency_id: int, apartment_id: int) -> list:
    """История действий по объекту (с именами сотрудников)."""
    # Проверяем принадлежность объекта агентству (иначе 404).
    get_apartment(db, agency_id, apartment_id)
    events = apartment_event_repo.list_for_apartment(db, agency_id, apartment_id)
    ids = {e.user_id for e in events if e.user_id is not None}
    names = {}
    if ids:
        for u in user_repo.get_by_ids(db, ids):
            names[u.id] = _display_name(u)
    return [
        {
            "action": e.action,
            "note": e.note,
            "user_name": names.get(e.user_id),
            "created_at": e.created_at,
        }
        for e in events
    ]



def get_analytics(db: Session, agency_id: int) -> dict:
    """
    Аналитика для руководителя агентства: счётчики по статусам, добавлено и
    продано за текущий месяц, активность по сотрудникам (всего/продано).
    """
    counts = apartment_repo.count_by_status(db, agency_id)
    active = counts.get(STATUS_ACTIVE, 0)
    deposit = counts.get(STATUS_DEPOSIT, 0)
    sold = counts.get(STATUS_SOLD, 0)
    rented = counts.get(STATUS_RENTED, 0)
    total = active + deposit + sold + rented

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    added_this_month = apartment_repo.count_created_since(db, agency_id, month_start)
    sold_this_month = apartment_repo.count_sold_since(db, agency_id, month_start)

    creator_rows = apartment_repo.stats_by_creator(db, agency_id)
    ids = {cid for cid, _, _ in creator_rows if cid is not None}
    names = {}
    if ids:
        for u in user_repo.get_by_ids(db, ids):
            names[u.id] = _display_name(u)
    agents = [
        {
            "user_id": cid,
            "name": names.get(cid) if cid is not None else None,
            "total": tot,
            "sold": sold_c,
        }
        for cid, tot, sold_c in creator_rows
    ]
    agents.sort(key=lambda a: a["total"], reverse=True)

    return {
        "active": active,
        "deposit": deposit,
        "sold": sold,
        "total": total,
        "added_this_month": added_this_month,
        "sold_this_month": sold_this_month,
        "agents": agents,
    }


def find_similar(
    db: Session,
    agency_id: int,
    *,
    district: Optional[str] = None,
    rooms: Optional[int] = None,
    type_: Optional[str] = None,
    price: Optional[float] = None,
    address: Optional[str] = None,
    exclude_id: Optional[int] = None,
) -> list:
    """Найти возможные дубли объекта (для предупреждения при добавлении)."""
    items = apartment_repo.find_similar(
        db,
        agency_id,
        district=district,
        rooms=rooms,
        type_=type_,
        price=price,
        address=address,
        exclude_id=exclude_id,
        limit=5,
    )
    _attach_creators(db, items)
    return items


def send_share(db: Session, agency_id: int, apartment_id: int, user) -> dict:
    """
    Отправить объект сотруднику в его личный чат с ботом: альбом фотографий с
    подписью (карточка без конфиденциальных полей). Сотрудник затем пересылает
    сообщение клиенту. Если фото нет — отправляем только текст.
    """
    if not telegram_service.is_configured():
        raise AppError("share_via_bot_not_configured", status.HTTP_400_BAD_REQUEST)
    card = build_share_card(db, agency_id, apartment_id)
    caption = card["share_text"]
    blobs = photo_service.read_blobs_for_share(db, agency_id, apartment_id, limit=10)
    if blobs:
        ok = telegram_service.send_media_group(user.telegram_id, blobs, caption)
    else:
        ok = telegram_service.send_message(user.telegram_id, caption)
    if not ok:
        raise AppError("share_send_failed", status.HTTP_502_BAD_GATEWAY)
    return {"ok": True, "photos": len(blobs)}



# Доступные периоды для графиков: (гранулярность, сколько корзин).
_PERIODS = {
    "week": ("day", 7),
    "month": ("day", 30),
    "halfyear": ("month", 6),
    "year": ("month", 12),
}


def _bucket_starts(granularity: str, count: int):
    """Список начал корзин (дат) от старой к новой, включая текущую."""
    today = datetime.now(timezone.utc).date()
    starts = []
    if granularity == "day":
        for i in range(count - 1, -1, -1):
            starts.append(today - timedelta(days=i))
    elif granularity == "week":
        # Начало недели — понедельник (как у Postgres date_trunc('week', ...)).
        monday = today - timedelta(days=today.weekday())
        for i in range(count - 1, -1, -1):
            starts.append(monday - timedelta(weeks=i))
    else:  # month
        y, m = today.year, today.month
        for i in range(count - 1, -1, -1):
            mm = m - i
            yy = y
            while mm <= 0:
                mm += 12
                yy -= 1
            starts.append(datetime(yy, mm, 1, tzinfo=timezone.utc).date())
    return starts


_MONTHS_RU = ["", "янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]


def _bucket_label(granularity: str, d) -> str:
    # День — "ДД.ММ"; месяц — только название месяца (без года, чтобы число года
    # не путалось с числом месяца, например «26» воспринимали как дату).
    if granularity in ("day", "week"):
        return f"{d.day:02d}.{d.month:02d}"
    return _MONTHS_RU[d.month]


def get_timeseries(db: Session, agency_id: int, period: str) -> dict:
    """Данные для графика «добавлено/продано» по периодам."""
    granularity, count = _PERIODS.get(period, _PERIODS["month"])
    starts = _bucket_starts(granularity, count)
    since = datetime(
        starts[0].year, starts[0].month, starts[0].day, tzinfo=timezone.utc
    )
    created_map, sold_map = apartment_repo.timeseries_counts(db, agency_id, since, granularity)
    buckets = [
        {
            "label": _bucket_label(granularity, d),
            "added": created_map.get(d, 0),
            "sold": sold_map.get(d, 0),
        }
        for d in starts
    ]
    return {"period": period, "buckets": buckets}


def get_agent_activity(db: Session, agency_id: int, user_id: int) -> list:
    """Последние действия сотрудника (для разбора активности)."""
    rows = apartment_event_repo.list_for_agency_user(db, agency_id, user_id, limit=30)
    return [
        {
            "display_id": display_id,
            "action": event.action,
            "note": event.note,
            "created_at": event.created_at,
        }
        for event, display_id in rows
    ]


def prepare_share(db: Session, agency_id: int, apartment_id: int, user) -> dict:
    """
    Подготовить сообщение для отправки НАПРЯМУЮ в выбранный пользователем чат
    (Telegram.WebApp.shareMessage). Возвращает prepared_message_id.

    Из-за ограничений Telegram прямое сообщение содержит одну (обложечную)
    фотографию и полную текстовую карточку в подписи. Если фото нет — уходит
    только текст.
    """
    if not telegram_service.is_configured():
        raise AppError("share_not_configured", status.HTTP_400_BAD_REQUEST)
    card = build_share_card(db, agency_id, apartment_id)
    caption = card["share_text"]
    cover = card.get("photo_url")
    result_id = secrets.token_hex(8)

    if cover:
        photo_url = settings.public_base_url.rstrip("/") + cover
        result = {
            "type": "photo",
            "id": result_id,
            "photo_url": photo_url,
            "thumbnail_url": photo_url,
            "caption": caption[:1024],
        }
    else:
        title = card.get("name") or f"Объект №{card.get('display_id')}"
        result = {
            "type": "article",
            "id": result_id,
            "title": title,
            "description": caption[:120],
            "input_message_content": {"message_text": caption[:4096]},
        }

    prepared_id = telegram_service.save_prepared_inline_message(user.telegram_id, result)
    if not prepared_id:
        raise AppError("share_prepare_failed", status.HTTP_502_BAD_GATEWAY)
    return {"prepared_message_id": prepared_id}
