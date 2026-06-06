"""
Доступ к данным фотографий объектов (таблица apartment_photos).
Все запросы фильтруются по agency_id (изоляция агентств).
"""
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.apartment_photo import ApartmentPhoto


def list_for(db: Session, agency_id: int, apartment_id: int) -> List[ApartmentPhoto]:
    return list(
        db.execute(
            select(ApartmentPhoto)
            .where(
                ApartmentPhoto.agency_id == agency_id,
                ApartmentPhoto.apartment_id == apartment_id,
            )
            .order_by(ApartmentPhoto.sort_order, ApartmentPhoto.id)
        )
        .scalars()
        .all()
    )


def count_for(db: Session, agency_id: int, apartment_id: int) -> int:
    return db.execute(
        select(func.count())
        .select_from(ApartmentPhoto)
        .where(
            ApartmentPhoto.agency_id == agency_id,
            ApartmentPhoto.apartment_id == apartment_id,
        )
    ).scalar_one()


def max_sort_order(db: Session, agency_id: int, apartment_id: int) -> int:
    val = db.execute(
        select(func.max(ApartmentPhoto.sort_order)).where(
            ApartmentPhoto.agency_id == agency_id,
            ApartmentPhoto.apartment_id == apartment_id,
        )
    ).scalar_one()
    return int(val) if val is not None else -1


def get(db: Session, agency_id: int, apartment_id: int, photo_id: int) -> Optional[ApartmentPhoto]:
    return db.execute(
        select(ApartmentPhoto).where(
            ApartmentPhoto.id == photo_id,
            ApartmentPhoto.agency_id == agency_id,
            ApartmentPhoto.apartment_id == apartment_id,
        )
    ).scalar_one_or_none()


def get_by_key(db: Session, storage_key: str) -> Optional[ApartmentPhoto]:
    return db.execute(
        select(ApartmentPhoto).where(ApartmentPhoto.storage_key == storage_key)
    ).scalar_one_or_none()


def create(
    db: Session,
    agency_id: int,
    apartment_id: int,
    storage_key: str,
    content_type: str,
    sort_order: int,
) -> ApartmentPhoto:
    photo = ApartmentPhoto(
        agency_id=agency_id,
        apartment_id=apartment_id,
        storage_key=storage_key,
        content_type=content_type,
        sort_order=sort_order,
    )
    db.add(photo)
    db.flush()
    return photo


def delete(db: Session, photo: ApartmentPhoto) -> None:
    db.delete(photo)


def list_keys_for_apartment(db: Session, apartment_id: int) -> List[str]:
    return list(
        db.execute(
            select(ApartmentPhoto.storage_key).where(ApartmentPhoto.apartment_id == apartment_id)
        )
        .scalars()
        .all()
    )


def list_keys_for_agency(db: Session, agency_id: int) -> List[str]:
    """Ключи файлов всех фото агентства (для удаления файлов с диска)."""
    return list(
        db.execute(
            select(ApartmentPhoto.storage_key).where(ApartmentPhoto.agency_id == agency_id)
        )
        .scalars()
        .all()
    )


def all_storage_keys(db: Session) -> List[str]:
    """Все ключи файлов фото (по всем агентствам) — для обслуживания: поиск
    «осиротевших» файлов на диске, у которых нет строки в БД (см. M4)."""
    return list(db.execute(select(ApartmentPhoto.storage_key)).scalars().all())


def delete_for_agency(db: Session, agency_id: int) -> None:
    """Удалить все строки фото агентства (файлы удаляются отдельно)."""
    from sqlalchemy import delete as sa_delete

    db.execute(sa_delete(ApartmentPhoto).where(ApartmentPhoto.agency_id == agency_id))
