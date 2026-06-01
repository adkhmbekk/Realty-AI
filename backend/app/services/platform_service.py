"""
Бизнес-логика уровня платформы (для суперадмина).

Сейчас здесь одна задача — передача прав владельца платформы (суперадмина)
другому человеку. Это нужно, когда владелец отдаёт проект другому человеку
(например, родственнику): новый человек становится суперадмином, а прежний
складывает полномочия.
"""
from datetime import datetime, timezone
from typing import Optional

import secrets
import time

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models.user import User
from app.repositories import user_repo
from app.services import telegram_service

# Временное хранилище кодов подтверждения передачи прав (в памяти процесса).
# Ключ — id текущего суперадмина. Код живёт 10 минут, не больше 5 попыток ввода.
_pending_transfers: dict[int, dict] = {}
_CODE_TTL_SECONDS = 600
_MAX_ATTEMPTS = 5


def _validate_new_owner(db: Session, current_superadmin: User, new_telegram_id: int) -> None:
    if new_telegram_id == current_superadmin.telegram_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Вы уже являетесь владельцем платформы.",
        )
    existing = user_repo.get_by_telegram_id(db, new_telegram_id)
    if existing is not None and existing.agency_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Этот человек состоит в агентстве. Сначала выведите его из "
            "агентства, затем передавайте права владельца.",
        )


def request_transfer_code(
    db: Session,
    current_superadmin: User,
    new_telegram_id: int,
    new_username: Optional[str] = None,
) -> dict:
    """
    Шаг 1 передачи прав: проверить данные и отправить текущему владельцу
    одноразовый код подтверждения в его чат с ботом.
    """
    _validate_new_owner(db, current_superadmin, new_telegram_id)
    if not telegram_service.is_configured():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Бот не настроен — отправить код подтверждения невозможно.",
        )
    code = f"{secrets.randbelow(1_000_000):06d}"
    _pending_transfers[current_superadmin.id] = {
        "code": code,
        "new_telegram_id": new_telegram_id,
        "new_username": new_username,
        "expires": time.time() + _CODE_TTL_SECONDS,
        "attempts": 0,
    }
    sent = telegram_service.send_message(
        current_superadmin.telegram_id,
        f"🔐 Код подтверждения передачи платформы: {code}\n"
        f"Никому его не сообщайте. Код действует 10 минут.",
    )
    if not sent:
        _pending_transfers.pop(current_superadmin.id, None)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Не удалось отправить код. Откройте чат с ботом, нажмите «Старт» и повторите.",
        )
    return {"ok": True}


def transfer_superadmin(
    db: Session,
    current_superadmin: User,
    new_telegram_id: int,
    code: str,
    new_username: Optional[str] = None,
) -> User:
    """
    Шаг 2 передачи прав: проверить код подтверждения и выполнить передачу.

    Правила:
      - требуется верный код, ранее отправленный в бот (см. request_transfer_code);
      - нельзя передать роль самому себе;
      - новый человек не должен состоять в каком-либо агентстве;
      - после передачи прежний суперадмин деактивируется (история сохраняется).
    """
    pending = _pending_transfers.get(current_superadmin.id)
    if not pending or pending["expires"] < time.time():
        _pending_transfers.pop(current_superadmin.id, None)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Код подтверждения не запрошен или истёк. Начните передачу заново.",
        )
    pending["attempts"] += 1
    if pending["attempts"] > _MAX_ATTEMPTS:
        _pending_transfers.pop(current_superadmin.id, None)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Слишком много попыток. Начните передачу заново.",
        )
    if (
        not code
        or code.strip() != pending["code"]
        or new_telegram_id != pending["new_telegram_id"]
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный код подтверждения.",
        )

    _validate_new_owner(db, current_superadmin, new_telegram_id)

    existing = user_repo.get_by_telegram_id(db, new_telegram_id)

    # 1. Назначаем нового суперадмина (создаём или повышаем существующего).
    if existing is not None:
        existing.role = "superadmin"
        existing.agency_id = None
        existing.is_owner = False
        existing.is_active = True
        if new_username:
            existing.username = new_username
        new_owner = existing
    else:
        new_owner = user_repo.create(
            db,
            telegram_id=new_telegram_id,
            role="superadmin",
            agency_id=None,
            username=new_username,
        )

    # 2. Прежний владелец складывает полномочия — деактивируем доступ.
    current_superadmin.is_active = False
    current_superadmin.last_login_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(new_owner)
    _pending_transfers.pop(current_superadmin.id, None)
    return new_owner
