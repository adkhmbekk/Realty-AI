"""
Зависимости FastAPI — переиспользуемые проверки для эндпоинтов.

- get_current_user — достаёт пользователя из пропуска (JWT) и проверяет,
  что он существует и активен.
- require_superadmin — пускает дальше только суперадмина.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core import security
from app.core.subscription import agency_is_active
from app.db.models.user import User
from app.db.session import get_db
from app.repositories import agency_repo, user_repo

# auto_error=False — сами решаем, как реагировать на отсутствие токена.
_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация.",
        )

    payload = security.decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный или истёкший пропуск. Войдите заново.",
        )

    user_id = payload.get("user_id")
    user = user_repo.get_by_id(db, user_id) if user_id is not None else None
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден или деактивирован.",
        )
    return user


def require_superadmin(user: User = Depends(get_current_user)) -> User:
    if user.role != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ только для суперадмина.",
        )
    return user


def _ensure_subscription_active(db: Session, user: User) -> None:
    """
    Жёсткая блокировка по подписке: если агентство заморожено или срок истёк —
    закрываем доступ к рабочим эндпоинтам (данные при этом не трогаем).
    """
    agency = agency_repo.get_by_id(db, user.agency_id)
    if not agency_is_active(agency):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ к агентству приостановлен: подписка неактивна. "
            "Обратитесь к владельцу платформы.",
        )


def require_agency_member(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> User:
    """
    Пропускает только сотрудника агентства (админа или агента), привязанного
    к какому-то агентству. Суперадмин (без агентства) сюда не проходит — у него
    нет объектов недвижимости (см. матрицу прав в ТЗ, раздел 5).

    Дополнительно проверяет, что подписка агентства в силе: замороженное или
    просроченное агентство блокируется (доступ приостановлен, данные сохранены).
    """
    if user.role not in ("agency_admin", "agent") or user.agency_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ только для сотрудников агентства.",
        )
    _ensure_subscription_active(db, user)
    return user


def require_agency_admin(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> User:
    """Пропускает только администратора агентства с активной подпиской."""
    if user.role != "agency_admin" or user.agency_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ только для администратора агентства.",
        )
    _ensure_subscription_active(db, user)
    return user
