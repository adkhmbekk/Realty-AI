"""
Эндпоинты справочников агентства (районы, типы и т.д.).

Просмотр — любому сотруднику агентства (нужно для форм и фильтров).
Изменение — только администратору агентства.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import require_agency_admin, require_agency_member
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.dictionary import DictionaryCreate, DictionaryOut, DictionaryUpdate
from app.services import dictionary_service

router = APIRouter(prefix="/dictionaries", tags=["dictionaries"])


@router.get("", response_model=List[DictionaryOut])
def list_dictionaries(
    category: Optional[str] = Query(
        None, description="Фильтр по категории, например 'district' или 'property_type'."
    ),
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Список значений справочников своего агентства (опционально по категории)."""
    return dictionary_service.list_dictionaries(
        db, current_user.agency_id, category=category, include_inactive=include_inactive
    )


@router.post("", response_model=DictionaryOut, status_code=201)
def create_dictionary(
    body: DictionaryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_admin),
):
    """Добавить значение в справочник."""
    return dictionary_service.create_dictionary(db, current_user.agency_id, body)


@router.patch("/{dict_id}", response_model=DictionaryOut)
def update_dictionary(
    dict_id: int,
    body: DictionaryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_admin),
):
    """Изменить значение справочника."""
    return dictionary_service.update_dictionary(db, current_user.agency_id, dict_id, body)


@router.delete("/{dict_id}", status_code=204)
def delete_dictionary(
    dict_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_admin),
):
    """Удалить значение справочника."""
    dictionary_service.delete_dictionary(db, current_user.agency_id, dict_id)
