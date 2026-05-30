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
from app.db.models.user import User
from app.db.session import get_db
from app.repositories import user_repo

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
