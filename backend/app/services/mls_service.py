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

from sqlalchemy.orm import Session

from app.repositories import agency_repo, apartment_repo
from app.schemas.apartment import ApartmentOut
from app.schemas.mls import MlsPoolItemOut, MlsPoolOut


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

    # Названия агентств-владельцев — одним проходом по уникальным id (как в
    # list_matches): показываем бренд проекта, если он задан, иначе имя.
    names: dict = {}
    for a in items:
        if a.agency_id not in names:
            ag = agency_repo.get_by_id(db, a.agency_id)
            names[a.agency_id] = (ag.project_name or ag.name) if ag is not None else None

    out_items: List[MlsPoolItemOut] = [
        MlsPoolItemOut(
            agency_id=a.agency_id,
            agency_name=names.get(a.agency_id),
            apartment=_blank_contacts(ApartmentOut.model_validate(a)),
        )
        for a in items
    ]
    return MlsPoolOut(items=out_items, total=total, limit=limit, offset=offset)
