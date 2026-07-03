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
from app.db.models.deal import Deal
from app.db.models.request_match import RequestMatch
from app.repositories import apartment_repo, client_repo, user_repo
from app.schemas.apartment import ApartmentOut
from app.schemas.client import (
    ActivityCreate,
    ActivityOut,
    ClientCreate,
    ClientOut,
    ClientStatsOut,
    ClientUpdate,
    MatchOut,
    DealCreate,
    DealOut,
    DealUpdate,
    HintOut,
    RequestCriteria,
    RequestOut,
    RequestUpdate,
    TaskCreate,
    TaskOut,
)
from app.services import apartment_service, telegram_service

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
    "land_area_min", "land_area_max", "area_min", "area_max", "price_min", "price_max",
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
    # Тип сделки должен совпадать: покупателю не предлагаем аренду и наоборот
    # (цена $500/мес и $50 000 несравнимы — иначе подбор завалит покупателя арендой).
    if (getattr(req, "deal_type", "sale") or "sale") != (getattr(apt, "deal_type", "sale") or "sale"):
        return False
    if req.types and apt.type not in req.types:
        return False
    if req.districts and apt.district not in req.districts:
        return False
    # «Мягкий» режим по числовым полям: если поле в объекте НЕ заполнено — НЕ
    # отсекаем (объект покажем с пометкой «данные неполные»); отсекаем только если
    # значение есть и вышло за рамки. Бюджет (цена) — исключение, он жёсткий.
    if req.rooms_min is not None and apt.rooms is not None and apt.rooms < req.rooms_min:
        return False
    if req.rooms_max is not None and apt.rooms is not None and apt.rooms > req.rooms_max:
        return False
    if req.floor_min is not None and apt.floor is not None and apt.floor < req.floor_min:
        return False
    if req.floor_max is not None and apt.floor is not None and apt.floor > req.floor_max:
        return False
    _amin = getattr(req, "area_min", None)
    _amax = getattr(req, "area_max", None)
    _aarea = getattr(apt, "area", None)
    if _amin is not None and _aarea is not None and _aarea < _amin:
        return False
    if _amax is not None and _aarea is not None and _aarea > _amax:
        return False
    if req.land_area_min is not None and apt.land_area is not None and apt.land_area < req.land_area_min:
        return False
    if req.land_area_max is not None and apt.land_area is not None and apt.land_area > req.land_area_max:
        return False
    # Валюта: фильтр цены имеет смысл только в одной валюте (как в поиске).
    if req.currency and apt.currency != req.currency:
        return False
    if req.price_min is not None and (apt.price is None or apt.price < req.price_min):
        return False
    if req.price_max is not None and (apt.price is None or apt.price > req.price_max):
        return False
    return True


def score_match(apt: Apartment, req: ClientRequest) -> Tuple[int, dict]:
    """
    Балл совпадения 0-100 + причины {"good": [...], "missing": [...]}.

    Жёсткие фильтры (тип сделки, район, тип, валюта, цена) к этому моменту уже
    пройдены, поэтому всегда «в плюс». Балл снижают только числовые поля, которые
    клиент указал, но в объекте они НЕ заполнены — это и есть «данные неполные».
    """
    good: List[str] = []
    missing: List[str] = []
    total = 0
    got = 0

    def crit(specified: bool, weight: int, present: bool, good_label: str, miss_label: str) -> None:
        nonlocal total, got
        if not specified:
            return
        total += weight
        if present:
            got += weight
            good.append(good_label)
        else:
            missing.append(miss_label)

    # Коды (price/district/rooms/...), слова подставит фронтенд на нужном языке.
    crit(req.price_min is not None or req.price_max is not None, 30, True, "price", "price")
    crit(bool(req.districts), 25, True, "district", "district")
    crit(bool(req.types), 12, True, "type", "type")
    crit(req.rooms_min is not None or req.rooms_max is not None, 18, apt.rooms is not None, "rooms", "rooms")
    a_min = getattr(req, "area_min", None)
    a_max = getattr(req, "area_max", None)
    crit(a_min is not None or a_max is not None, 10, getattr(apt, "area", None) is not None, "area", "area")
    crit(req.floor_min is not None or req.floor_max is not None, 5, apt.floor is not None, "floor", "floor")
    crit(req.land_area_min is not None or req.land_area_max is not None, 10, apt.land_area is not None, "land", "land")

    score = 100 if total == 0 else round(got / total * 100)
    return score, {"good": good, "missing": missing}


