"""
Эндпоинты витрины «юзеры прошки» для владельца платформы (Фаза 5, 2026-07).

Роуты тонкие: разбор запроса → вызов platform_service → schema-ответ. Доступ —
только суперадмину (require_superadmin). Приватность: отдаются объекты, но НЕ
клиентская база (см. platform_service).
"""
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import require_superadmin
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.platform import PlatformUserDetail, PlatformUserList
from app.services import platform_service

router = APIRouter(prefix="/superadmin", tags=["superadmin"])


@router.get("/users", response_model=PlatformUserList)
def platform_users(
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Список юзеров прошки (кроме суперадминов) — главный экран владельца платформы."""
    return platform_service.list_platform_users(db, q=q, limit=limit, offset=offset)


@router.get("/users/{user_id}", response_model=PlatformUserDetail)
def platform_user_detail(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Карточка юзера: агентства/роли + ЕГО объекты (без клиентской базы)."""
    return platform_service.get_platform_user(db, user_id)
