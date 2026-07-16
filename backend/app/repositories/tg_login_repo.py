"""
Доступ к данным одноразовых кодов входа через Telegram-бота (tg_login_codes).
Только этот слой ходит в БД напрямую — бизнес-логика в tg_login_service.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import select, update
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


def claim_confirmed(db: Session, code: str) -> Optional[TgLoginCode]:
    """Атомарно «забрать» подтверждённый код (confirmed → consumed).

    Условный UPDATE закрывает гонку двух одновременных poll: сессию выдаёт ТОЛЬКО
    тот запрос, чей UPDATE реально перевёл строку из confirmed. Коммита здесь нет —
    вызывающий коммитит вместе с выдачей сессии (провал логина откатит и claim).
    """
    res = db.execute(
        update(TgLoginCode)
        .where(TgLoginCode.code == code, TgLoginCode.status == "confirmed")
        .values(status="consumed")
    )
    if res.rowcount != 1:
        return None
    return get_by_code(db, code)