def _request_to_search_params(req: ClientRequest) -> dict:
    return dict(
        status="active",
        deal_type=getattr(req, "deal_type", "sale") or "sale",
        types=req.types or None,
        districts=req.districts or None,
        rooms_min=req.rooms_min,
        rooms_max=req.rooms_max,
        floor_min=req.floor_min,
        floor_max=req.floor_max,
        land_area_min=req.land_area_min,
        land_area_max=req.land_area_max,
        area_min=getattr(req, "area_min", None),
        area_max=getattr(req, "area_max", None),
        # Подбор «мягкий»: объект с незаполненным числовым полем не отсекаем.
        lenient_missing=True,
        price_min=req.price_min,
        price_max=req.price_max,
        currency=req.currency,
    )


def _new_request(agency_id: int, client_id: int, created_by: Optional[int], c: RequestCriteria) -> ClientRequest:
    return ClientRequest(
        agency_id=agency_id,
        client_id=client_id,
        created_by=created_by,
        deal_type=(c.deal_type or "sale"),
        types=c.types or None,
        districts=c.districts or None,
        rooms_min=c.rooms_min,
        rooms_max=c.rooms_max,
        floor_min=c.floor_min,
        floor_max=c.floor_max,
        land_area_min=c.land_area_min,
        land_area_max=c.land_area_max,
        area_min=c.area_min,
        area_max=c.area_max,
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
    # Архивному (удалённому) клиенту совпадения не подбираем.
    c0 = client_repo.get_client_by_id(db, req.client_id)
    if c0 is not None and c0.status == "archived":
        return 0
    items, _total = apartment_repo.search(
        db, agency_id, **_request_to_search_params(req), limit=500, offset=0
    )
    existing = client_repo.existing_apartment_ids_for_request(db, req.id)
    found = 0
    for apt in items:
        if apt.id in existing:
            continue
        score, reasons = score_match(apt, req)
        if client_repo.add_match(db, agency_id, req.id, apt.id, score, reasons, source="own"):
            found += 1
            existing.add(apt.id)
    # Общая база (MLS): подходящие shared-объекты ДРУГИХ агентств (Волна 9).
    mls_params = {k: v for k, v in _request_to_search_params(req).items() if k != "lenient_missing"}
    for apt in apartment_repo.search_shared(db, agency_id, **mls_params):
        if apt.id in existing:
            continue
        score, reasons = score_match(apt, req)
        if client_repo.add_match(db, agency_id, req.id, apt.id, score, reasons, source="mls"):
            found += 1
            existing.add(apt.id)
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
    # Все активные заявки всех агентств — нужно для кросс-агентского MLS (Волна 9).
    reqs = client_repo.all_active_requests(db)
    if not reqs:
        return 0
    reqs_by_agency: dict = {}
    for r in reqs:
        if not _is_empty_criteria(r):
            reqs_by_agency.setdefault(r.agency_id, []).append(r)

    created = 0
    new_by_client: dict = {}
    existing_cache: dict = {}

    def _existing(req):
        s = existing_cache.get(req.id)
        if s is None:
            s = client_repo.existing_apartment_ids_for_request(db, req.id)
            existing_cache[req.id] = s
        return s

    def _try(req, apt, source):
        nonlocal created
        ex = _existing(req)
        if apt.id in ex:
            return
        if apartment_matches_request(apt, req):
            score, reasons = score_match(apt, req)
            if client_repo.add_match(db, req.agency_id, req.id, apt.id, score, reasons, source=source):
                created += 1
                ex.add(apt.id)
                new_by_client[req.client_id] = new_by_client.get(req.client_id, 0) + 1

    for apt in apts:
        # Своя база: новый объект против заявок СВОЕГО агентства.
        for req in reqs_by_agency.get(apt.agency_id, []):
            _try(req, apt, "own")
        # Общая база (MLS): shared-объект против заявок ДРУГИХ агентств.
        if getattr(apt, "shared_mls", False):
            for aid, group in reqs_by_agency.items():
                if aid == apt.agency_id:
                    continue
                for req in group:
                    _try(req, apt, "mls")
    db.commit()
    # Мгновенный бот-пуш агентам (Волна 8) — по их выбору и без приглушённых клиентов.
    if new_by_client:
        _notify_instant_matches(db, new_by_client)
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
        deal_type=getattr(req, "deal_type", "sale") or "sale",
        types=req.types,
        districts=req.districts,
        rooms_min=req.rooms_min,
        rooms_max=req.rooms_max,
        floor_min=req.floor_min,
        floor_max=req.floor_max,
        land_area_min=req.land_area_min,
        land_area_max=req.land_area_max,
        area_min=getattr(req, "area_min", None),
        area_max=getattr(req, "area_max", None),
        price_min=req.price_min,
        price_max=req.price_max,
        currency=req.currency,
        note=req.note,
        status=req.status,
        created_at=req.created_at,
        match_count=total,
        new_match_count=new,
    )


