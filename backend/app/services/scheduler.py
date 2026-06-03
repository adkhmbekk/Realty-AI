"""
Фоновые задачи по расписанию (внутри backend).

Сейчас здесь одна задача: ЗАРАНЕЕ предупреждать владельца агентства о скором
окончании подписки (бот пишет ему за несколько дней). Задача крутится в
отдельном демон-потоке и не мешает обработке запросов.

Авто-БЭКАПЫ реализованы НЕ здесь, а отдельным сервисом `backup` в
docker-compose (он использует образ postgres:16 с нужной версией pg_dump и
складывает копии в папку backups, как и ручной backup.bat).
"""
import logging
import math
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.agency import Agency
from app.db.models.user import User
from app.db.session import SessionLocal
from app.services import telegram_service

logger = logging.getLogger("uvicorn.error")

# Как часто проверять подписки (одна задача в сутки была бы достаточна, но
# проверяем чаще, чтобы не зависеть от точного момента запуска).
CHECK_INTERVAL_SECONDS = 6 * 3600
# Не слать одному агентству предупреждение чаще, чем раз в ~сутки.
_WARN_THROTTLE = timedelta(hours=20)
_ACTIVE_STATUSES = ("trial", "active")


def _as_utc(dt: datetime | None) -> datetime | None:
    """Привести дату к timezone-aware UTC (на случай наивных дат из БД)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _owner_telegram_id(db: Session, agency_id: int) -> int | None:
    """Telegram ID главного админа агентства (или любого админа как запас)."""
    owner = db.execute(
        select(User).where(
            User.agency_id == agency_id,
            User.role == "agency_admin",
            User.is_owner.is_(True),
            User.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if owner is None:
        owner = db.execute(
            select(User)
            .where(
                User.agency_id == agency_id,
                User.role == "agency_admin",
                User.is_active.is_(True),
            )
            .order_by(User.created_at, User.id)
        ).scalars().first()
    return owner.telegram_id if owner and owner.telegram_id else None


def run_subscription_warnings(db: Session, now: datetime | None = None) -> int:
    """
    Найти агентства, у которых подписка истекает в ближайшие
    settings.subscription_warn_days дней, и предупредить их владельцев.
    Возвращает число отправленных предупреждений (для тестов/логов).
    """
    warn_days = settings.subscription_warn_days
    if warn_days <= 0 or not telegram_service.is_configured():
        return 0

    now = now or datetime.now(timezone.utc)
    window_end = now + timedelta(days=warn_days)

    sent = 0
    agencies = db.execute(select(Agency)).scalars().all()
    for agency in agencies:
        if agency.status not in _ACTIVE_STATUSES:
            continue
        expires = _as_utc(agency.subscription_expires_at)
        if expires is None or expires <= now or expires > window_end:
            continue
        warned = _as_utc(agency.subscription_warned_at)
        if warned is not None and (now - warned) < _WARN_THROTTLE:
            continue

        chat_id = _owner_telegram_id(db, agency.id)
        if chat_id is not None:
            days_left = max(1, math.ceil((expires - now).total_seconds() / 86400))
            name = agency.project_name or agency.name
            text = (
                f"⏳ Подписка агентства «{name}» скоро закончится.\n"
                f"Осталось дней: {days_left} (до {expires:%Y-%m-%d}).\n"
                f"Обратитесь к владельцу платформы для продления, "
                f"чтобы доступ не приостановился."
            )
            if telegram_service.send_message(chat_id, text):
                sent += 1
        # Метку ставим в любом случае, чтобы не долбить проверками каждые 6 часов.
        agency.subscription_warned_at = now

    if sent or any(a.subscription_warned_at == now for a in agencies):
        db.commit()
    return sent


def expire_due_subscriptions(db: Session, now: datetime | None = None) -> int:
    """
    Перевести в статус 'expired' агентства, у которых срок подписки истёк, а
    статус всё ещё trial/active. Доступ блокируется и так (agency_is_active
    проверяет дату), но явный статус 'expired' делает панель суперадмина
    правдивой: видно, кто реально не оплатил. Возвращает число переведённых.
    """
    now = now or datetime.now(timezone.utc)
    changed = 0
    agencies = db.execute(
        select(Agency).where(Agency.status.in_(_ACTIVE_STATUSES))
    ).scalars().all()
    for agency in agencies:
        expires = _as_utc(agency.subscription_expires_at)
        if expires is not None and expires < now:
            agency.status = "expired"
            changed += 1
    if changed:
        db.commit()
    return changed


def _loop() -> None:
    logger.info("Планировщик: проверка подписок запущена (раз в %s ч).", CHECK_INTERVAL_SECONDS // 3600)
    while True:
        try:
            db = SessionLocal()
            try:
                expired = expire_due_subscriptions(db)
                if expired:
                    logger.info("Планировщик: агентств переведено в 'expired': %s.", expired)
                count = run_subscription_warnings(db)
                if count:
                    logger.info("Планировщик: отправлено предупреждений о подписке: %s.", count)
            finally:
                db.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Планировщик: ошибка проверки подписок: %s", exc)
        time.sleep(CHECK_INTERVAL_SECONDS)


def start_scheduler() -> None:
    """Запустить фоновые задачи (демон-поток). Безопасно при любом окружении."""
    threading.Thread(target=_loop, name="realty-scheduler", daemon=True).start()
