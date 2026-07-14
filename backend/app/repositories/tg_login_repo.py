"""
Доступ к данным одноразовых кодов входа через Telegram-бота (tg_login_codes).
Только этот слой ходит в БД напрямую — бизнес-логика в tg_login_service.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.tg_login_code import TgLoginCode


def create(db: Session, code: str, expires_at: datetime) -> TgLoginCode:
    row = TgLoginCode(code=code, status="pending", expires_at=expires_at)
    db.add(row)
    db.flush()  # получить сгенерированный id
    return row


def get_by_code(db: Session, code: str) -> Optional[TgLoginCode]:
    return db.execute(
        select(TgLoginCode).where(TgLoginCode.code == code)
    ).scalar_one_or_none()