def _client_to_out(c: Client, created_by_name=None, *, requests=None, active_requests=0, new_match_count=0, open_tasks=0) -> ClientOut:
    return ClientOut(
        id=c.id,
        name=c.name,
        last_name=c.last_name,
        phone=c.phone,
        note=c.note,
        priority=c.priority,
        source=c.source,
        muted=c.muted,
        status=c.status,
        created_by=c.created_by,
        created_by_name=created_by_name,
        created_at=c.created_at,
        requests=requests or [],
        active_requests=active_requests,
        new_match_count=new_match_count,
        open_tasks=open_tasks,
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
def list_clients(db: Session, agency_id: int, user, q: Optional[str] = None, archived: bool = False) -> List[ClientOut]:
    clients = client_repo.list_clients(db, agency_id, owner_id=_owner_filter(user), q=q, only_archived=archived)
    ids = [c.id for c in clients]
    active_map = client_repo.count_active_requests_by_client(db, ids)
    new_map = client_repo.count_new_matches_by_client(db, ids)
    task_map = client_repo.count_open_tasks_by_client(db, ids)
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
            open_tasks=task_map.get(c.id, 0),
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
        priority=(payload.priority or None),
        source=((payload.source or "").strip() or None),
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
    if payload.priority is not None:
        pv = (payload.priority or "").strip().lower()
        if pv in ("", "none"):
            c.priority = None
        elif pv in ("hot", "warm", "cold"):
            c.priority = pv
        # некорректное значение просто игнорируем (фронт шлёт только валидные)
    if payload.source is not None:
        c.source = payload.source.strip() or None
    if payload.muted is not None:
        c.muted = bool(payload.muted)
    if payload.status is not None:
        if payload.status not in ("active", "archived"):
            raise AppError("invalid_client_status", status.HTTP_400_BAD_REQUEST)
        c.status = payload.status
    # Переназначить клиента другому агенту может только администратор — и только на
    # АКТИВНОГО сотрудника СВОЕГО агентства (защита от «увода» и висячих владельцев).
    if payload.owner_id is not None and _can_see_all(user):
        target = user_repo.get_by_id(db, payload.owner_id)
        if target is None or target.agency_id != agency_id or not target.is_active:
            raise AppError("invalid_owner", status.HTTP_400_BAD_REQUEST)
        c.created_by = payload.owner_id
    db.commit()
    return get_client_detail(db, agency_id, user, client_id)


def delete_client(db: Session, agency_id: int, user, client_id: int) -> None:
    # Мягкое удаление: помечаем «archived», НЕ стираем — история заявок и
    # совпадений сохраняется. В списке клиентов архивные не показываются;
    # вернуть можно, сменив статус обратно на active.
    c = _load_client_for_user(db, agency_id, user, client_id)
    c.status = "archived"
    db.commit()


def purge_client(db: Session, agency_id: int, user, client_id: int) -> None:
    # ПОЛНОЕ (безвозвратное) удаление: стираем клиента вместе с заявками,
    # совпадениями, задачами, сделками и историей (каскад ON DELETE на уровне БД).
    # Разрешено ТОЛЬКО для архивных — защита от случайного стирания активного клиента.
    c = _load_client_for_user(db, agency_id, user, client_id)
    if c.status != "archived":
        raise AppError("client_not_archived", status.HTTP_400_BAD_REQUEST)
    db.delete(c)
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
    # Тип сделки заявки (продажа/аренда) — только валидное значение, без None.
    if data.get("deal_type") in ("sale", "rent"):
        req.deal_type = data["deal_type"]
    if "status" in data and data["status"] is not None:
        if data["status"] not in ("active", "fulfilled", "cancelled"):
            raise AppError("invalid_request_status", status.HTTP_400_BAD_REQUEST)
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
def _rows_to_match_out(db: Session, agency_id: int, rows) -> List[MatchOut]:
    """Собрать MatchOut из строк (m, r, c, a). У MLS-совпадений (чужой объект)
    скрываем контакт владельца, точный адрес и личность чужого агента."""
    apts = [a for _m, _r, _c, a in rows]
    apartment_service._attach_creators(db, apts)
    # Названия агентств-владельцев — для MLS-совпадений (чужие объекты).
    from app.repositories import agency_repo
    ag_names: dict = {}
    ag_phones: dict = {}
    for _m, _r, _c, a in rows:
        if _m.source == "mls" and a.agency_id not in ag_names:
            ag = agency_repo.get_by_id(db, a.agency_id)
            ag_names[a.agency_id] = (ag.project_name or ag.name) if ag is not None else None
            # Контактный телефон агентства-владельца — чтобы из совпадения можно было
            # связаться (как в общей базе). Это НЕ номер собственника (тот скрыт).
            ag_phones[a.agency_id] = ag.contact_phone if ag is not None else None
    out: List[MatchOut] = []
    for m, r, c, a in rows:
        reasons = m.reasons or {}
        apt_out = ApartmentOut.model_validate(a)
        mls_agency = None
        mls_agency_id = None
        agency_phone = None
        possible_dup = False
        if m.source == "mls":
            # Скрываем контакт владельца И личность чужого агента/точный адрес
            # (Волна 9 #2 + фикс аудита H1): created_by/created_by_name = ФИО или
            # @username чужого агента, address = точный адрес — это позволяло обойти
            # агентство-владельца. Оставляем только общие характеристики + бренд агентства.
            apt_out.owner_phone = None
            apt_out.comment = None
            apt_out.source = None
            apt_out.source_link = None
            apt_out.created_by = None
            apt_out.created_by_name = None
            apt_out.address = None
            mls_agency = ag_names.get(a.agency_id)
            mls_agency_id = a.agency_id
            agency_phone = ag_phones.get(a.agency_id)
            possible_dup = client_repo.has_similar_own(db, agency_id, a.district, a.rooms, a.price, a.deal_type)
        out.append(
            MatchOut(
                id=m.id,
                status=m.status,
                created_at=m.created_at,
                request_id=r.id,
                client_id=c.id,
                client_name=_client_full_name(c),
                request_label=_request_label(r),
                score=m.score,
                match_good=list(reasons.get("good", []) or []),
                match_missing=list(reasons.get("missing", []) or []),
                source=m.source,
                mls_agency=mls_agency,
                agency_id=mls_agency_id,
                agency_phone=agency_phone,
                possible_dup=possible_dup,
                apartment=apt_out,
            )
        )
    return out


def list_matches(db: Session, agency_id: int, user, statuses: Optional[List[str]] = None) -> List[MatchOut]:
    rows = client_repo.list_matches(
        db, agency_id, owner_id=_owner_filter(user), statuses=statuses, limit=100
    )
    return _rows_to_match_out(db, agency_id, rows)


def list_client_matches(
    db: Session, agency_id: int, user, client_id: int, statuses: Optional[List[str]] = None
) -> List[MatchOut]:
    """Совпадения ОДНОГО клиента (подходящие объекты именно для него)."""
    _load_client_for_user(db, agency_id, user, client_id)  # проверка владения
    rows = client_repo.list_matches(
        db, agency_id, owner_id=_owner_filter(user), statuses=statuses, client_id=client_id, limit=200
    )
    return _rows_to_match_out(db, agency_id, rows)


def mark_client_matches_seen(db: Session, agency_id: int, user, client_id: int) -> int:
    """Отметить новые совпадения этого клиента просмотренными (значок гаснет)."""
    _load_client_for_user(db, agency_id, user, client_id)  # проверка владения
    rows = client_repo.list_matches(
        db, agency_id, owner_id=_owner_filter(user), statuses=["new"], client_id=client_id, limit=500
    )
    for m, _r, _c, _a in rows:
        m.status = "seen"
    if rows:
        db.commit()
    return len(rows)


def list_request_matches(
    db: Session, agency_id: int, user, request_id: int, statuses: Optional[List[str]] = None
) -> List[MatchOut]:
    """Совпадения ОДНОЙ заявки (у клиента может быть несколько заявок — у каждой
    свой список подходящих объектов)."""
    _load_request_for_user(db, agency_id, user, request_id)  # проверка владения
    rows = client_repo.list_matches(
        db, agency_id, owner_id=_owner_filter(user), statuses=statuses, request_id=request_id, limit=200
    )
    return _rows_to_match_out(db, agency_id, rows)


def mark_request_matches_seen(db: Session, agency_id: int, user, request_id: int) -> int:
    """Отметить новые совпадения этой заявки просмотренными (значок гаснет)."""
    _load_request_for_user(db, agency_id, user, request_id)  # проверка владения
    rows = client_repo.list_matches(
        db, agency_id, owner_id=_owner_filter(user), statuses=["new"], request_id=request_id, limit=500
    )
    for m, _r, _c, _a in rows:
        m.status = "seen"
    if rows:
        db.commit()
    return len(rows)


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


# ── Лента действий по клиенту (Волна 3) ──────────────────────────────
def add_activity(db: Session, agency_id: int, user, client_id: int, payload: ActivityCreate) -> ActivityOut:
    _load_client_for_user(db, agency_id, user, client_id)  # проверка владения
    a = client_repo.add_activity(
        db, agency_id, client_id, payload.kind, (payload.note or "").strip() or None, user.id,
    )
    db.commit()
    return ActivityOut(
        id=a.id, kind=a.kind, note=a.note, created_by=a.created_by,
        created_by_name=apartment_service._display_name(user), created_at=a.created_at,
    )


def list_activities(db: Session, agency_id: int, user, client_id: int) -> List[ActivityOut]:
    _load_client_for_user(db, agency_id, user, client_id)  # проверка владения
    rows = client_repo.list_activities(db, client_id)
    names: dict = {}
    ids = {r.created_by for r in rows if r.created_by is not None}
    if ids:
        for u in user_repo.get_by_ids(db, ids):
            names[u.id] = apartment_service._display_name(u)
    return [
        ActivityOut(
            id=r.id, kind=r.kind, note=r.note, created_by=r.created_by,
            created_by_name=names.get(r.created_by), created_at=r.created_at,
        )
        for r in rows
    ]


def delete_activity(db: Session, agency_id: int, user, activity_id: int) -> None:
    """Удалить запись истории (например, ошибочно добавленный звонок)."""
    a = client_repo.get_activity(db, agency_id, activity_id)
    if a is None:
        raise AppError("activity_not_found", status.HTTP_404_NOT_FOUND)
    _load_client_for_user(db, agency_id, user, a.client_id)  # проверка владения
    db.delete(a)
    db.commit()


# ── Задачи по клиенту (Волна 4) ──────────────────────────────────────
_AUTOTASK_IDLE_DAYS = 7


def _task_to_out(t, client_name: Optional[str] = None) -> TaskOut:
    return TaskOut(
        id=t.id, client_id=t.client_id, title=t.title, deadline=t.deadline,
        status=t.status, kind=t.kind, created_at=t.created_at, client_name=client_name,
    )


def add_task(db: Session, agency_id: int, user, client_id: int, payload: TaskCreate) -> TaskOut:
    _load_client_for_user(db, agency_id, user, client_id)  # проверка владения
    t = client_repo.add_task(db, agency_id, client_id, payload.title, payload.deadline, user.id, kind="manual")
    db.commit()
    return _task_to_out(t)


def list_tasks_for_client(db: Session, agency_id: int, user, client_id: int) -> List[TaskOut]:
    _load_client_for_user(db, agency_id, user, client_id)  # проверка владения
    return [_task_to_out(t) for t in client_repo.list_tasks_for_client(db, client_id)]


def set_task_status(db: Session, agency_id: int, user, task_id: int, new_status: str) -> TaskOut:
    if new_status not in ("open", "done"):
        raise AppError("invalid_task_status", status.HTTP_400_BAD_REQUEST)
    t = client_repo.get_task(db, agency_id, task_id)
    if t is None:
        raise AppError("task_not_found", status.HTTP_404_NOT_FOUND)
    _load_client_for_user(db, agency_id, user, t.client_id)  # проверка владения
    t.status = new_status
    t.done_at = datetime.now(timezone.utc) if new_status == "done" else None
    db.commit()
    return _task_to_out(t)


def delete_task(db: Session, agency_id: int, user, task_id: int) -> None:
    """Удалить задачу (например, ошибочно добавленную)."""
    t = client_repo.get_task(db, agency_id, task_id)
    if t is None:
        raise AppError("task_not_found", status.HTTP_404_NOT_FOUND)
    _load_client_for_user(db, agency_id, user, t.client_id)  # проверка владения
    db.delete(t)
    db.commit()


def list_my_open_tasks(db: Session, agency_id: int, user) -> List[TaskOut]:
    """Открытые задачи пользователя (агенту — свои, админу — все) с именем клиента."""
    rows = client_repo.list_open_tasks_for_user(db, agency_id, owner_id=_owner_filter(user))
    return [_task_to_out(t, client_name=_client_full_name(c)) for t, c in rows]


def run_autotask_tick(db: Session, idle_days: int = _AUTOTASK_IDLE_DAYS) -> int:
    """
    Авто-задачи: клиентам с активной заявкой, по которым нет действий idle_days+
    дней, ставим задачу «позвонить». Дубли гасим (одна открытая авто-задача на клиента).
    """
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(days=idle_days)
    clients = client_repo.clients_with_active_requests(db)
    if not clients:
        return 0
    cids = [c.id for c in clients]
    last_act = client_repo.last_activity_map(db, cids)
    busy = client_repo.client_ids_with_open_auto_task(db, cids)
    created = 0
    for c in clients:
        if c.id in busy:
            continue
        last = last_act.get(c.id) or c.created_at
        if last is None:
            continue
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if last <= threshold:
            client_repo.add_task(
                db, c.agency_id, c.id,
                f"Позвонить — клиент молчит {idle_days}+ дней",
                None, c.created_by, kind="auto",
            )
            created += 1
    if created:
        db.commit()
    return created


# ── Сделки и комиссия (Волна 5) ──────────────────────────────────────
def _name_of(db: Session, uid: Optional[int]) -> Optional[str]:
    if not uid:
        return None
    u = user_repo.get_by_id(db, uid)
    return apartment_service._display_name(u) if u else None


def _apartment_label(a: Optional[Apartment]) -> Optional[str]:
    if a is None:
        return None
    parts = [f"№{a.display_id}"]
    if a.district:
        parts.append(a.district)
    return " · ".join(parts)


def _lookup_apartment(db: Session, agency_id: int, apartment_id) -> Optional[Apartment]:
    """Объект для подписи сделки: сначала свой, затем из общей базы (MLS) —
    чтобы кросс-агентская сделка тоже показывала объект, а не пустую подпись."""
    if not apartment_id:
        return None
    return client_repo.get_agency_apartment(db, agency_id, apartment_id) or client_repo.get_shared_apartment(
        db, apartment_id
    )


def _deal_to_out(d: Deal, *, client_name=None, apartment_label=None, agent_name=None) -> DealOut:
    return DealOut(
        id=d.id, client_id=d.client_id, client_name=client_name,
        apartment_id=d.apartment_id, apartment_label=apartment_label,
        stage=d.stage,
        price=float(d.price) if d.price is not None else None, currency=d.currency,
        commission=float(d.commission) if d.commission is not None else None,
        commission_currency=d.commission_currency,
        agent_id=d.agent_id, agent_name=agent_name, note=d.note,
        created_at=d.created_at, closed_at=d.closed_at,
    )


def _valid_agent_id(db: Session, agency_id: int, agent_id):
    """Ответственный по сделке — только АКТИВНЫЙ сотрудник ЭТОГО агентства (или None).
    Фикс аудита M1: раньше agent_id из тела принимался без проверки (можно было
    подставить чужого → искажение комиссий и раскрытие имени)."""
    if agent_id is None:
        return None
    u = user_repo.get_by_id(db, agent_id)
    if u is None or u.agency_id != agency_id or not u.is_active:
        raise AppError("invalid_agent", status.HTTP_400_BAD_REQUEST)
    return agent_id


def create_deal(db: Session, agency_id: int, user, client_id: int, payload: DealCreate) -> DealOut:
    c = _load_client_for_user(db, agency_id, user, client_id)  # проверка владения
    apt = None
    seller_agency = agency_id
    if payload.apartment_id is not None:
        apt = client_repo.get_agency_apartment(db, agency_id, payload.apartment_id)
        if apt is None:
            # Объект из общей базы (MLS) другого агентства — кросс-агентская сделка.
            apt = client_repo.get_shared_apartment(db, payload.apartment_id)
        if apt is None:
            raise AppError("apartment_not_found", status.HTTP_404_NOT_FOUND)
        seller_agency = apt.agency_id
    agent_id = _valid_agent_id(db, agency_id, payload.agent_id) if payload.agent_id is not None else (c.created_by or user.id)
    d = Deal(
        agency_id=agency_id, client_id=client_id, apartment_id=(apt.id if apt else None),
        stage=payload.stage, price=payload.price, currency=payload.currency,
        commission=payload.commission, commission_currency=payload.commission_currency,
        agent_id=agent_id, seller_agency_id=seller_agency, note=(payload.note or None),
        created_by=user.id,
        closed_at=(datetime.now(timezone.utc) if payload.stage == "sold" else None),
    )
    client_repo.add_deal(db, d)
    db.commit()
    return _deal_to_out(
        d, client_name=_client_full_name(c), apartment_label=_apartment_label(apt),
        agent_name=_name_of(db, agent_id),
    )


def list_deals_for_client(db: Session, agency_id: int, user, client_id: int) -> List[DealOut]:
    c = _load_client_for_user(db, agency_id, user, client_id)  # проверка владения
    deals = client_repo.list_deals_for_client(db, client_id)
    name = _client_full_name(c)
    agent_ids = {d.agent_id for d in deals if d.agent_id}
    anames = (
        {u.id: apartment_service._display_name(u) for u in user_repo.get_by_ids(db, agent_ids)}
        if agent_ids else {}
    )
    out: List[DealOut] = []
    for d in deals:
        apt = _lookup_apartment(db, agency_id, d.apartment_id)
        out.append(_deal_to_out(
            d, client_name=name, apartment_label=_apartment_label(apt),
            agent_name=anames.get(d.agent_id),
        ))
    return out


def update_deal(db: Session, agency_id: int, user, deal_id: int, payload: DealUpdate) -> DealOut:
    d = client_repo.get_deal(db, agency_id, deal_id)
    if d is None:
        raise AppError("deal_not_found", status.HTTP_404_NOT_FOUND)
    c = _load_client_for_user(db, agency_id, user, d.client_id)  # проверка владения
    data = payload.model_dump(exclude_unset=True)
    if "apartment_id" in data:
        if data["apartment_id"] is None:
            d.apartment_id = None
            d.seller_agency_id = None  # фикс аудита #14: убрали объект — убираем и его агентство
        else:
            apt = client_repo.get_agency_apartment(db, agency_id, data["apartment_id"])
            if apt is None:
                apt = client_repo.get_shared_apartment(db, data["apartment_id"])
            if apt is None:
                raise AppError("apartment_not_found", status.HTTP_404_NOT_FOUND)
            d.apartment_id = apt.id
            d.seller_agency_id = apt.agency_id
    if "agent_id" in data:
        d.agent_id = _valid_agent_id(db, agency_id, data["agent_id"])  # фикс аудита M1
    for f in ("price", "currency", "commission", "commission_currency", "note"):
        if f in data:
            setattr(d, f, data[f] if data[f] != "" else None)
    if data.get("stage") is not None:
        d.stage = data["stage"]
        d.closed_at = datetime.now(timezone.utc) if data["stage"] == "sold" else None
    db.commit()
    apt = _lookup_apartment(db, agency_id, d.apartment_id)
    return _deal_to_out(
        d, client_name=_client_full_name(c), apartment_label=_apartment_label(apt),
        agent_name=_name_of(db, d.agent_id),
    )


def delete_deal(db: Session, agency_id: int, user, deal_id: int) -> None:
    """Удалить сделку (например, ошибочно созданную)."""
    d = client_repo.get_deal(db, agency_id, deal_id)
    if d is None:
        raise AppError("deal_not_found", status.HTTP_404_NOT_FOUND)
    _load_client_for_user(db, agency_id, user, d.client_id)  # проверка владения
    db.delete(d)
    db.commit()


def list_my_deals(db: Session, agency_id: int, user) -> List[DealOut]:
    rows = client_repo.list_deals_for_user(db, agency_id, owner_id=_owner_filter(user))
    agent_ids = {d.agent_id for d, _c, _a in rows if d.agent_id}
    anames = (
        {u.id: apartment_service._display_name(u) for u in user_repo.get_by_ids(db, agent_ids)}
        if agent_ids else {}
    )
    return [
        _deal_to_out(
            d, client_name=_client_full_name(c), apartment_label=_apartment_label(a),
            agent_name=anames.get(d.agent_id),
        )
        for d, c, a in rows
    ]


# ── ИИ-подсказки по правилам (Волна 6) ───────────────────────────────
_HINT_SILENT_DAYS = 7


def client_hints(db: Session, agency_id: int, user, client_id: int) -> List[HintOut]:
    """
    Простые подсказки по правилам (без ИИ-модели): «молчит N дней», «N новых
    совпадений», «N объектов подходят», «нет активной заявки». Считаются из уже
    имеющихся данных (заявки, совпадения, история).
    """
    c = _load_client_for_user(db, agency_id, user, client_id)  # проверка владения
    hints: List[HintOut] = []
    reqs = client_repo.list_requests_for_client(db, c.id)
    active_reqs = [r for r in reqs if r.status == "active"]
    if not active_reqs:
        hints.append(HintOut(kind="no_request"))
    counts = client_repo.match_counts_by_request(db, [r.id for r in reqs])
    total = sum(counts.get(r.id, (0, 0))[0] for r in reqs)
    new = sum(counts.get(r.id, (0, 0))[1] for r in reqs)
    if new > 0:
        hints.append(HintOut(kind="new_matches", count=new))
    elif total > 0:
        hints.append(HintOut(kind="total_matches", count=total))
    last_map = client_repo.last_activity_map(db, [c.id])
    last = last_map.get(c.id) or c.created_at
    if last is not None and active_reqs:
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - last).days
        if days >= _HINT_SILENT_DAYS:
            hints.append(HintOut(kind="silent", days=days))
    return hints


