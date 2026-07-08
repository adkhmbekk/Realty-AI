"""
Зависимости FastAPI — переиспользуемые проверки для эндпоинтов.

- get_current_user — достаёт пользователя из пропуска (JWT) и проверяет,
  что он существует и активен.
- require_superadmin — пускает дальше только суперадмина.
"""
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core import security
from app.core.errors import AppError
from app.db.models.user import User
from app.db.session import get_db
from app.repositories import agency_membership_repo, agency_repo, user_repo

# auto_error=False — сами решаем, как реагировать на отсутствие токена.
_bearer = HTTPBearer(auto_error=False)


@dataclass
class ActingUser:
    """
    «Эффективный» пользователь: владелец платформы (суперадмин), работающий
    ВНУТРИ своего личного агентства (acting-контекст). Для всех агентских
    эндпоинтов он выглядит как главный админ (agency_admin, is_owner=True).

    ВАЖНО: это НЕ ORM-объект. Его НЕЛЬЗЯ добавлять/коммитить/refresh'ить в
    сессию БД — иначе можно затереть настоящую строку суперадмина (у которой
    agency_id всегда NULL). Только чтение полей (.id, .agency_id, .role и т.п.).
    """
    id: int
    telegram_id: int
    username: Optional[str]
    full_name: Optional[str]
    agency_id: int
    role: str = "agency_admin"
    is_owner: bool = True
    is_active: bool = True
    # Признаки acting-режима (уезжают в профиль и в UI).
    acting: bool = True
    real_role: str = "superadmin"
    acting_as_agency_id: Optional[int] = None
    acting_as_agency_name: Optional[str] = None


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise AppError("auth_required", status.HTTP_401_UNAUTHORIZED)

    payload = security.decode_access_token(credentials.credentials)
    if payload is None:
        raise AppError("auth_invalid_token", status.HTTP_401_UNAUTHORIZED)

    user_id = payload.get("user_id")
    user = user_repo.get_by_id(db, user_id) if user_id is not None else None
    if user is None or not user.is_active:
        raise AppError("user_not_found_or_inactive", status.HTTP_401_UNAUTHORIZED)

    # Мгновенный отзыв: пропуск с устаревшей «версией сессии» больше не действует
    # (сотрудника отключили/исключили или нажали «выйти со всех устройств»).
    if (payload.get("epoch") or 0) != (getattr(user, "session_epoch", 0) or 0):
        raise AppError("session_revoked", status.HTTP_401_UNAUTHORIZED)

    # Acting-контекст: человек «вошёл» в ДРУГОЕ своё агентство (не домашнее).
    # Права перепроверяем из БД на КАЖДОМ запросе — claim'у из токена не доверяем.
    act_as = payload.get("act_as_agency_id")
    if act_as is not None and act_as != user.agency_id:
        # Путь А: суперадмин — в своё личное/общее агентство платформы.
        if user.role == "superadmin":
            agency = agency_repo.get_by_id(db, act_as)
            if agency is not None and (
                agency.owner_telegram_id == user.telegram_id
                or getattr(agency, "is_shared", False)
            ):
                return ActingUser(
                    id=user.id,
                    telegram_id=user.telegram_id,
                    username=user.username,
                    full_name=user.full_name,
                    agency_id=agency.id,
                    role="agency_admin",
                    is_owner=True,
                    acting_as_agency_id=agency.id,
                    acting_as_agency_name=agency.name,
                    real_role="superadmin",
                )
        # Путь Б: обычный участник — в другое своё агентство (по членству).
        # Роль и «владелец» берутся из членства именно в ТОМ агентстве.
        else:
            m = agency_membership_repo.get(db, user.id, act_as)
            if m is not None and m.is_active:
                agency = agency_repo.get_by_id(db, act_as)
                if agency is not None:
                    return ActingUser(
                        id=user.id,
                        telegram_id=user.telegram_id,
                        username=user.username,
                        full_name=user.full_name,
                        agency_id=agency.id,
                        role=m.role,
                        is_owner=m.is_owner,
                        acting_as_agency_id=agency.id,
                        acting_as_agency_name=agency.name,
                        real_role=user.role,
                    )
    return user


def require_superadmin(user: User = Depends(get_current_user)) -> User:
    if user.role != "superadmin":
        raise AppError("forbidden_superadmin_only", status.HTTP_403_FORBIDDEN)
    return user


def _ensure_subscription_active(db: Session, user: User) -> None:
    """
    Блокировка по подписке (единая точка). ПОДПИСКА ОТКЛЮЧЕНА (тарифы, 2026-07):
    доступ по подписке никогда не блокируется, поэтому проверка ничего не делает.

    Раньше здесь на КАЖДЫЙ авторизованный запрос шёл лишний SELECT агентства
    (PERF1) — на горячем пути это лишний round-trip к БД без всякого эффекта.
    Убираем его до возврата платных тарифов. Когда гейтинг вернётся —
    восстановить прежнюю логику (agency_repo.get_by_id + проверка срока) здесь.
    """
    return


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
        raise AppError("forbidden_member_only", status.HTTP_403_FORBIDDEN)
    _ensure_subscription_active(db, user)
    return user


def require_agency_admin(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> User:
    """Пропускает только администратора агентства с активной подпиской."""
    if user.role != "agency_admin" or user.agency_id is None:
        raise AppError("forbidden_admin_only", status.HTTP_403_FORBIDDEN)
    _ensure_subscription_active(db, user)
    return user


def require_agency_owner(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> User:
    """
    Пропускает только ГЛАВНОГО администратора агентства (is_owner).

    Главный админ — единственный, кто управляет приглашениями (добавлением
    людей в команду) и повышением сотрудников до администратора. Обычный
    администратор такими правами не обладает.
    """
    if user.role != "agency_admin" or user.agency_id is None or not user.is_owner:
        raise AppError("forbidden_owner_only", status.HTTP_403_FORBIDDEN)
    _ensure_subscription_active(db, user)
    return user
