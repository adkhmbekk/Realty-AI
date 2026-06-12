"""
Бизнес-логика справочников агентства (районы, типы и т.д.).
Справочниками управляет администратор агентства.
"""
from typing import List, Optional

from fastapi import status
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models.dictionary import Dictionary
from app.repositories import dictionary_repo
from app.schemas.dictionary import DictionaryCreate, DictionaryUpdate


def list_dictionaries(
    db: Session,
    agency_id: int,
    category: Optional[str] = None,
    include_inactive: bool = False,
) -> List[Dictionary]:
    return dictionary_repo.get_all(
        db, agency_id, category=category, include_inactive=include_inactive
    )


def create_dictionary(
    db: Session, agency_id: int, payload: DictionaryCreate
) -> Dictionary:
    # Запрещаем дубликаты значения в пределах категории агентства.
    existing = dictionary_repo.get_one(db, agency_id, payload.category, payload.value)
    if existing is not None:
        raise AppError(
            "dict_value_exists",
            status.HTTP_409_CONFLICT,
            value=payload.value,
            category=payload.category,
        )
    item = dictionary_repo.create(
        db, agency_id, category=payload.category, value=payload.value,
        sort_order=payload.sort_order,
    )
    db.commit()
    db.refresh(item)
    return item


def update_dictionary(
    db: Session, agency_id: int, dict_id: int, payload: DictionaryUpdate
) -> Dictionary:
    item = dictionary_repo.get_by_id(db, agency_id, dict_id)
    if item is None:
        raise AppError("dict_value_not_found", status.HTTP_404_NOT_FOUND)
    if payload.value is not None and payload.value != item.value:
        # Как и при создании: два одинаковых значения в категории не допускаем,
        # иначе переименованием можно получить дубликат (два «Юнусабада»).
        existing = dictionary_repo.get_one(db, agency_id, item.category, payload.value)
        if existing is not None and existing.id != item.id:
            raise AppError(
                "dict_value_exists",
                status.HTTP_409_CONFLICT,
                value=payload.value,
                category=item.category,
            )
        item.value = payload.value
    if payload.sort_order is not None:
        item.sort_order = payload.sort_order
    if payload.is_active is not None:
        item.is_active = payload.is_active
    db.commit()
    db.refresh(item)
    return item


def delete_dictionary(db: Session, agency_id: int, dict_id: int) -> None:
    item = dictionary_repo.get_by_id(db, agency_id, dict_id)
    if item is None:
        raise AppError("dict_value_not_found", status.HTTP_404_NOT_FOUND)
    dictionary_repo.delete(db, item)
    db.commit()
