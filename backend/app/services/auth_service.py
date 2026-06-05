"""
Бизнес-логика входа.

Принимает initData от Telegram, проверяет его, находит пользователя в нашей
базе, обновляет его данные и выдаёт пропуск (JWT).

Важно: незнакомый пользователь (не привязанный к агентству) НЕ получает доступ.
Привязка происходит только через приглашение (будет на следующем этапе) или
если это суперадмин платформы.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import status
from sqlalchemy.orm import Session

from app.config import settings
from app.core import security
from app.core.errors import AppError
from app.core.subscription import agency_is_active
from app.repositories import agency_repo, audit_repo, user_repo


def login_with_init_data(db: Session, init_data: str, ip: Optional[str] = None) -> dict:
    # 1. Без токена бота проверить подлинность входа невозможно.
    if not settings.bot_token:
        raise AppError(
            "telegram_login_not_configured", status.HTTP_503_SERVICE_UNAVAILABLE
        )

    # 2. Проверяем подпись Telegram.
    try:
        data = security.validate_init_data(
            init_data, settings.bot_token, settings.init_data_max_age_seconds
        )
    except security.InitDataError as exc:
        raise AppError(exc.key, status.HTTP_401_UNAUTHORIZED) from exc

    tg_user = data["user"]
    telegram_id = int(tg_user["id"])

    # 3. Ищем пользователя в нашей базе.
    user = user_repo.get_by_telegram_id(db, telegram_id)
    if user is None:
        raise AppError("not_in_agency", status.HTTP_403_FORBIDDEN)
    if not user.is_active:
        raise AppError("access_deactivated", status.HTTP_403_FORBIDDEN)

    # 4. Обновляем актуальные данные из Telegram и время входа.
    username = tg_user.get("username")
    if username:
        user.username = username
    full_name = " ".join(
        part for part in [tg_user.get("first_name"), tg_user.get("last_name")] if part
    )
    if full_name:
        user.full_name = full_name
    user.last_login_at = datetime.now(timezone.utc)

    # 5. Журнал аудита: фиксируем вход (для сотрудников агентства).
    if user.agency_id is not None:
        audit_repo.add(
            db,
            action="login",
            agency_id=user.agency_id,
            actor_user_id=user.id,
            actor_telegram_id=user.telegram_id,
            actor_name=user.full_name or (("@" + user.username) if user.username else None),
            ip=ip,
        )

    db.commit()
    db.refresh(user)

    # 6. Выдаём пропуск (вместе со статусом подписки агентства).
    return build_auth_response(db, user)


def refresh_session(db: Session, refresh_token: str) -> dict:
    """
    Обновить сессию по refresh-пропуску: выдать новый access (+ refresh) без
    повторной проверки initData. Так длинная сессия не упирается в «тихий
    тупик» после истечения короткого пропуска.
    """
    payload = security.decode_refresh_token(refresh_token)
    if payload is None:
        raise AppError("auth_invalid_token", status.HTTP_401_UNAUTHORIZED)
    user = user_repo.get_by_id(db, payload.get("user_id"))
    if user is None or not user.is_active:
        raise AppError("user_not_found_or_inactive", status.HTTP_401_UNAUTHORIZED)
    return build_auth_response(db, user)


def build_auth_response(db: Session, user) -> dict:
    """
    Собрать ответ авторизации: пропуск (JWT), refresh-пропуск, статус подписки и
    профиль. Используется при входе, вступлении по приглашению и обновлении сессии.
    """
    # У суперадмина (владельца платформы) подписки нет — оставляем None,
    # чтобы фронтенд не показывал ему строку про подписку.
    subscription_active = None
    if user.role != "superadmin":
        agency = agency_repo.get_by_id(db, user.agency_id) if user.agency_id else None
        subscription_active = agency_is_active(agency)

    token = security.create_access_token(
        {
            "user_id": user.id,
            "telegram_id": user.telegram_id,
            "agency_id": user.agency_id,
            "role": user.role,
        }
    )
    refresh_token = security.create_refresh_token({"user_id": user.id})

    return {
        "access_token": token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "subscription_active": subscription_active,
        "user": user,
    }
