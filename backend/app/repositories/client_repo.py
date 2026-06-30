"""
Доступ к данным клиентской базы: клиенты, заявки, совпадения.

Все запросы обязательно фильтруются по agency_id (изоляция агентств). Личные
клиенты: фильтр по created_by (агент видит только своих); администратор видит
всех (owner_id не передаётся).
"""
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.apartment import Apartment
from app.db.models.client import Client
from app.db.models.client_activity import ClientActivity
from app.db.models.client_request import ClientRequest
from app.db.models.request_match import RequestMatch
from app.db.models.task import Task


# ── Клиенты ──────────────────────────────────────────────────────────
def create_client(db: Session, client: Client) -> Client:
    db.add(client)
    db.flush()
    return client


def get_client(db: Session, agency_id: int, client_id: int) -> Optional[Client]:
    return db.execute(
        select(Client).where(Client.id == client_id, Client.agency_id == agency_id)
    ).scalar_one_or_none()


def list_clients(
    db: Session,
    agency_id: int,
    *,
    owner_id: Optional[int] = None,
    q: Optional[str] = None,
    include_archived: bool = False,
) -> List[Client]:
    conds = [Client.agency_id == agency_id]
    if owner_id is not None:
        conds.append(Client.created_by == owner_id)
    if not include_archived:
        conds.append(Client.status != "archived")
    if q and q.strip():
        like = f"%{q.strip()}%"
        conds.append(or_(Client.name.ilike(like), Client.last_name.ilike(like), Client.phone.ilike(like)))
    return list(
        db.execute(
            select(Client).where(*conds).order_by(Client.created_at.desc())
        ).scalars().all()
    )


def count_active_requests_by_client(db: Session, client_ids: Sequence[int]) -> Dict[int, int]:
    if not client_ids:
        return {}
    rows = db.execute(
        select(ClientRequest.client_id, func.count())
        .where(ClientRequest.client_id.in_(list(client_ids)), ClientRequest.status == "active")
        .group_by(ClientRequest.client_id)
    ).all()
    return {cid: int(n) for cid, n in rows}


def count_new_matches_by_client(db: Session, client_ids: Sequence[int]) -> Dict[int, int]:
    """Сколько новых (не просмотренных) совпадений у каждого клиента."""
    if not client_ids:
        return {}
    rows = db.execute(
        select(ClientRequest.client_id, func.count())
        .join(RequestMatch, RequestMatch.request_id == ClientRequest.id)
        .where(ClientRequest.client_id.in_(list(client_ids)), RequestMatch.status == "new")
        .group_by(ClientRequest.client_id)
    ).all()
    return {cid: int(n) for cid, n in rows}


# ── Заявки ───────────────────────────────────────────────────────────
def create_request(db: Session, req: ClientRequest) -> ClientRequest:
    db.add(req)
    db.flush()
    return req


def get_request(db: Session, agency_id: int, request_id: int) -> Optional[ClientRequest]:
    return db.execute(
        select(ClientRequest).where(
            ClientRequest.id == request_id, ClientRequest.agency_id == agency_id
        )
    ).scalar_one_or_none()


def list_requests_for_client(db: Session, client_id: int) -> List[ClientRequest]:
    return list(
        db.execute(
            select(ClientRequest)
            .where(ClientRequest.client_id == client_id)
            .order_by(ClientRequest.created_at.desc())
        ).scalars().all()
    )


def active_requests_for_agencies(db: Session, agency_ids: Sequence[int]) -> List[ClientRequest]:
    if not agency_ids:
        return []
    return list(
        db.execute(
            select(ClientRequest).where(
                ClientRequest.agency_id.in_(list(agency_ids)),
                ClientRequest.status == "active",
            )
        ).scalars().all()
    )


