"""
Витрина общей базы (MLS) для владельца платформы (только суперадмин).

Показывает все объекты, которыми агентства поделились в общей базе (shared_mls),
по всем агентствам, с фильтрами. Контакты собственника скрыты (как видят
агентства друг друга). Только чтение — ничего не меняет и не удаляет.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import require_agency_member, require_superadmin
from app.core.ratelimit import rate_limit
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.apartment import ApartmentStatsOut
from app.schemas.mls import MlsPoolOut
from app.services import mls_service

router = APIRouter(prefix="/mls", tags=["mls"])


@router.get(
    "/pool",
    response_model=MlsPoolOut,
    dependencies=[Depends(rate_limit(60, 60, "mls_pool"))],
)
def mls_pool(
    agency_id: Optional[int] = Query(default=None),
    deal_type: Optional[str] = Query(default=None),
    district: Optional[str] = Query(default=None),
    status: str = Query(default="active"),
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Все объекты общей базы (MLS) по всем агентствам. Контакты скрыты."""
    return mls_service.list_pool(
        db,
        status=status,
        agency_id=agency_id,
        districts=[district] if district else None,
        deal_type=deal_type,
        q=q,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/browse",
    response_model=MlsPoolOut,
    dependencies=[Depends(rate_limit(60, 60, "mls_browse"))],
)
def mls_browse(
    agency_id: Optional[int] = Query(default=None),
    deal_type: Optional[str] = Query(default=None),
    district: Optional[str] = Query(default=None),
    districts: Optional[List[str]] = Query(default=None),
    types: Optional[List[str]] = Query(default=None),
    rooms_min: Optional[int] = Query(default=None),
    rooms_max: Optional[int] = Query(default=None),
    price_min: Optional[float] = Query(default=None),
    price_max: Optional[float] = Query(default=None),
    currency: Optional[str] = Query(default=None),
    status: str = Query(default="active"),
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Общая база (MLS) для агентства: все объекты, которыми поделились агентства,
    с фильтрами (район/тип/комнаты/цена) — используется и на экране «Общая база», и в
    поиске (секция «В общей базе»). Телефон собственника виден ТОЛЬКО у своих объектов."""
    # Районы: поддерживаем и одиночный district (совместимость), и список districts.
    dl = list(districts) if districts else []
    if district:
        dl.append(district)
    return mls_service.list_pool_for_member(
        db,
        current_user.agency_id,
        status=status,
        agency_id=agency_id,
        districts=dl or None,
        types=types,
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


@router.get("/objects/{object_id}/photos")
def mls_object_photos(
    object_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Фото объекта из общей базы (MLS) — для просмотра read-only карточки любым
    агентством. Телефон/контакты сюда не входят (только изображения)."""
    return mls_service.object_photos(db, object_id)


@router.post(
    "/objects/{object_id}/take",
    dependencies=[Depends(rate_limit(30, 60, "mls_take"))],
)
def mls_take_for_client(
    object_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """«Беру для клиента»: уведомить агентство-владельца объекта из общей базы, что
    его объект берут для клиента — с контактом берущего агентства (связь риелторов)."""
    return mls_service.take_for_client(db, current_user.agency_id, current_user, object_id)


@router.get("/stats", response_model=ApartmentStatsOut)
def mls_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Счётчики общей базы (MLS) по статусам — для главного экрана агентства."""
    return mls_service.pool_stats(db)