# ── Сводка для дашборда (Волна 7) ────────────────────────────────────
def client_stats(db: Session, agency_id: int, user) -> ClientStatsOut:
    """Сводка по клиентам и сделкам: агенту — свои, администратору — все."""
    of = _owner_filter(user)
    sc = client_repo.deal_stage_counts(db, agency_id, owner_id=of)
    won = sc.get("sold", 0)
    active = sum(n for st, n in sc.items() if st not in ("sold", "cancelled"))
    return ClientStatsOut(
        clients=client_repo.count_clients(db, agency_id, owner_id=of),
        in_search=client_repo.count_clients_in_search(db, agency_id, owner_id=of),
        deals_active=active,
        deals_won=won,
    )


# ── Уведомления о совпадениях: бот-пуш (Волна 8) ──────────────────────
def _notify_instant_matches(db: Session, new_by_client: dict) -> None:
    """Мгновенный пуш агенту по каждому клиенту (если выбрал 'instant' и не приглушил)."""
    if not telegram_service.is_configured():
        return
    owners: dict = {}
    for client_id, count in new_by_client.items():
        c = client_repo.get_client_by_id(db, client_id)
        if c is None or c.muted or c.status == "archived" or c.created_by is None:
            continue
        owner = owners.get(c.created_by)
        if owner is None:
            owner = user_repo.get_by_id(db, c.created_by)
            owners[c.created_by] = owner
        if owner is None or not owner.is_active or not owner.telegram_id:
            continue
        if getattr(owner, "match_notify", "instant") != "instant":
            continue
        name = _client_full_name(c)
        text = (
            f"🔔 Новый подходящий объект для клиента «{name}»: {count}. "
            f"Откройте «Совпадения» в приложении."
        )
        telegram_service.send_message(owner.telegram_id, text)


def run_match_digest(db: Session, since: datetime) -> int:
    """Суточный дайджест: одному агенту — одна сводка о новых совпадениях (выбор 'daily')."""
    if not telegram_service.is_configured():
        return 0
    counts = client_repo.digest_match_counts(db, since)
    sent = 0
    for owner_id, count in counts.items():
        u = user_repo.get_by_id(db, owner_id)
        if u is None or not u.is_active or not u.telegram_id:
            continue
        if getattr(u, "match_notify", "instant") != "daily":
            continue
        text = (
            f"🔔 За сутки: {count} новых подходящих объектов для ваших клиентов. "
            f"Откройте «Совпадения»."
        )
        if telegram_service.send_message(u.telegram_id, text):
            sent += 1
    return sent


def set_match_notify(db: Session, user, value: str) -> str:
    """Сохранить выбор частоты уведомлений текущего пользователя (off/instant/daily)."""
    if value not in ("off", "instant", "daily"):
        raise AppError("invalid_notify_pref", status.HTTP_400_BAD_REQUEST)
    u = user_repo.get_by_id(db, user.id)
    if u is None:
        raise AppError("user_not_found", status.HTTP_404_NOT_FOUND)
    u.match_notify = value
    db.commit()
    return value