def match_counts_by_request(db: Session, request_ids: Sequence[int]) -> Dict[int, Tuple[int, int]]:
    """Для каждой заявки: (всего совпадений кроме отклонённых, из них новых)."""
    if not request_ids:
        return {}
    total_expr = func.count()
    new_expr = func.sum(case((RequestMatch.status == "new", 1), else_=0))
    rows = db.execute(
        select(RequestMatch.request_id, total_expr, new_expr)
        .where(RequestMatch.request_id.in_(list(request_ids)), RequestMatch.status != "dismissed")
        .group_by(RequestMatch.request_id)
    ).all()
    return {rid: (int(total), int(new or 0)) for rid, total, new in rows}


# ── Совпадения «заявка ↔ объект» ─────────────────────────────────────
def existing_apartment_ids_for_request(db: Session, request_id: int) -> set:
    rows = db.execute(
        select(RequestMatch.apartment_id).where(RequestMatch.request_id == request_id)
    ).all()
    return {r[0] for r in rows}


def add_match(
    db: Session,
    agency_id: int,
    request_id: int,
    apartment_id: int,
    score: Optional[int] = None,
    reasons: Optional[dict] = None,
) -> bool:
    """
    Создать совпадение. Возвращает True, если оно реально создано (False — если
    такая пара уже была). Гонку (одновременный подбор из двух мест) гасим через
    SAVEPOINT + уникальное ограничение (request_id, apartment_id).
    """
    try:
        with db.begin_nested():
            db.add(
                RequestMatch(
                    agency_id=agency_id,
                    request_id=request_id,
                    apartment_id=apartment_id,
                    status="new",
                    score=score,
                    reasons=reasons,
                )
            )
        return True
    except IntegrityError:
        return False


def get_match(db: Session, agency_id: int, match_id: int) -> Optional[RequestMatch]:
    return db.execute(
        select(RequestMatch).where(
            RequestMatch.id == match_id, RequestMatch.agency_id == agency_id
        )
    ).scalar_one_or_none()


def list_matches(
    db: Session,
    agency_id: int,
    *,
    owner_id: Optional[int] = None,
    statuses: Optional[Sequence[str]] = None,
    limit: int = 100,
) -> List[Tuple[RequestMatch, ClientRequest, Client, Apartment]]:
    conds = [RequestMatch.agency_id == agency_id]
    if statuses:
        conds.append(RequestMatch.status.in_(list(statuses)))
    if owner_id is not None:
        conds.append(Client.created_by == owner_id)
    rows = db.execute(
        select(RequestMatch, ClientRequest, Client, Apartment)
        .join(ClientRequest, RequestMatch.request_id == ClientRequest.id)
        .join(Client, ClientRequest.client_id == Client.id)
        .join(Apartment, RequestMatch.apartment_id == Apartment.id)
        .where(*conds)
        .order_by(RequestMatch.created_at.desc())
        .limit(limit)
    ).all()
    return [(m, r, c, a) for m, r, c, a in rows]


def count_new_matches(db: Session, agency_id: int, *, owner_id: Optional[int] = None) -> int:
    conds = [RequestMatch.agency_id == agency_id, RequestMatch.status == "new"]
    stmt = (
        select(func.count())
        .select_from(RequestMatch)
        .join(ClientRequest, RequestMatch.request_id == ClientRequest.id)
        .join(Client, ClientRequest.client_id == Client.id)
        .where(*conds)
    )
    if owner_id is not None:
        stmt = stmt.where(Client.created_by == owner_id)
    return int(db.execute(stmt).scalar_one())


# ── Для фонового подбора ─────────────────────────────────────────────
def recent_active_apartments(db: Session, since: datetime) -> List[Apartment]:
    """Активные объекты, созданные не раньше since (для подбора по новым)."""
    return list(
        db.execute(
            select(Apartment).where(
                Apartment.created_at >= since,
                Apartment.status == "active",
                Apartment.deleted_at.is_(None),
            )
        ).scalars().all()
    )


