"""
Бизнес-логика клиентской базы: клиенты, заявки («что ищет») и авто-подбор.

Подбор сделан на ТОМ ЖЕ поиске, что и обычный поиск объектов (заявка = сохранённый
поиск). Два момента срабатывания:
  • при создании/правке заявки — синхронно прогоняем по существующей базе
    (apartment_repo.search) и показываем «что уже есть»;
  • при появлении новых объектов — фоновый планировщик (run_matching_tick)
    сверяет недавние объекты с активными заявками (предикат apartment_matches_request,
    зеркало условий поиска) и создаёт совпадения.
Совпадения дедуплицируются уникальной парой (request_id, apartment_id).

Доступ: клиенты ЛИЧНЫЕ у агента (видит только свои), администратор видит всех и
может переназначить владельца. Телефон клиента — конфиденциален.
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from fastapi import status

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models.apartment import Apartment
from app.db.models.client import Client
from app.db.models.client_request import ClientRequest
from app.db.models.request_match import RequestMatch
from app.repositories import apartment_repo, client_repo, user_repo
from app.schemas.apartment import ApartmentOut
from app.schemas.client import (
    ClientCreate,
    ClientOut,
    ClientUpdate,
    MatchOut,
    RequestCriteria,
    RequestOut,
    RequestUpdate,
)
from app.services import apartment_service

# Сколько минут «назад» смотрит фоновый подбор (с запасом перекрывает тик).
_MATCH_LOOKBACK_MINUTES = 30


# ── Права/видимость ──────────────────────────────────────────────────
def _can_see_all(user) -> bool:
    """Администратор (в т.ч. acting-владелец) видит всех клиентов агентства."""
    return getattr(user, "role", None) == "agency_admin"


def _owner_filter(user) -> Optional[int]:
    """Агент видит только своих клиентов → фильтр по created_by; админ — None."""
    return None if _can_see_all(user) else user.id


# ── Критерии заявки ──────────────────────────────────────────────────
_CRITERIA_FIELDS = (
    "types", "districts", "rooms_min", "rooms_max", "floor_min", "floor_max",
    "land_area_min", "land_area_max", "price_min", "price_max",
)


def _is_empty_criteria(c) -> bool:
    """Заявка без единого значимого критерия (валюта/заметка не в счёт) — пустая."""
    for f in _CRITERIA_FIELDS:
        v = getattr(c, f, None)
        if v not in (None, [], ""):
            return False
    return True


def apartment_matches_request(apt: Apartment, req: ClientRequest) -> bool:
    """
    Подходит ли объект под заявку. Зеркало условий apartment_repo._build_conditions:
    указанные критерии должны выполняться; цена сравнивается только в той же валюте.
    """
    if req.types and apt.type not in req.types:
        return False
    if req.districts and apt.district not in req.districts:
        return False
    if req.rooms_min is not None and (apt.rooms is None or apt.rooms < req.rooms_min):
        return False
    if req.rooms_max is not None and (apt.rooms is None or apt.rooms > req.rooms_max):
        return False
    if req.floor_min is not None and (apt.floor is None or apt.floor < req.floor_min):
        return False
    if req.floor_max is not None and (apt.floor is None or apt.floor > req.floor_max):
        return False
    if req.land_area_min is not None and (apt.land_area is None or apt.land_area < req.land_area_min):
        return False
    if req.land_area_max is not None and (apt.land_area is None or apt.land_area > req.land_area_max):
        return False
    # Валюта: фильтр цены имеет смысл только в одной валюте (как в поиске).
    if req.currency and apt.currency != req.currency:
        return False
    if req.price_min is not None and (apt.price is None or apt.price < req.price_min):
        return False
    if req.price_max is not None and (apt.price is None or apt.price > req.price_max):
        return False
    return True


def _request_to_search_params(req: ClientRequest) -> dict:
    return dict(
        status="active",
        types=req.types or None,
        districts=req.districts or None,
        rooms_min=req.rooms_min,
        rooms_max=req.rooms_max,
        floor_min=req.floor_min,
        floor_max=req.floor_max,
        land_area_min=req.land_area_min,
        land_area_max=req.land_area_max,
        price_min=req.price_min,
        price_max=req.price_max,
        currency=req.currency,
    )


def _new_request(agency_id: int, client_id: int, created_by: Optional[int], c: RequestCriteria) -> ClientRequest:
    return ClientRequest(
        agency_id=agency_id,
        client_id=client_id,
        created_by=created_by,
        types=c.types or None,
        districts=c.districts or None,
        rooms_min=c.rooms_min,
        rooms_max=c.rooms_max,
        floor_min=c.floor_min,
        floor_max=c.floor_max,
        land_area_min=c.land_area_min,
        land_area_max=c.land_area_max,
        price_min=c.price_min,
        price_max=c.price_max,
        currency=c.currency,
        note=(c.note or None),
        status="active",
    )


# ── Подбор ───────────────────────────────────────────────────────────
def scan_request_against_base(db: Session, agency_id: int, req: ClientRequest) -> int:
    """Прогнать заявку по существующим активным объектам, создать новые совпадения."""
    if _is_empty_criteria(req):
        return 0
    items, _total = apartment_repo.search(
        db, agency_id, **_request_to_search_params(req), limit=500, offset=0
    )
    existing = client_repo.existing_apartment_ids_for_request(db, req.id)
    found = 0
    for apt in items:
        if apt.id in existing:
            continue
        if client_repo.add_match(db, agency_id, req.id, apt.id):
            found += 1
    db.commit()
    return found


def run_matching_tick(db: Session, lookback_minutes: int = _MATCH_LOOKBACK_MINUTES) -> int:
    """
    Фоновый тик подбора: сверить недавно добавленные активные объекты со ВСЕМИ
    активными заявками и создать совпадения. Дедуп — по уникальной паре.
    """
    since = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)
    apts = client_repo.recent_active_apartments(db, since)
    if not apts:
        return 0
    agency_ids = {a.agency_id for a in apts}
    reqs = client_repo.active_requests_for_agencies(db, agency_ids)
    if not reqs:
        return 0
    apts_by_agency: dict = {}
    for a in apts:
        apts_by_agency.setdefault(a.agency_id, []).append(a)

    created = 0
    for req in reqs:
        if _is_empty_criteria(req):
            continue
        candidates = apts_by_agency.get(req.agency_id, [])
        if not candidates:
            continue
        existing = client_repo.existing_apartment_ids_for_request(db, req.id)
        for apt in candidates:
            if apt.id in existing:
                continue
            if apartment_matches_request(apt, req):
                if client_repo.add_match(db, req.agency_id, req.id, apt.id):
                    created += 1
                    existing.add(apt.id)
    db.commit()
    return created


# ── Сериализация ─────────────────────────────────────────────────────
def _client_full_name(c: Client) -> str:
    return (f"{c.name} {c.last_name}".strip()) if c.last_name else c.name


def _num(v) -> str:
    try:
        f = float(v)
        return str(int(f)) if f == int(f) else str(f)
    except Exception:  # noqa: BLE001
        return str(v)


def _range_label(lo, hi) -> Optional[str]:
    if lo is not None and hi is not None:
        return _num(lo) if _num(lo) == _num(hi) else f"{_num(lo)}–{_num(hi)}"
    if lo is not None:
        return f"≥{_num(lo)}"
    if hi is not None:
        return f"≤{_num(hi)}"
    return None


def _request_label(req: ClientRequest) -> str:
    parts: List[str] = []
    if req.types:
        parts.append("/".join(req.types))
    if req.districts:
        parts.append(", ".join(req.districts))
    rooms = _range_label(req.rooms_min, req.rooms_max)
    if rooms:
        parts.append(rooms)
    price = _range_label(req.price_min, req.price_max)
    if price:
        parts.append(price + (f" {req.currency}" if req.currency else ""))
    return " · ".join(parts) if parts else "—"


def _request_to_out(req: ClientRequest, counts: Optional[Tuple[int, int]] = None) -> RequestOut:
    total, new = counts if counts else (0, 0)
    return RequestOut(
        id=req.id,
        client_id=req.client_id,
        types=req.types,
        districts=req.districts,
        rooms_min=req.rooms_min,
        rooms_max=req.rooms_max,
        floor_min=req.floor_min,
        floor_max=req.floor_max,
        land_area_min=req.land_area_min,
        land_area_max=req.land_area_max,
        price_min=req.price_min,
        price_max=req.price_max,
        currency=req.currency,
        note=req.note,
        status=req.status,
        created_at=req.created_at,
        match_count=total,
        new_match_count=new,
    )


def _client_to_out(c: Client, created_by_name=None, *, requests=None, active_requests=0, new_match_count=0) -> ClientOut:
    return ClientOut(
        id=c.id,
        name=c.name,
        last_name=c.last_name,
        phone=c.phone,
        note=c.note,
        status=c.status,
        created_by=c.created_by,
        created_by_name=created_by_name,
        created_at=c.created_at,
        requests=requests or [],
        active_requests=active_requests,
        new_match_count=new_match_count,
    )


# ── Загрузка с проверкой прав ────────────────────────────────────────
def _load_client_for_user(db: Session, agency_id: int, user, client_id: int) -> Client:
    c = client_repo.get_client(db, agency_id, client_id)
    if c is None or (not _can_see_all(user) and c.created_by != user.id):
        # Чужого клиента «не существует» — не раскрываем факт его наличия.
        raise AppError("client_not_found", status.HTTP_404_NOT_FOUND)
    return c


def _load_request_for_user(db: Session, agency_id: int, user, request_id: int) -> ClientRequest:
    req = client_repo.get_request(db, agency_id, request_id)
    if req is None:
        raise AppError("request_not_found", status.HTTP_404_NOT_FOUND)
    _load_client_for_user(db, agency_id, user, req.client_id)  # проверка владения
    return req


# ── Клиенты ──────────────────────────────────────────────────────────
def list_clients(db: Session, agency_id: int, user, q: Optional[str] = None) -> List[ClientOut]:
    clients = client_repo.list_clients(db, agency_id, owner_id=_owner_filter(user), q=q)
    ids = [c.id for c in clients]
    active_map = client_repo.count_active_requests_by_client(db, ids)
    new_map = client_repo.count_new_matches_by_client(db, ids)
    names: dict = {}
    creator_ids = {c.created_by for c in clients if c.created_by is not None}
    if creator_ids:
        for u in user_repo.get_by_ids(db, creator_ids):
            names[u.id] = apartment_service._display_name(u)
    return [
        _client_to_out(
            c, names.get(c.created_by),
            active_requests=active_map.get(c.id, 0),
            new_match_count=new_map.get(c.id, 0),
        )
        for c in clients
    ]


def get_client_detail(db: Session, agency_id: int, user, client_id: int) -> ClientOut:
    c = _load_client_for_user(db, agency_id, user, client_id)
    reqs = client_repo.list_requests_for_client(db, c.id)
    counts = client_repo.match_counts_by_request(db, [r.id for r in reqs])
    req_outs = [_request_to_out(r, counts.get(r.id)) for r in reqs]
    name = apartment_service._display_name(user_repo.get_by_id(db, c.created_by)) if c.created_by else None
    active = sum(1 for r in reqs if r.status == "active")
    new_total = sum(counts.get(r.id, (0, 0))[1] for r in reqs)
    return _client_to_out(c, name, requests=req_outs, active_requests=active, new_match_count=new_total)


def create_client(db: Session, agency_id: int, user, payload: ClientCreate) -> Tuple[ClientOut, int]:
    client = Client(
        agency_id=agency_id,
        name=payload.name,
        last_name=(payload.last_name or None),
        phone=(payload.phone or None),
        note=(payload.note or None),
        created_by=user.id,
        status="active",
    )
    client_repo.create_client(db, client)
    found = 0
    req: Optional[ClientRequest] = None
    if payload.request is not None and not _is_empty_criteria(payload.request):
        req = _new_request(agency_id, client.id, user.id, payload.request)
        client_repo.create_request(db, req)
    db.commit()
    db.refresh(client)
    if req is not None:
        found = scan_request_against_base(db, agency_id, req)
    return get_client_detail(db, agency_id, user, client.id), found


def update_client(db: Session, agency_id: int, user, client_id: int, payload: ClientUpdate) -> ClientOut:
    c = _load_client_for_user(db, agency_id, user, client_id)
    if payload.name is not None and payload.name.strip():
        c.name = payload.name.strip()
    if payload.last_name is not None:
        c.last_name = payload.last_name.strip() or None
    if payload.phone is not None:
        c.phone = payload.phone.strip() or None
    if payload.note is not None:
        c.note = payload.note.strip() or None
    if payload.status in ("active", "archived"):
        c.status = payload.status
    # Переназначить клиента другому агенту может только администратор.
    if payload.owner_id is not None and _can_see_all(user):
        c.created_by = payload.owner_id
    db.commit()
    return get_client_detail(db, agency_id, user, client_id)


def delete_client(db: Session, agency_id: int, user, client_id: int) -> None:
    c = _load_client_for_user(db, agency_id, user, client_id)
    db.delete(c)  # каскад удалит заявки и совпадения
    db.commit()


# ── Заявки ───────────────────────────────────────────────────────────
def add_request(db: Session, agency_id: int, user, client_id: int, criteria: RequestCriteria) -> Tuple[RequestOut, int]:
    c = _load_client_for_user(db, agency_id, user, client_id)
    if _is_empty_criteria(criteria):
        raise AppError("request_empty", status.HTTP_400_BAD_REQUEST)
    req = _new_request(agency_id, c.id, user.id, criteria)
    client_repo.create_request(db, req)
    db.commit()
    found = scan_request_against_base(db, agency_id, req)
    counts = client_repo.match_counts_by_request(db, [req.id]).get(req.id)
    return _request_to_out(req, counts), found


def update_request(db: Session, agency_id: int, user, request_id: int, payload: RequestUpdate) -> RequestOut:
    req = _load_request_for_user(db, agency_id, user, request_id)
    data = payload.model_dump(exclude_unset=True)
    for f in _CRITERIA_FIELDS + ("currency", "note"):
        if f in data:
            setattr(req, f, data[f] if data[f] not in ("",) else None)
    if data.get("status") in ("active", "fulfilled", "cancelled"):
        req.status = data["status"]
    db.commit()
    # Критерии могли измениться — досканируем базу (новые совпадения добавятся).
    if req.status == "active":
        scan_request_against_base(db, agency_id, req)
    counts = client_repo.match_counts_by_request(db, [req.id]).get(req.id)
    return _request_to_out(req, counts)


def delete_request(db: Session, agency_id: int, user, request_id: int) -> None:
    req = _load_request_for_user(db, agency_id, user, request_id)
    db.delete(req)
    db.commit()


def rescan_request(db: Session, agency_id: int, user, request_id: int) -> int:
    req = _load_request_for_user(db, agency_id, user, request_id)
    return scan_request_against_base(db, agency_id, req)


# ── Совпадения ───────────────────────────────────────────────────────
def list_matches(db: Session, agency_id: int, user, statuses: Optional[List[str]] = None) -> List[MatchOut]:
    rows = client_repo.list_matches(
        db, agency_id, owner_id=_owner_filter(user), statuses=statuses, limit=100
    )
    apts = [a for _m, _r, _c, a in rows]
    apartment_service._attach_creators(db, apts)
    out: List[MatchOut] = []
    for m, r, c, a in rows:
        out.append(
            MatchOut(
                id=m.id,
                status=m.status,
                created_at=m.created_at,
                request_id=r.id,
                client_id=c.id,
                client_name=_client_full_name(c),
                request_label=_request_label(r),
                apartment=ApartmentOut.model_validate(a),
            )
        )
    return out


def new_match_count(db: Session, agency_id: int, user) -> int:
    return client_repo.count_new_matches(db, agency_id, owner_id=_owner_filter(user))


def set_match_status(db: Session, agency_id: int, user, match_id: int, new_status: str) -> None:
    if new_status not in ("new", "seen", "offered", "dismissed"):
        raise AppError("invalid_match_status", status.HTTP_400_BAD_REQUEST)
    m = client_repo.get_match(db, agency_id, match_id)
    if m is None:
        raise AppError("match_not_found", status.HTTP_404_NOT_FOUND)
    # Проверка владения: заявка совпадения должна принадлежать клиенту пользователя.
    _load_request_for_user(db, agency_id, user, m.request_id)
    m.status = new_status
    db.commit()


def mark_all_seen(db: Session, agency_id: int, user) -> int:
    """Отметить все новые совпадения пользователя просмотренными (открыл список)."""
    rows = client_repo.list_matches(
        db, agency_id, owner_id=_owner_filter(user), statuses=["new"], limit=500
    )
    for m, _r, _c, _a in rows:
        m.status = "seen"
    if rows:
        db.commit()
    return len(rows)
