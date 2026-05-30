"""
Эндпоинты объектов недвижимости.

Создание/редактирование/архив/восстановление/продан — любой сотрудник
агентства (агент или админ). Удаление — только администратор агентства
(по умолчанию из матрицы прав ТЗ, раздел 5).

Все операции изолированы по агентству: agency_id берётся из текущего
пользователя (из его пропуска), а не из параметров запроса.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import require_agency_admin, require_agency_member
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.apartment import (
    ApartmentCreate,
    ApartmentListOut,
    ApartmentOut,
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
    """Создать объект. ID (display_id) генерируется автоматически по агенту."""
    return apartment_service.create_apartment(
        db, current_user.agency_id, created_by=current_user.id, payload=body
    )


@router.get("", response_model=ApartmentListOut)
def search_apartments(
    status: Optional[str] = Query(
        "active",
        description="Статус: active / archived / sold. Передайте 'all' для всех статусов.",
    ),
    districts: Optional[List[str]] = Query(None, description="Районы (можно несколько)."),
    types: Optional[List[str]] = Query(None, description="Типы (можно несколько)."),
    rooms: Optional[List[int]] = Query(None, description="Кол-во комнат (можно несколько)."),
    floor_min: Optional[int] = Query(None, description="Этаж от."),
    floor_max: Optional[int] = Query(None, description="Этаж до."),
    price_min: Optional[float] = Query(None, description="Цена от."),
    price_max: Optional[float] = Query(None, description="Цена до."),
    agent_id: Optional[int] = Query(None, description="Фильтр по агенту."),
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
        floor_min=floor_min,
        floor_max=floor_max,
        price_min=price_min,
        price_max=price_max,
        agent_id=agent_id,
        limit=limit,
        offset=offset,
    )
    return ApartmentListOut(items=items, total=total, limit=limit, offset=offset)


@router.get("/{apartment_id}", response_model=ApartmentOut)
def get_apartment(
    apartment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Карточка объекта."""
    return apartment_service.get_apartment(db, current_user.agency_id, apartment_id)


@router.patch("/{apartment_id}", response_model=ApartmentOut)
def update_apartment(
    apartment_id: int,
    body: ApartmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Отредактировать объект (только разрешённые поля)."""
    return apartment_service.update_apartment(
        db, current_user.agency_id, apartment_id, body
    )


@router.post("/{apartment_id}/archive", response_model=ApartmentOut)
def archive_apartment(
    apartment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Перевести объект в архив."""
    return apartment_service.archive_apartment(db, current_user.agency_id, apartment_id)


@router.post("/{apartment_id}/restore", response_model=ApartmentOut)
def restore_apartment(
    apartment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Вернуть объект из архива в активные."""
    return apartment_service.restore_apartment(db, current_user.agency_id, apartment_id)


@router.post("/{apartment_id}/sold", response_model=ApartmentOut)
def mark_sold(
    apartment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Пометить объект как проданный."""
    return apartment_service.mark_sold(db, current_user.agency_id, apartment_id)


@router.delete("/{apartment_id}", status_code=204)
def delete_apartment(
    apartment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_admin),
):
    """Удалить объект безвозвратно (только администратор агентства)."""
    apartment_service.delete_apartment(db, current_user.agency_id, apartment_id)