# ── Лента действий по клиенту (Волна 3) ──────────────────────────────
def add_activity(
    db: Session, agency_id: int, client_id: int, kind: str,
    note: Optional[str], created_by: Optional[int],
) -> ClientActivity:
    a = ClientActivity(
        agency_id=agency_id, client_id=client_id, kind=kind, note=note, created_by=created_by,
    )
    db.add(a)
    db.flush()
    return a


def list_activities(db: Session, client_id: int, limit: int = 50) -> List[ClientActivity]:
    return list(
        db.execute(
            select(ClientActivity)
            .where(ClientActivity.client_id == client_id)
            .order_by(ClientActivity.created_at.desc())
            .limit(limit)
        ).scalars().all()
    )


def last_activity_map(db: Session, client_ids: Sequence[int]) -> Dict[int, datetime]:
    """Для каждого клиента — время последнего действия (для ИИ-подсказок «молчит»)."""
    if not client_ids:
        return {}
    rows = db.execute(
        select(ClientActivity.client_id, func.max(ClientActivity.created_at))
        .where(ClientActivity.client_id.in_(list(client_ids)))
        .group_by(ClientActivity.client_id)
    ).all()
    return {cid: ts for cid, ts in rows}


# ── Задачи по клиенту (Волна 4) ──────────────────────────────────────
def add_task(
    db: Session, agency_id: int, client_id: int, title: str,
    deadline, created_by: Optional[int], kind: str = "manual",
) -> Task:
    t = Task(
        agency_id=agency_id, client_id=client_id, title=title,
        deadline=deadline, created_by=created_by, kind=kind,
    )
    db.add(t)
    db.flush()
    return t


def get_task(db: Session, agency_id: int, task_id: int) -> Optional[Task]:
    return db.execute(
        select(Task).where(Task.id == task_id, Task.agency_id == agency_id)
    ).scalar_one_or_none()


def list_tasks_for_client(db: Session, client_id: int) -> List[Task]:
    # open (o) перед done (d) — status.desc(); внутри — новые сверху.
    return list(
        db.execute(
            select(Task)
            .where(Task.client_id == client_id)
            .order_by(Task.status.desc(), Task.created_at.desc())
        ).scalars().all()
    )


def list_open_tasks_for_user(
    db: Session, agency_id: int, *, owner_id: Optional[int] = None, limit: int = 100,
) -> List[Tuple[Task, Client]]:
    conds = [Task.agency_id == agency_id, Task.status == "open"]
    stmt = select(Task, Client).join(Client, Task.client_id == Client.id).where(*conds)
    if owner_id is not None:
        stmt = stmt.where(Client.created_by == owner_id)
    stmt = stmt.order_by(Task.created_at.desc()).limit(limit)
    return [(t, c) for t, c in db.execute(stmt).all()]


def count_open_tasks_by_client(db: Session, client_ids: Sequence[int]) -> Dict[int, int]:
    if not client_ids:
        return {}
    rows = db.execute(
        select(Task.client_id, func.count())
        .where(Task.client_id.in_(list(client_ids)), Task.status == "open")
        .group_by(Task.client_id)
    ).all()
    return {cid: int(n) for cid, n in rows}


def clients_with_active_requests(db: Session) -> List[Client]:
    """Неархивные клиенты, у которых есть хотя бы одна активная заявка (для авто-задач)."""
    sub = select(ClientRequest.client_id).where(ClientRequest.status == "active")
    return list(
        db.execute(
            select(Client).where(Client.status != "archived", Client.id.in_(sub))
        ).scalars().all()
    )


def client_ids_with_open_auto_task(db: Session, client_ids: Sequence[int]) -> set:
    if not client_ids:
        return set()
    rows = db.execute(
        select(Task.client_id).where(
            Task.client_id.in_(list(client_ids)),
            Task.status == "open",
            Task.kind == "auto",
        )
    ).all()
    return {r[0] for r in rows}
