"""
Бизнес-логика уровня платформы (для суперадмина).

Сейчас здесь одна задача — передача прав владельца платформы (суперадмина)
другому человеку. Это нужно, когда владелец отдаёт проект другому человеку
(например, родственнику): новый человек становится суперадмином, а прежний
складывает полномочия.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models.user import User
from app.repositories import user_repo


def transfer_superadmin(
    db: Session,
    current_superadmin: User,
    new_telegram_id: int,
    new_username: Optional[str] = None,
) -> User:
    """
    Передать роль суперадмина другому человеку по его Telegram ID.

    Правила:
      - нельзя передать роль самому себе;
      - новый человек не должен состоять в каком-либо агентстве
        (иначе агентство останется без него — сначала выведите его оттуда);
      - после передачи прежний суперадмин деактивируется (доступ закрывается,
        история сохраняется). При необходимости новый владелец сможет вернуть
        ему доступ или назначить заново.
    """
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
    return new_owner
