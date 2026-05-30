"""
Бизнес-логика приглашений сотрудников (Этап 2).

Сценарий:
  1) Админ агентства создаёт приглашение с ролью и сроком → получает код и
     (если задано имя бота) готовую ссылку-диплинк для Telegram.
  2) Новый сотрудник открывает Mini App по ссылке (или вводит код вручную) и
     присылает свой initData + код. Мы проверяем подпись Telegram и код, после
     чего создаём/привязываем пользователя к агентству с нужной ролью и выдаём
     ему пропуск — точно такой же, как при обычном входе.

Приглашение одноразовое: после успешного вступления оно помечается
использованным (used_at) и больше не действует.
"""
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.core import security
from app.repositories import invite_repo, user_repo
from app.schemas.invite import InviteCreate, InviteOut
from app.services import auth_service

# Сколько байт случайности в коде (token_urlsafe даёт ~1.3 символа на байт).
_CODE_BYTES = 9


def _generate_unique_code(db: Session) -> str:
    """Сгенерировать случайный код, которого ещё нет в базе."""
    for _ in range(10):
        code = secrets.token_urlsafe(_CODE_BYTES)
        if invite_repo.get_by_code(db, code) is None:
            return code
    # Практически недостижимо, но не зацикливаемся молча.
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Не удалось сгенерировать код приглашения, попробуйте ещё раз.",
    )


def _status_of(invite) -> str:
    if invite.used_at is not None:
        return "used"
    if invite.expires_at <= datetime.now(timezone.utc):
        return "expired"
    return "active"


def _join_link(code: str) -> Optional[str]:
    # Диплинк Telegram Mini App: открывает бота и передаёт код в start_param.
    if settings.bot_username:
        return f"https://t.me/{settings.bot_username}?startapp={code}"
    return None


def _to_out(invite) -> InviteOut:
    return InviteOut(
        id=invite.id,
        code=invite.code,
        role=invite.role,
        status=_status_of(invite),
        join_link=_join_link(invite.code),
        expires_at=invite.expires_at,
        used_at=invite.used_at,
        used_by_telegram_id=invite.used_by_telegram_id,
        created_at=invite.created_at,
    )


def create_invite(
    db: Session, agency_id: int, created_by: int, payload: InviteCreate
) -> InviteOut:
    code = _generate_unique_code(db)
    expires_at = datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days)
    invite = invite_repo.create(
        db,
        agency_id=agency_id,
        code=code,
        role=payload.role,
        created_by=created_by,
        expires_at=expires_at,
    )
    db.commit()
    db.refresh(invite)
    return _to_out(invite)


def list_invites(db: Session, agency_id: int) -> List[InviteOut]:
    return [_to_out(inv) for inv in invite_repo.get_all(db, agency_id)]


def revoke_invite(db: Session, agency_id: int, invite_id: int) -> None:
    invite = invite_repo.get_by_id(db, agency_id, invite_id)
    if invite is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Приглашение не найдено."
        )
    invite_repo.delete(db, invite)
    db.commit()


def redeem_invite(db: Session, init_data: str, code: str) -> dict:
    # 1. Без токена бота проверить подлинность входа невозможно.
    if not settings.bot_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Вход через Telegram не настроен (не задан токен бота).",
        )

    # 2. Проверяем подпись Telegram — это подтверждает личность сотрудника.
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

    # 3. Находим и проверяем приглашение.
    invite = invite_repo.get_by_code(db, code)
    if invite is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Приглашение не найдено."
        )
    if invite.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Это приглашение уже использовано.",
        )
    if invite.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Срок действия приглашения истёк.",
        )

    # 4. Создаём или привязываем пользователя к агентству приглашения.
    username = tg_user.get("username")
    full_name = " ".join(
        part for part in [tg_user.get("first_name"), tg_user.get("last_name")] if part
    ) or None

    user = user_repo.get_by_telegram_id(db, telegram_id)
    if user is not None:
        if user.role == "superadmin":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Владелец платформы не может вступать в агентство.",
            )
        if user.agency_id is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Вы уже состоите в агентстве.",
            )
        # Пользователь существовал без агентства — привязываем.
        user.agency_id = invite.agency_id
        user.role = invite.role
        user.is_active = True
        if username:
            user.username = username
        if full_name:
            user.full_name = full_name
    else:
        user = user_repo.create(
            db,
            telegram_id=telegram_id,
            role=invite.role,
            agency_id=invite.agency_id,
            username=username,
            full_name=full_name,
        )

    # 5. Помечаем приглашение использованным (одноразовое).
    invite.used_at = datetime.now(timezone.utc)
    invite.used_by_telegram_id = telegram_id
    user.last_login_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(user)

    # 6. Выдаём пропуск (как при обычном входе).
    return auth_service.build_auth_response(db, user)
