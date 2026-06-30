"""
Эндпоинты клиентской базы: клиенты, заявки («что ищет»), совпадения.

Все операции изолированы по агентству (agency_id берётся из пропуска). Клиенты
личные: агент видит только своих, администратор — всех. Уведомления о совпадениях
— внутри приложения (значок-счётчик + список «Совпадения»).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.dependencies import require_agency_member
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.client import (
    ActivityCreate,
    ActivityOut,
    ClientCreate,
    ClientOut,
    ClientStatsOut,
    ClientUpdate,
    DealCreate,
    DealOut,
    DealUpdate,
    HintOut,
    MatchOut,
    MatchSummaryOut,
    NotifyPrefIn,
    RequestCreate,
    RequestOut,
    RequestUpdate,
    TaskCreate,
    TaskOut,
    TaskUpdate,
)
from app.services import client_service

router = APIRouter(prefix="/clients", tags=["clients"])


class MatchStatusIn(BaseModel):
    status: str


@router.get("", response_model=List[ClientOut])
def list_clients(
    q: Optional[str] = Query(None, description="Поиск по имени/фамилии/телефону."),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Список клиентов: агент видит своих, администратор — всех."""
    return client_service.list_clients(db, current_user.agency_id, current_user, q=q)


@router.post("", status_code=201)
def create_client(
    body: ClientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Создать клиента (+ необязательно первую заявку). Возвращает клиента и
    сколько подходящих объектов уже есть в базе (found)."""
    client, found = client_service.create_client(db, current_user.agency_id, current_user, body)
    return {"client": client, "found": found}


# ── Совпадения (объявлены ДО /{client_id}, иначе слово попадёт в id) ──
@router.get("/matches", response_model=List[MatchOut])
def list_matches(
    status: Optional[str] = Query(None, description="Фильтр: new / seen / offered / dismissed."),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Список совпадений «заявка ↔ объект» (свои — агенту, все — администратору)."""
    statuses = [status] if status else ["new", "seen", "offered"]
    return client_service.list_matches(db, current_user.agency_id, current_user, statuses=statuses)


@router.get("/matches/summary", response_model=MatchSummaryOut)
def matches_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Сколько новых совпадений (для значка-счётчика)."""
    return MatchSummaryOut(new_count=client_service.new_match_count(db, current_user.agency_id, current_user))


@router.get("/stats", response_model=ClientStatsOut)
def client_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Сводка по клиентам и сделкам для дашборда (свои — агенту, все — администратору)."""
    return client_service.client_stats(db, current_user.agency_id, current_user)


@router.patch("/notify")
def set_notify(
    body: NotifyPrefIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Частота бот-пуша о новых совпадениях: off / instant / daily."""
    value = client_service.set_match_notify(db, current_user, body.match_notify)
    return {"match_notify": value}


@router.post("/matches/seen")
def mark_all_seen(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Отметить все новые совпадения просмотренными (при открытии списка)."""
    updated = client_service.mark_all_seen(db, current_user.agency_id, current_user)
    return {"updated": updated}


@router.post("/matches/{match_id}/status", status_code=204)
def set_match_status(
    match_id: int,
    body: MatchStatusIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Сменить статус совпадения: seen / offered / dismissed / new."""
    client_service.set_match_status(db, current_user.agency_id, current_user, match_id, body.status)


# ── Заявки (объявлены ДО /{client_id}) ───────────────────────────────
@router.patch("/requests/{request_id}", response_model=RequestOut)
def update_request(
    request_id: int,
    body: RequestUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Изменить заявку (критерии и/или статус: active/fulfilled/cancelled)."""
    return client_service.update_request(db, current_user.agency_id, current_user, request_id, body)


@router.delete("/requests/{request_id}", status_code=204)
def delete_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Удалить заявку (вместе с её совпадениями)."""
    client_service.delete_request(db, current_user.agency_id, current_user, request_id)


@router.post("/requests/{request_id}/rescan")
def rescan_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Подобрать заново по существующей базе. Возвращает число новых совпадений."""
    found = client_service.rescan_request(db, current_user.agency_id, current_user, request_id)
    return {"found": found}


# ── Задачи (объявлены ДО /{client_id}, иначе «tasks» попадёт в id) ────
@router.get("/tasks", response_model=List[TaskOut])
def my_open_tasks(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Открытые задачи пользователя (свои — агенту, все — администратору)."""
    return client_service.list_my_open_tasks(db, current_user.agency_id, current_user)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def set_task_status(
    task_id: int,
    body: TaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Сменить статус задачи: open / done."""
    return client_service.set_task_status(db, current_user.agency_id, current_user, task_id, body.status)


# ── Сделки (объявлены ДО /{client_id}) ───────────────────────────────
@router.get("/deals", response_model=List[DealOut])
def my_deals(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Сделки пользователя (свои — агенту, все — администратору). Для воронки/аналитики."""
    return client_service.list_my_deals(db, current_user.agency_id, current_user)


@router.patch("/deals/{deal_id}", response_model=DealOut)
def update_deal(
    deal_id: int,
    body: DealUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Изменить сделку (этап воронки, цена, комиссия, агент, объект, заметка)."""
    return client_service.update_deal(db, current_user.agency_id, current_user, deal_id, body)


# ── Клиент по id ─────────────────────────────────────────────────────
@router.get("/{client_id}", response_model=ClientOut)
def get_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Карточка клиента с его заявками и счётчиками совпадений."""
    return client_service.get_client_detail(db, current_user.agency_id, current_user, client_id)


@router.patch("/{client_id}", response_model=ClientOut)
def update_client(
    client_id: int,
    body: ClientUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Изменить клиента (имя/телефон/заметка/статус; владельца — только админ)."""
    return client_service.update_client(db, current_user.agency_id, current_user, client_id, body)


@router.delete("/{client_id}", status_code=204)
def delete_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Удалить клиента (вместе с заявками и совпадениями)."""
    client_service.delete_client(db, current_user.agency_id, current_user, client_id)


@router.post("/{client_id}/requests", status_code=201)
def add_request(
    client_id: int,
    body: RequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Добавить заявку клиенту. Возвращает заявку и число уже подходящих объектов."""
    request, found = client_service.add_request(db, current_user.agency_id, current_user, client_id, body)
    return {"request": request, "found": found}


# ── Лента действий по клиенту (Волна 3) ──────────────────────────────
@router.get("/{client_id}/activities", response_model=List[ActivityOut])
def list_activities(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """История действий по клиенту (звонки/показы/встречи/заметки)."""
    return client_service.list_activities(db, current_user.agency_id, current_user, client_id)


@router.post("/{client_id}/activities", status_code=201, response_model=ActivityOut)
def add_activity(
    client_id: int,
    body: ActivityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Записать действие по клиенту в ленту истории."""
    return client_service.add_activity(db, current_user.agency_id, current_user, client_id, body)


# ── Задачи по клиенту (Волна 4) ──────────────────────────────────────
@router.get("/{client_id}/tasks", response_model=List[TaskOut])
def list_client_tasks(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Список задач клиента (открытые сверху)."""
    return client_service.list_tasks_for_client(db, current_user.agency_id, current_user, client_id)


@router.post("/{client_id}/tasks", status_code=201, response_model=TaskOut)
def add_client_task(
    client_id: int,
    body: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Добавить задачу клиенту."""
    return client_service.add_task(db, current_user.agency_id, current_user, client_id, body)


# ── Сделки по клиенту (Волна 5) ──────────────────────────────────────
@router.get("/{client_id}/deals", response_model=List[DealOut])
def list_client_deals(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Сделки клиента."""
    return client_service.list_deals_for_client(db, current_user.agency_id, current_user, client_id)


@router.post("/{client_id}/deals", status_code=201, response_model=DealOut)
def create_client_deal(
    client_id: int,
    body: DealCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Создать сделку для клиента (опционально с объектом)."""
    return client_service.create_deal(db, current_user.agency_id, current_user, client_id, body)


# ── ИИ-подсказки по клиенту (Волна 6) ────────────────────────────────
@router.get("/{client_id}/hints", response_model=List[HintOut])
def client_hints(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Простые подсказки по правилам: «молчит N дней», «N новых совпадений» и т.п."""
    return client_service.client_hints(db, current_user.agency_id, current_user, client_id)
