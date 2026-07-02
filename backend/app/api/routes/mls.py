"""
Витрина общей базы (MLS) для владельца платформы (только суперадмин).

Показывает все объекты, которыми агентства поделились в общей базе (shared_mls),
по всем агентствам, с фильтрами. Контакты собственника скрыты (как видят
агентства друг друга). Только чтение — ничего не меняет и не удаляет.
"""
from typing import Optional

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
    status: str = Query(default="active"),
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Общая база (MLS) для агентства: все объекты, которыми поделились агентства.
    Телефон собственника виден ТОЛЬКО у своих объектов (кто добавил — тот и видит)."""
    return mls_service.list_pool_for_member(
        db,
        current_user.agency_id,
        status=status,
        agency_id=agency_id,
        districts=[district] if district else None,
        deal_type=deal_type,
        q=q,
        limit=limit,
        offset=offset,
    )


@router.get("/stats", response_model=ApartmentStatsOut)
def mls_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Счётчики общей базы (MLS) по статусам — для главного экрана агентства."""
    return mls_service.pool_stats(db)
