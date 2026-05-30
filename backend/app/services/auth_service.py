"""
Бизнес-логика входа.

Принимает initData от Telegram, проверяет его, находит пользователя в нашей
базе, обновляет его данные и выдаёт пропуск (JWT).

Важно: незнакомый пользователь (не привязанный к агентству) НЕ получает доступ.
Привязка происходит только через приглашение (будет на следующем этапе) или
если это суперадмин платформы.
"""
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.core import security
from app.repositories import agency_repo, user_repo


def login_with_init_data(db: Session, init_data: str) -> dict:
    # 1. Без токена бота проверить подлинность входа невозможно.
    if not settings.bot_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Вход через Telegram не настроен (не задан токен бота).",
        )

    # 2. Проверяем подпись Telegram.
    try:
        data = security.validate_init_data(
            init_data, settings.bot_token, settings.init_data_max_age_seconds
        )
    except security.InitDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc

    tg_user = data["user"]
    telegram_id = int(tg_user["id"])

    # 3. Ищем пользователя в нашей базе.
    user = user_repo.get_by_telegram_id(db, telegram_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Вы не привязаны ни к одному агентству. Обратитесь к администратору.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ваш доступ деактивирован. Обратитесь к администратору.",
        )

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

    # 5. Проверяем подписку агентства.
    # У суперадмина (владельца платформы) подписки нет — оставляем None,
    # чтобы фронтенд не показывал ему строку про подписку.
    subscription_active = None
    if user.role != "superadmin":
        agency = agency_repo.get_by_id(db, user.agency_id) if user.agency_id else None
        subscription_active = agency is not None and agency.status in ("trial", "active")

    db.commit()
    db.refresh(user)

    # 6. Выдаём пропуск.
    token = security.create_access_token(
        {
            "user_id": user.id,
            "telegram_id": user.telegram_id,
            "agency_id": user.agency_id,
            "role": user.role,
        }
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "subscription_active": subscription_active,
        "user": user,
    }
