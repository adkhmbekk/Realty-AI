"""
Вход по номеру телефона (SMS-код) — для нативного приложения.

Поток:
  1. /auth/phone/request  → нормализуем номер, гасим старые коды, создаём новый
     6-значный код (TTL 5 мин) и шлём SMS (Eskiz). Без учётки Eskiz — 503
     sms_not_configured (кнопка в приложении говорит «пока недоступно»).
  2. /auth/phone/verify   → код верный → сессия. Аккаунт резолвим по номеру:
     совпал с существующим (номер — «якорь», уникален среди активных) → входим
     в него; нет — создаём новый ЛИЧНЫЙ аккаунт (role='user', phone_verified).

Защита: троттлинг повторной отправки (60с на номер), лимит неверных вводов
(5 → код гасится), одноразовость через атомарный claim (pending → consumed),
rate-limit по IP на роутах. Каждый публичный write-путь коммитит сам (урок
tg-login: get_db не коммитит, а verify приходит в другой сессии).
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import status
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.repositories import phone_otp_repo, user_repo
from app.services import auth_service, sms_service
from app.services.auth_service import _PHONE_RE, _normalize_phone

logger = logging.getLogger(__name__)

CODE_TTL_SECONDS = 300      # SMS-код живёт 5 минут
RESEND_COOLDOWN_SECONDS = 60  # не чаще одного SMS в минуту на номер
MAX_ATTEMPTS = 5            # неверных вводов до гашения кода


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(dt: datetime) -> datetime:
    """Привести значение из БД к timezone-aware (SQLite отдаёт naive)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _valid_phone_or_raise(raw: str) -> str:
    normalized = _normalize_phone(raw)
    if not _PHONE_RE.match(normalized):
        raise AppError("phone_invalid", status.HTTP_400_BAD_REQUEST)
    return normalized


def request_code(db: Session, phone: str) -> dict:
    """Выслать SMS-код на номер. Возвращает {expires_in} (номер не раскрываем)."""
    normalized = _valid_phone_or_raise(phone)
    if not sms_service.is_configured():
        raise AppError("sms_not_configured", status.HTTP_503_SERVICE_UNAVAILABLE)

    # Троттлинг: свежий (< 60с) pending-код уже есть → не шлём новый SMS
    # (защита от SMS-бомбинга по одному номеру; по IP лимитирует роут).
    prev = phone_otp_repo.latest_pending(db, normalized)
    if prev is not None:
        age = (_now() - _as_aware(prev.created_at)).total_seconds()
        if age < RESEND_COOLDOWN_SECONDS and _as_aware(prev.expires_at) > _now():
            raise AppError("otp_too_soon", status.HTTP_429_TOO_MANY_REQUESTS)

    # Активен только один код: старые гасим, создаём новый.
    phone_otp_repo.expire_pending(db, normalized)
    code = f"{secrets.randbelow(1_000_000):06d}"
    phone_otp_repo.create(db, normalized, code, _now() + timedelta(seconds=CODE_TTL_SECONDS))
    # Коммит ДО отправки: verify придёт в другой сессии и обязан видеть код.
    db.commit()

    sent = sms_service.send_sms(
        normalized, f"Realty AI: код входа {code}. Никому его не сообщайте."
    )
    if not sent:
        raise AppError("sms_send_failed", status.HTTP_502_BAD_GATEWAY)
    return {"expires_in": CODE_TTL_SECONDS}


def verify_code(db: Session, phone: str, code: str) -> dict:
    """Обменять SMS-код на сессию (вход в существующий аккаунт или новый личный)."""
    normalized = _valid_phone_or_raise(phone)
    row = phone_otp_repo.latest_pending(db, normalized)
    # Единый ответ на «нет кода / не тот код»: не раскрываем, что именно не так.
    if row is None:
        raise AppError("otp_invalid", status.HTTP_401_UNAUTHORIZED)
    if _as_aware(row.expires_at) < _now():
        row.status = "expired"
        db.commit()
        raise AppError("otp_expired", status.HTTP_401_UNAUTHORIZED)
    if row.attempts >= MAX_ATTEMPTS:
        row.status = "expired"
        db.commit()
        raise AppError("otp_too_many", status.HTTP_429_TOO_MANY_REQUESTS)
    if not secrets.compare_digest(row.code, (code or "").strip()):
        row.attempts += 1
        if row.attempts >= MAX_ATTEMPTS:
            row.status = "expired"
        db.commit()
        raise AppError("otp_invalid", status.HTTP_401_UNAUTHORIZED)

    # Код верный — атомарный claim (одноразовость при параллельных verify).
    if not phone_otp_repo.claim_pending(db, row.id):
        raise AppError("otp_invalid", status.HTTP_401_UNAUTHORIZED)

    # Резолв аккаунта: номер — «якорь». Существующий (в т.ч. Telegram-аккаунт с
    # этим номером) → входим в него; иначе — новый личный аккаунт.
    user = user_repo.get_by_phone(db, normalized)
    if user is not None and not user.is_active:
        raise AppError("access_deactivated", status.HTTP_403_FORBIDDEN)
    if user is None:
        user = user_repo.create(db, telegram_id=None, role="user", agency_id=None)
        user.phone = normalized
    user.phone_verified = True  # владение номером доказано кодом
    user.last_login_at = _now()
    db.commit()
    db.refresh(user)
    return auth_service.build_auth_response(db, user)
