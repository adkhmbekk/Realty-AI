"""
Эндпоинты витрины «юзеры прошки» для владельца платформы (Фаза 5, 2026-07).

Роуты тонкие: разбор запроса → вызов platform_service → schema-ответ. Доступ —
только суперадмину (require_superadmin). Приватность: отдаются объекты, но НЕ
клиентская база (см. platform_service).
"""
from typing import Optional

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.dependencies import require_superadmin
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.platform import (
    ArchiveUserRequest,
    PlatformUserDetail,
    PlatformUserList,
    RestoreUserRequest,
)
from app.services import platform_service

router = APIRouter(prefix="/superadmin", tags=["superadmin"])


@router.get("/users", response_model=PlatformUserList)
def platform_users(
    q: Optional[str] = None,
    archived: bool = False,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Список юзеров прошки (кроме суперадминов). archived=true — вкладка «Архив»."""
    return platform_service.list_platform_users(
        db, q=q, archived=archived, limit=limit, offset=offset
    )


@router.get("/users/{user_id}", response_model=PlatformUserDetail)
def platform_user_detail(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Карточка юзера: агентства/роли + ЕГО объекты (без клиентской базы)."""
    return platform_service.get_platform_user(db, user_id)


@router.post("/users/{user_id}/archive", response_model=PlatformUserDetail)
def archive_user(
    user_id: int,
    body: ArchiveUserRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """«Удалить» юзера → в архив. freeze_agencies — заодно заморозить его агентства."""
    return platform_service.archive_user(
        db, user_id, freeze_agencies=body.freeze_agencies
    )


@router.post("/users/{user_id}/restore", status_code=status.HTTP_204_NO_CONTENT)
def restore_user(
    user_id: int,
    body: RestoreUserRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Вернуть данные архивного юзера: передать его владельческие агентства
    выбранному активному юзеру (target_user_id). Архивная запись удаляется."""
    platform_service.restore_user_data(db, user_id, body.target_user_id)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def purge_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Удалить архивного юзера НАВСЕГДА (вместе с его владельческими агентствами)."""
    platform_service.purge_user(db, user_id, actor=current_user)
