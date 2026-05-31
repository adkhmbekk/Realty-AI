"""
Эндпоинты объектов недвижимости.

Создание/редактирование/архив/восстановление/продан/удаление — любой сотрудник
агентства (агент или админ). Все операции изолированы по агентству: agency_id
берётся из текущего пользователя (из его пропуска), а не из параметров запроса.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import require_agency_member
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.apartment import (
    ApartmentCreate,
    ApartmentEventOut,
    ApartmentListOut,
    ApartmentOut,
    ApartmentShareOut,
    ApartmentStatsOut,
    ApartmentStatusUpdate,
    ApartmentUpdate,
)
from app.services import apartment_service

router = APIRouter(prefix="/apartments", tags=["apartments"])


@router.post("", response_model=ApartmentOut, status_code=201)
def create_apartment(
    body: ApartmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Создать объект. ID (display_id) генерируется автоматически."""
    return apartment_service.create_apartment(
        db, current_user.agency_id, created_by=current_user.id, payload=body
    )


@router.get("", response_model=ApartmentListOut)
def search_apartments(
    status: Optional[str] = Query(
        "active",
        description="Статус: active / deposit / sold / archived / unsold. 'all' — все статусы.",
    ),
    districts: Optional[List[str]] = Query(None, description="Районы (можно несколько)."),
    types: Optional[List[str]] = Query(None, description="Типы (можно несколько)."),
    rooms: Optional[List[int]] = Query(None, description="Кол-во комнат (можно несколько)."),
    rooms_min: Optional[int] = Query(None, description="Комнат от (диапазон)."),
    rooms_max: Optional[int] = Query(None, description="Комнат до (диапазон)."),
    floor_min: Optional[int] = Query(None, description="Этаж от."),
    floor_max: Optional[int] = Query(None, description="Этаж до."),
    price_min: Optional[float] = Query(None, description="Цена от."),
    price_max: Optional[float] = Query(None, description="Цена до."),
    agent_id: Optional[int] = Query(None, description="Фильтр по агенту."),
    q: Optional[str] = Query(None, description="Текстовый поиск: наименование, адрес, номер объекта."),
    limit: int = Query(50, ge=1, le=200, description="Сколько вернуть (1–200)."),
    offset: int = Query(0, ge=0, description="Смещение для пагинации."),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Поиск/список объектов своего агентства с фильтрами и пагинацией."""
    # 'all' → показать все статусы (передаём None в сервис).
    status_filter = None if status == "all" else status
    items, total = apartment_service.search_apartments(
        db,
        current_user.agency_id,
        status_filter=status_filter,
        districts=districts,
        types=types,
        rooms=rooms,
        rooms_min=rooms_min,
        rooms_max=rooms_max,
        floor_min=floor_min,
        floor_max=floor_max,
        price_min=price_min,
        price_max=price_max,
        agent_id=agent_id,
        q=q,
        limit=limit,
        offset=offset,
    )
    return ApartmentListOut(items=items, total=total, limit=limit, offset=offset)


# ВНИМАНИЕ: /stats объявлен ДО /{apartment_id}, иначе "stats" попадёт в параметр id.
@router.get("/stats", response_model=ApartmentStatsOut)
def get_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Мини-статистика по объектам агентства (счётчики по статусам)."""
    return apartment_service.get_stats(db, current_user.agency_id)


@router.get("/{apartment_id}", response_model=ApartmentOut)
def get_apartment(
    apartment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Карточка объекта."""
    return apartment_service.get_apartment(db, current_user.agency_id, apartment_id)


@router.get("/{apartment_id}/share", response_model=ApartmentShareOut)
def share_apartment(
    apartment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """
    Карточка объекта для отправки клиентам.
    Без номера собственника и внутреннего комментария; вместо номера
    собственника — контактный номер агентства (главного администратора).
    """
    return apartment_service.build_share_card(
        db, current_user.agency_id, apartment_id
    )


@router.get("/{apartment_id}/events", response_model=List[ApartmentEventOut])
def list_events(
    apartment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """История действий по объекту (кто создал/менял/сменил статус)."""
    return apartment_service.list_events(db, current_user.agency_id, apartment_id)


@router.patch("/{apartment_id}", response_model=ApartmentOut)
def update_apartment(
    apartment_id: int,
    body: ApartmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Отредактировать объект (только разрешённые поля)."""
    return apartment_service.update_apartment(
        db, current_user.agency_id, apartment_id, body, actor_id=current_user.id
    )


@router.post("/{apartment_id}/status", response_model=ApartmentOut)
def change_status(
    apartment_id: int,
    body: ApartmentStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Сменить статус объекта: active / deposit (задаток) / sold / archived."""
    return apartment_service.set_status(
        db, current_user.agency_id, apartment_id, body.status, actor_id=current_user.id
    )


@router.delete("/{apartment_id}", status_code=204)
def delete_apartment(
    apartment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Удалить объект безвозвратно (любой сотрудник агентства)."""
    apartment_service.delete_apartment(db, current_user.agency_id, apartment_id)
