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

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.core.defaults import DEFAULT_AGENT_CODE, DEFAULT_AGENT_NAME
from app.db.models.apartment import Apartment
from app.repositories import (
    agency_repo,
    agent_repo,
    apartment_event_repo,
    apartment_repo,
    user_repo,
)
from app.schemas.apartment import ApartmentCreate, ApartmentUpdate
from app.services import photo_service, telegram_service

# Допустимые статусы объекта.
STATUS_ACTIVE = "active"
STATUS_DEPOSIT = "deposit"     # задаток внесён — объект «придержан»
STATUS_SOLD = "sold"
STATUS_ARCHIVED = "archived"
VALID_STATUSES = (STATUS_ACTIVE, STATUS_DEPOSIT, STATUS_SOLD, STATUS_ARCHIVED)
# Статусы, при которых объект считается снятым с продажи (фиксируем дату).
_CLOSED_STATUSES = (STATUS_SOLD, STATUS_ARCHIVED)

# Поля, изменение которых отражаем в журнале (в порядке формы).
_TRACKED_FIELDS = (
    "name", "type", "district", "address", "rooms", "floor", "total_floors",
    "area", "condition", "furniture_appliances", "price", "currency",
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
    Номер берётся из атомарного служебного счётчика агентства.
    """
    counter = agent_repo.get_by_code(db, agency_id, DEFAULT_AGENT_CODE)
    if counter is None:
        counter = agent_repo.create(
            db, agency_id, name=DEFAULT_AGENT_NAME, code=DEFAULT_AGENT_CODE
        )
    number = agent_repo.next_number(db, agency_id, counter.id)
    if number is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не удалось сгенерировать номер объекта.",
        )
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
    display_id = _next_display_id(db, agency_id)

    new_status = payload.status or STATUS_ACTIVE
    apartment = Apartment(
        agency_id=agency_id,
        display_id=display_id,
        status=new_status,
        agent_id=None,
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
        condition=payload.condition,
        furniture_appliances=payload.furniture_appliances,
        price=payload.price,
        currency=payload.currency or "USD",
        description=payload.description,
        comment=payload.comment,
        photo_url=payload.photo_url,
        source_link=payload.source_link,
        archived_at=datetime.now(timezone.utc) if new_status in _CLOSED_STATUSES else None,
    )
    apartment_repo.create(db, apartment)
    apartment_event_repo.add_event(db, agency_id, apartment.id, created_by, "created")
    db.commit()
    db.refresh(apartment)
    _attach_creators(db, [apartment])
    _notify_new_apartment(db, agency_id, apartment, created_by)
    return apartment


def _notify_new_apartment(db: Session, agency_id: int, apartment: Apartment, creator_id) -> None:
    """
    Уведомить руководителей агентства (главного админа и админов) о новом
    объекте. Создателя самого себя не уведомляем. Best-effort: любые ошибки
    глушим, рассылка идёт в фоне и не задерживает ответ.
    """
    try:
        if not telegram_service.is_configured():
            return
        agency = agency_repo.get_by_id(db, agency_id)
        # Уведомления отключены в настройках агентства — ничего не делаем.
        if agency is None or not getattr(agency, "notify_new_objects", False):
            return
        recipients = []
        creator_name = None
        for u in user_repo.get_by_agency(db, agency_id):
            if u.id == creator_id:
                creator_name = _display_name(u)
            if (
                u.role == "agency_admin"
                and u.is_active
                and u.telegram_id
                and u.id != creator_id
            ):
                recipients.append(u.telegram_id)
        if not recipients:
            return
        parts = [f"🏠 Новый объект №{apartment.display_id}"]
        if apartment.name:
            parts.append(apartment.name)
        loc = " · ".join(x for x in [apartment.type, apartment.district] if x)
        if loc:
            parts.append(loc)
        price = _format_price(apartment)
        if price:
            parts.append(f"Цена: {price}")
        if creator_name:
            parts.append(f"Добавил: {creator_name}")
        telegram_service.notify_async(recipients, "\n".join(parts))
    except Exception:  # noqa: BLE001
        pass


def get_apartment(db: Session, agency_id: int, apartment_id: int) -> Apartment:
    apartment = apartment_repo.get_by_id(db, agency_id, apartment_id)
    if apartment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Объект не найден."
        )
    _attach_creators(db, [apartment])
    return apartment


def search_apartments(
    db: Session,
    agency_id: int,
    *,
    status_filter: Optional[str] = STATUS_ACTIVE,
    districts: Optional[Sequence[str]] = None,
    types: Optional[Sequence[str]] = None,
    rooms: Optional[Sequence[int]] = None,
    floor_min: Optional[int] = None,
    floor_max: Optional[int] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    agent_id: Optional[int] = None,
    q: Optional[str] = None,
    rooms_min: Optional[int] = None,
    rooms_max: Optional[int] = None,
    created_by: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[list, int]:
    items, total = apartment_repo.search(
        db,
        agency_id,
        status=status_filter,
        districts=districts,
        types=types,
        rooms=rooms,
        floor_min=floor_min,
        floor_max=floor_max,
        price_min=price_min,
        price_max=price_max,
        agent_id=agent_id,
        q=q,
        rooms_min=rooms_min,
        rooms_max=rooms_max,
        created_by=created_by,
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
    changes.pop("agent_id", None)
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
    """Сменить статус объекта (active / deposit / sold / archived)."""
    if new_status not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Недопустимый статус объекта.",
        )
    apartment = get_apartment(db, agency_id, apartment_id)
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
    apartment = get_apartment(db, agency_id, apartment_id)
    # Сначала удаляем фото (файлы + строки) и журнал — на них ссылается объект.
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
    archived = counts.get(STATUS_ARCHIVED, 0)
    total = active + deposit + sold + archived
    return {
        "active": active,
        "deposit": deposit,
        "sold": sold,
        "archived": archived,
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
    return f"{price_str} {apartment.currency}".strip()


def build_share_card(db: Session, agency_id: int, apartment_id: int) -> dict:
    """
    Подготовить карточку объекта для отправки третьим лицам.

    ВАЖНО: номер собственника (owner_phone) и внутренний комментарий (comment)
    НЕ включаются. Вместо номера собственника подставляется контактный номер
    главного администратора агентства (contact_phone из настроек агентства).
    """
    apartment = get_apartment(db, agency_id, apartment_id)
    contact_phone = _agency_contact_phone(db, agency_id)

    # Собираем текстовое представление карточки (без конфиденциальных полей).
    lines = []
    title = apartment.name or f"Объект №{apartment.display_id}"
    lines.append(f"🏠 {title}")
    lines.append(f"№ {apartment.display_id}")
    lines.append("")

    if apartment.type:
        lines.append(f"Тип: {apartment.type}")
    if apartment.district:
        lines.append(f"Район: {apartment.district}")
    if apartment.address:
        lines.append(f"Адрес: {apartment.address}")
    if apartment.rooms is not None:
        lines.append(f"Комнат: {apartment.rooms}")
    if apartment.floor is not None:
        floor_line = f"Этаж: {apartment.floor}"
        if apartment.total_floors is not None:
            floor_line += f"/{apartment.total_floors}"
        lines.append(floor_line)
    if apartment.area is not None:
        lines.append(f"Площадь: {apartment.area} м²")
    if apartment.condition:
        lines.append(f"Состояние: {apartment.condition}")
    if apartment.furniture_appliances:
        label = FURNITURE_APPLIANCES_LABELS.get(
            apartment.furniture_appliances, apartment.furniture_appliances
        )
        lines.append(f"Мебель/техника: {label}")
    price_str = _format_price(apartment)
    if price_str:
        lines.append(f"Цена: {price_str}")
    if apartment.description:
        lines.append("")
        lines.append(apartment.description)
    if contact_phone:
        lines.append("")
        lines.append(f"☎️ Контакт: {contact_phone}")

    share_text = "\n".join(lines)

    return {
        "display_id": apartment.display_id,
        "status": apartment.status,
        "name": apartment.name,
        "district": apartment.district,
        "address": apartment.address,
        "type": apartment.type,
        "rooms": apartment.rooms,
        "floor": apartment.floor,
        "total_floors": apartment.total_floors,
        "area": float(apartment.area) if apartment.area is not None else None,
        "condition": apartment.condition,
        "furniture_appliances": apartment.furniture_appliances,
        "price": float(apartment.price) if apartment.price is not None else None,
        "currency": apartment.currency,
        "description": apartment.description,
        "photo_url": apartment.photo_url,
        "source_link": apartment.source_link,
        "contact_phone": contact_phone,
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
    archived = counts.get(STATUS_ARCHIVED, 0)
    total = active + deposit + sold + archived

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
        "archived": archived,
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Отправка через бота недоступна: не настроен токен бота.",
        )
    card = build_share_card(db, agency_id, apartment_id)
    caption = card["share_text"]
    blobs = photo_service.read_blobs_for_share(db, agency_id, apartment_id, limit=10)
    if blobs:
        ok = telegram_service.send_media_group(user.telegram_id, blobs, caption)
    else:
        ok = telegram_service.send_message(user.telegram_id, caption)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Не удалось отправить. Откройте чат с ботом, нажмите «Старт» и повторите.",
        )
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Отправка недоступна: не настроен токен бота.",
        )
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
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Не удалось подготовить отправку. Попробуйте ещё раз.",
        )
    return {"prepared_message_id": prepared_id}
