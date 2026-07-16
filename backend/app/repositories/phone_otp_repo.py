"""
Доступ к одноразовым SMS-кодам входа (phone_otp_codes).
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models.phone_otp_code import PhoneOtpCode


def create(db: Session, phone: str, code: str, expires_at: datetime) -> PhoneOtpCode:
    row = PhoneOtpCode(phone=phone, code=code, status="pending", expires_at=expires_at)
    db.add(row)
    db.flush()
    return row


def latest_pending(db: Session, phone: str) -> Optional[PhoneOtpCode]:
    """Самый свежий pending-код номера (актуален только он: старые гасятся)."""
    return db.execute(
        select(PhoneOtpCode)
        .where(PhoneOtpCode.phone == phone, PhoneOtpCode.status == "pending")
        .order_by(PhoneOtpCode.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def expire_pending(db: Session, phone: str) -> None:
    """Погасить все pending-коды номера (перед выдачей нового: активен один)."""
    db.execute(
        update(PhoneOtpCode)
        .where(PhoneOtpCode.phone == phone, PhoneOtpCode.status == "pending")
        .values(status="expired")
    )


def claim_pending(db: Session, row_id: int) -> bool:
    """Атомарно «забрать» код (pending → consumed): при двух одновременных verify
    сессию получает только один запрос (тот же паттерн, что у tg-login кодов)."""
    res = db.execute(
        update(PhoneOtpCode)
        .where(PhoneOtpCode.id == row_id, PhoneOtpCode.status == "pending")
        .values(status="consumed")
    )
    return res.rowcount == 1
