"""
Витрина общей базы (MLS) для владельца платформы.

Владелец платформы видит ВСЕ объекты, которые агентства пометили «поделиться в
общей базе» (shared_mls=True), по всем агентствам, с фильтрами. Контакты
собственника (телефон, точный адрес, внутренние пометки, имя автора) СКРЫТЫ —
ровно так же, как агентства видят чужие объекты при подборе (см. фикс аудита H1
в client_service.list_matches). Видно только, какому агентству принадлежит
объект (это и есть цель: контроль наполнения общей базы). Только чтение.
"""
from typing import List, Optional, Sequence

from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.repositories import agency_repo, apartment_repo
from app.schemas.apartment import ApartmentOut, ApartmentStatsOut
from app.schemas.mls import MlsPoolItemOut, MlsPoolOut
from app.services import photo_service


def _blank_contacts(apt_out: ApartmentOut) -> ApartmentOut:
    """Скрыть всё, что ведёт напрямую к собственнику/агенту — как при подборе MLS."""
    apt_out.owner_phone = None
    apt_out.address = None
    apt_out.comment = None
    apt_out.source = None
    apt_out.source_link = None
    apt_out.created_by = None
    apt_out.created_by_name = None
    return apt_out


def _agency_info(db: Session, items) -> dict:
    """Для каждого уникального агентства из выборки: (отображаемое имя, контактный
    телефон). Имя — бренд проекта, иначе name; телефон — agency.contact_phone: по
    нему другое агентство связывается с риелтором, выложившим объект в общую базу."""
    info: dict = {}
    for a in items:
        if a.agency_id not in info:
            ag = agency_repo.get_by_id(db, a.agency_id)
            info[a.agency_id] = (
                (ag.project_name or ag.name) if ag is not None else None,
                ag.contact_phone if ag is not None else None,
            )
    return info


def list_pool(
    db: Session,
    *,
    status: Optional[str] = "active",
    agency_id: Optional[int] = None,
    districts: Optional[Sequence[str]] = None,
    deal_type: Optional[str] = None,
    rooms_min: Optional[int] = None,
    rooms_max: Optional[int] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    currency: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> MlsPoolOut:
    items, total = apartment_repo.list_mls_pool(
        db,
        status=status,
        agency_id=agency_id,
        districts=districts,
        deal_type=deal_type,
        rooms_min=rooms_min,
        rooms_max=rooms_max,
        price_min=price_min,
        price_max=price_max,
        currency=currency,
        q=q,
        limit=limit,
        offset=offset,
    )

    # Имя + контактный телефон агентства-владельца — одним проходом по уникальным
    # id: показываем бренд проекта (иначе имя) и agency.contact_phone для связи.
    info = _agency_info(db, items)

    out_items: List[MlsPoolItemOut] = [
        MlsPoolItemOut(
            agency_id=a.agency_id,
            agency_name=info.get(a.agency_id, (None, None))[0],
            agency_phone=info.get(a.agency_id, (None, None))[1],
            apartment=_blank_contacts(ApartmentOut.model_validate(a)),
        )
        for a in items
    ]
    return MlsPoolOut(items=out_items, total=total, limit=limit, offset=offset)


def list_pool_for_member(
    db: Session,
    viewer_agency_id: int,
    *,
    status: Optional[str] = "active",
    agency_id: Optional[int] = None,
    districts: Optional[Sequence[str]] = None,
    deal_type: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> MlsPoolOut:
    """
    Общая база (MLS) глазами обычного агентства: видны ВСЕ shared-объекты всех
    агентств платформы. Телефон/адрес/автора собственника показываем ТОЛЬКО у
    СВОИХ объектов (agency_id == viewer_agency_id). Чужие контакты скрыты: номер
    собственника видит лишь то агентство, которое само добавило объект.
    """
    items, total = apartment_repo.list_mls_pool(
        db,
        status=status,
        agency_id=agency_id,
        districts=districts,
        deal_type=deal_type,
        q=q,
        limit=limit,
        offset=offset,
    )
    info = _agency_info(db, items)

    out_items: List[MlsPoolItemOut] = []
    for a in items:
        apt_out = ApartmentOut.model_validate(a)
        if a.agency_id != viewer_agency_id:
            apt_out = _blank_contacts(apt_out)
        out_items.append(
            MlsPoolItemOut(
                agency_id=a.agency_id,
                agency_name=info.get(a.agency_id, (None, None))[0],
                agency_phone=info.get(a.agency_id, (None, None))[1],
                apartment=apt_out,
            )
        )
    return MlsPoolOut(items=out_items, total=total, limit=limit, offset=offset)


def object_photos(db: Session, object_id: int) -> list:
    """Фото объекта из общей базы (MLS) — для read-only карточки у ЛЮБОГО
    агентства. Сначала убеждаемся, что объект действительно в общей базе
    (shared_mls), затем отдаём его фото (по агентству-владельцу объекта)."""
    apt = apartment_repo.get_shared_mls(db, object_id)
    if apt is None:
        raise AppError("apartment_not_found", http_status.HTTP_404_NOT_FOUND)
    return photo_service.list_photos(db, apt.agency_id, object_id)


def pool_stats(db: Session) -> ApartmentStatsOut:
    """Счётчики общей базы (MLS) по статусам — для главного экрана агентства."""
    counts = apartment_repo.mls_pool_status_counts(db)
    return ApartmentStatsOut(
        active=counts.get("active", 0),
        deposit=counts.get("deposit", 0),
        sold=counts.get("sold", 0),
        rented=counts.get("rented", 0),
        total=sum(counts.values()),
    )
