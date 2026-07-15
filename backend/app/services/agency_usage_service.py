"""
Наблюдение за агентствами (использование) — для владельца платформы.

Считает по уже существующим данным (новые таблицы НЕ нужны):
  - apartments     — сколько объектов, по статусам/типу сделки, КОГДА добавлены
                     (по дням), КАК добавлены (source: вручную/ссылка/канал);
  - apartment_events — последняя активность по объектам;
  - audit_log      — входы (action='login') и последняя активность;
  - users.last_login_at — кто из сотрудников когда заходил.

Дни считаются в часовом поясе агентства (agencies.timezone, по умолчанию
Asia/Tashkent) — чтобы «сегодня/вчера» совпадали с местным днём.

Всё под require_superadmin (вызывается из роутов agencies).
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import status as http_status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from app.core.errors import AppError
from app.db.models.apartment import Apartment
from app.db.models.apartment_event import ApartmentEvent
from app.db.models.audit_log import AuditLog
from app.db.models.client import Client
from app.db.models.deal import DEAL_REVENUE_STAGES, Deal
from app.db.models.user import User
from app.repositories import agency_repo, apartment_repo
from app.services import user_presence
from app.schemas.agency import (
    AgencyActivityOut,
    AgencyUsageOut,
    DailyCountOut,
    EmployeeActivityOut,
)
from app.services.apartment_service import _display_name

# Пороги «светофора» вовлечённости (в днях). Агентства новые — берём узко.
_ACTIVE_DAYS = 3      # активность за последние N дней → 🟢
_QUIET_DAYS = 10      # 3–10 дней тишины → 🟡; больше → 🔴
_NEW_DAYS = 3         # создано недавно и ещё ноль действий → ⚪ «Новое»
# Сколько дней показывать в дневной разбивке (карточка агентства).
_DAILY_DAYS = 14
_FALLBACK_TZ = "Asia/Tashkent"
# Порог «в сети» — единый, из user_presence.ONLINE_WITHIN (см. _is_online ниже).


def _tz(tzname: Optional[str]):
    if ZoneInfo is None:
        return timezone(timedelta(hours=5))  # UTC+5 (Ташкент) как запас
    try:
        return ZoneInfo(tzname or _FALLBACK_TZ)
    except Exception:  # noqa: BLE001
        return ZoneInfo(_FALLBACK_TZ)


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _local_day_start_utc(now_utc: datetime, tz, days_ago: int = 0) -> datetime:
    """Начало местного дня (минус days_ago суток), выраженное в UTC."""
    local = now_utc.astimezone(tz)
    d = (local - timedelta(days=days_ago)).date()
    start_local = datetime(d.year, d.month, d.day, tzinfo=tz)
    return start_local.astimezone(timezone.utc)


def _tz_name(tzname: Optional[str]) -> str:
    """Безопасное имя пояса для SQL (func.timezone): кривое значение из БД не
    должно ронять запрос активности — откатываемся на Asia/Tashkent."""
    name = tzname or _FALLBACK_TZ
    if ZoneInfo is None:
        return _FALLBACK_TZ
    try:
        ZoneInfo(name)
        return name
    except Exception:  # noqa: BLE001
        return _FALLBACK_TZ


# ── Список: компактная сводка по всем клиентским агентствам ───────────
def _count_by_agency(db: Session, ids, *extra) -> Dict[int, int]:
    q = (
        select(Apartment.agency_id, func.count())
        .where(Apartment.agency_id.in_(ids), *extra)
        .group_by(Apartment.agency_id)
    )
    return {row[0]: row[1] for row in db.execute(q)}


def _logins_by_agency(db: Session, ids, since: datetime) -> Dict[int, int]:
    q = (
        select(AuditLog.agency_id, func.count())
        .where(AuditLog.agency_id.in_(ids), AuditLog.action == "login", AuditLog.created_at >= since)
        .group_by(AuditLog.agency_id)
    )
    return {row[0]: row[1] for row in db.execute(q)}


def _last_activity_by_agency(db: Session, ids) -> Dict[int, datetime]:
    out: Dict[int, datetime] = {}
    ev = (
        select(ApartmentEvent.agency_id, func.max(ApartmentEvent.created_at))
        .where(ApartmentEvent.agency_id.in_(ids))
        .group_by(ApartmentEvent.agency_id)
    )
    au = (
        select(AuditLog.agency_id, func.max(AuditLog.created_at))
        .where(AuditLog.agency_id.in_(ids))
        .group_by(AuditLog.agency_id)
    )
    for aid, ts in db.execute(ev):
        if ts is not None:
            out[aid] = ts
    for aid, ts in db.execute(au):
        if ts is not None and (aid not in out or ts > out[aid]):
            out[aid] = ts
    return out


def _users_by_agency(db: Session, ids, since: datetime):
    total = {
        row[0]: row[1]
        for row in db.execute(
            select(User.agency_id, func.count())
            .where(User.agency_id.in_(ids), User.is_active.is_(True))
            .group_by(User.agency_id)
        )
    }
    active = {
        row[0]: row[1]
        for row in db.execute(
            select(User.agency_id, func.count())
            .where(User.agency_id.in_(ids), User.is_active.is_(True), User.last_login_at >= since)
            .group_by(User.agency_id)
        )
    }
    return total, active


def _engagement(created_at, last_activity, total: int, now: datetime) -> str:
    la = _as_utc(last_activity)
    if la is None:
        age = (now - (_as_utc(created_at) or now)).days
        return "new" if (age <= _NEW_DAYS and total == 0) else "asleep"
    days = (now - la).days
    if days <= _ACTIVE_DAYS:
        return "active"
    if days <= _QUIET_DAYS:
        return "quiet"
    return "asleep"


def usage_list(db: Session) -> List[AgencyUsageOut]:
    """Сводка использования по всем КЛИЕНТСКИМ агентствам (для списка)."""
    agencies = agency_repo.get_clients(db)
    ids = [a.id for a in agencies]
    if not ids:
        return []
    now = datetime.now(timezone.utc)
    # «Сегодня» для списка считаем в общем поясе Ташкента (все агентства в UZ).
    today0 = _local_day_start_utc(now, _tz(_FALLBACK_TZ), 0)
    since7 = now - timedelta(days=7)
    since30 = now - timedelta(days=30)

    nd = Apartment.deleted_at.is_(None)
    total_map = _count_by_agency(db, ids, nd)
    today_map = _count_by_agency(db, ids, nd, Apartment.created_at >= today0)
    d7_map = _count_by_agency(db, ids, nd, Apartment.created_at >= since7)
    d30_map = _count_by_agency(db, ids, nd, Apartment.created_at >= since30)
    logins7 = _logins_by_agency(db, ids, since7)
    last_act = _last_activity_by_agency(db, ids)
    users_total, users_active = _users_by_agency(db, ids, since7)

    out: List[AgencyUsageOut] = []
    for a in agencies:
        out.append(
            AgencyUsageOut(
                agency_id=a.id,
                objects_total=total_map.get(a.id, 0),
                added_today=today_map.get(a.id, 0),
                added_7d=d7_map.get(a.id, 0),
                added_30d=d30_map.get(a.id, 0),
                logins_7d=logins7.get(a.id, 0),
                active_users=users_active.get(a.id, 0),
                total_users=users_total.get(a.id, 0),
                last_activity_at=last_act.get(a.id),
                engagement=_engagement(a.created_at, last_act.get(a.id), total_map.get(a.id, 0), now),
            )
        )
    return out


# ── Детальный отчёт по одному агентству ──────────────────────────────
def _scalar_count(db: Session, *where) -> int:
    return db.execute(select(func.count()).select_from(Apartment).where(*where)).scalar() or 0


def activity(db: Session, agency_id: int) -> AgencyActivityOut:
    agency = agency_repo.get_by_id(db, agency_id)
    if agency is None:
        raise AppError("agency_not_found", http_status.HTTP_404_NOT_FOUND)
    tzname = _tz_name(agency.timezone)  # безопасно для func.timezone в SQL
    tz = _tz(tzname)
    now = datetime.now(timezone.utc)

    # Объекты по статусам и типу сделки (без удалённых).
    not_deleted = Apartment.deleted_at.is_(None)
    st = {
        k: v
        for k, v in db.execute(
            select(Apartment.status, func.count())
            .where(Apartment.agency_id == agency_id, not_deleted)
            .group_by(Apartment.status)
        )
    }
    dl = {
        (k or "sale"): v
        for k, v in db.execute(
            select(Apartment.deal_type, func.count())
            .where(Apartment.agency_id == agency_id, not_deleted)
            .group_by(Apartment.deal_type)
        )
    }
    total = sum(st.values())

    # Дневная разбивка добавлений (последние _DAILY_DAYS дней, местный день).
    since_daily = _local_day_start_utc(now, tz, _DAILY_DAYS - 1)
    bucket = func.date_trunc("day", func.timezone(tzname, Apartment.created_at))
    drows = db.execute(
        select(bucket, func.count())
        .where(Apartment.agency_id == agency_id, not_deleted, Apartment.created_at >= since_daily)
        .group_by(bucket)
    ).all()
    dmap: Dict[object, int] = {}
    for d, c in drows:
        key = d.date() if hasattr(d, "date") else d
        dmap[key] = c
    today_local = now.astimezone(tz).date()
    daily: List[DailyCountOut] = []
    for i in range(_DAILY_DAYS - 1, -1, -1):
        day = today_local - timedelta(days=i)
        daily.append(DailyCountOut(date=day.isoformat(), added=dmap.get(day, 0)))
    added_today = dmap.get(today_local, 0)
    added_yesterday = dmap.get(today_local - timedelta(days=1), 0)
    added_2d = dmap.get(today_local - timedelta(days=2), 0)

    since7 = now - timedelta(days=7)
    since30 = now - timedelta(days=30)
    added_7d = _scalar_count(db, Apartment.agency_id == agency_id, not_deleted, Apartment.created_at >= since7)
    added_30d = _scalar_count(db, Apartment.agency_id == agency_id, not_deleted, Apartment.created_at >= since30)

    # Как добавляют: вручную / по ссылке (по одному) / массовый импорт из канала /
    # авто-импорт из отслеживаемого канала. Считаем по added_via; у старых объектов
    # (added_via NULL) выводим из source (канал → авто, домен → по ссылке).
    manual = link = bulk = auto = 0
    for via, s, c in db.execute(
        select(Apartment.added_via, Apartment.source, func.count())
        .where(Apartment.agency_id == agency_id, not_deleted)
        .group_by(Apartment.added_via, Apartment.source)
    ):
        v = via
        if v is None:
            v = "manual" if not s else ("auto" if str(s).startswith("@") else "link")
        if v == "manual":
            manual += c
        elif v == "bulk":
            bulk += c
        elif v == "auto":
            auto += c
        else:  # link и всё прочее — «по одному / по ссылке»
            link += c

    # Входы (логины) за 7/30 дней.
    def _logins(since):
        return db.execute(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.agency_id == agency_id, AuditLog.action == "login", AuditLog.created_at >= since)
        ).scalar() or 0

    logins_7d = _logins(since7)
    logins_30d = _logins(since30)

    # Сотрудники: активные/всего + последняя активность.
    total_users = db.execute(
        select(func.count()).select_from(User).where(User.agency_id == agency_id, User.is_active.is_(True))
    ).scalar() or 0
    active_users = db.execute(
        select(func.count())
        .select_from(User)
        .where(User.agency_id == agency_id, User.is_active.is_(True), User.last_login_at >= since7)
    ).scalar() or 0
    last_act = _last_activity_by_agency(db, [agency_id]).get(agency_id)

    # ── Сделки и комиссия агентства (Волна 7) ───────────────────────
    deal_counts = {
        s: int(n)
        for s, n in db.execute(
            select(Deal.stage, func.count()).where(Deal.agency_id == agency_id).group_by(Deal.stage)
        )
    }
    deals_total = sum(deal_counts.values())
    deals_won = deal_counts.get("sold", 0)
    deals_active = sum(n for stg, n in deal_counts.items() if stg not in ("sold", "cancelled"))
    # Выручка (комиссия) по валютам — со сделок «деньги» (задаток и далее).
    revenue: Dict[str, float] = {}
    for cur, ssum in db.execute(
        select(Deal.commission_currency, func.sum(Deal.commission))
        .where(Deal.agency_id == agency_id, Deal.stage.in_(DEAL_REVENUE_STAGES), Deal.commission.is_not(None))
        .group_by(Deal.commission_currency)
    ):
        if ssum is not None:
            revenue[cur or "?"] = float(ssum)
    clients_total = db.execute(
        select(func.count()).select_from(Client).where(Client.agency_id == agency_id, Client.status != "archived")
    ).scalar() or 0
    # По сотрудникам: продано + комиссия по валютам.
    emp_won: Dict[int, int] = {}
    for aid, n in db.execute(
        select(Deal.agent_id, func.count())
        .where(Deal.agency_id == agency_id, Deal.stage == "sold", Deal.agent_id.is_not(None))
        .group_by(Deal.agent_id)
    ):
        emp_won[aid] = int(n)
    emp_comm: Dict[int, Dict[str, float]] = {}
    for aid, cur, ssum in db.execute(
        select(Deal.agent_id, Deal.commission_currency, func.sum(Deal.commission))
        .where(
            Deal.agency_id == agency_id,
            Deal.stage.in_(DEAL_REVENUE_STAGES),
            Deal.commission.is_not(None),
            Deal.agent_id.is_not(None),
        )
        .group_by(Deal.agent_id, Deal.commission_currency)
    ):
        if ssum is not None:
            emp_comm.setdefault(aid, {})[cur or "?"] = float(ssum)

    # По сотрудникам: сколько добавил + когда заходил.
    added_by = {cid: tot for cid, tot, _sold, _rented in apartment_repo.stats_by_creator(db, agency_id)}
    users = db.execute(
        select(User).where(User.agency_id == agency_id, User.is_active.is_(True))
    ).scalars().all()
    # Единый источник правды порогов «в сети» — user_presence (тот же порог, что и
    # в карточке юзера у владельца платформы), чтобы экраны не расходились.
    def _is_online(seen) -> bool:
        return user_presence.presence(seen, now) == "online"

    employees = [
        EmployeeActivityOut(
            user_id=u.id,
            name=_display_name(u),
            last_login_at=u.last_login_at,
            last_seen_at=u.last_seen_at,
            # Последняя активность = МАКСИМУМ(seen, login) — как в платформенной
            # карточке; раньше экран агентства брал seen||login (coalesce) и расходился.
            last_active_at=user_presence.latest(u.last_seen_at, u.last_login_at),
            online=_is_online(u.last_seen_at),
            added=added_by.get(u.id, 0),
            deals_won=emp_won.get(u.id, 0),
            commission=emp_comm.get(u.id, {}),
        )
        for u in users
    ]
    online_users = sum(1 for u in users if _is_online(u.last_seen_at))
    # Сортировка: нормализуем last_login_at к aware-UTC, иначе при равном
    # «added» сравнение naive vs aware дат бросило бы TypeError.
    _min = datetime.min.replace(tzinfo=timezone.utc)
    employees.sort(key=lambda e: (e.added, _as_utc(e.last_login_at) or _min), reverse=True)

    return AgencyActivityOut(
        objects_total=total,
        active=st.get("active", 0),
        deposit=st.get("deposit", 0),
        sold=st.get("sold", 0),
        rented=st.get("rented", 0),
        sale=dl.get("sale", 0),
        rent=dl.get("rent", 0),
        added_today=added_today,
        added_yesterday=added_yesterday,
        added_2d=added_2d,
        added_7d=added_7d,
        added_30d=added_30d,
        daily=daily,
        source_manual=manual,
        source_link=link,
        source_channel=bulk + auto,
        added_bulk=bulk,
        added_auto=auto,
        logins_7d=logins_7d,
        logins_30d=logins_30d,
        active_users=active_users,
        total_users=total_users,
        online_users=online_users,
        last_activity_at=last_act,
        clients_total=clients_total,
        deals_total=deals_total,
        deals_active=deals_active,
        deals_won=deals_won,
        revenue=revenue,
        employees=employees,
    )
