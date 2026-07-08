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
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services import photo_service

logger = logging.getLogger("uvicorn.error")

# Как часто крутить общий цикл обслуживания (подчистка фото и т.п.).
CHECK_INTERVAL_SECONDS = 6 * 3600
# Подчистку осиротевших файлов фото запускаем не чаще раза в сутки.
_SWEEP_INTERVAL = timedelta(hours=24)
_last_sweep: datetime | None = None
# Суточный дайджест совпадений (Волна 8) — раз в ~сутки.
_DIGEST_INTERVAL = timedelta(hours=24)
_last_digest: datetime | None = None


def run_subscription_warnings(db: Session, now: datetime | None = None) -> int:
    """ПОДПИСКА ОТКЛЮЧЕНА (переход на тарифы, 2026-07): у всех бесплатный тариф
    'start' без срока — предупреждать не о чем. Оставлено стабом (задел на возврат
    платных тарифов), вызывается из _loop. Возвращает 0."""
    return 0


def expire_due_subscriptions(db: Session, now: datetime | None = None) -> int:
    """ПОДПИСКА ОТКЛЮЧЕНА (переход на тарифы, 2026-07): доступ не зависит от срока
    подписки. Оставлено стабом (задел на тарифы). Возвращает 0."""
    return 0


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
                # Подчистка осиротевших файлов фото — не чаще раза в сутки (M4).
                global _last_sweep
                now_ts = datetime.now(timezone.utc)
                if _last_sweep is None or (now_ts - _last_sweep) >= _SWEEP_INTERVAL:
                    try:
                        removed = photo_service.sweep_orphan_photos(db)
                        if removed:
                            logger.info("Планировщик: удалено осиротевших файлов фото: %s.", removed)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Планировщик: ошибка подчистки фото: %s", exc)
                    _last_sweep = now_ts
                # Авто-задачи «клиент молчит N дней» (Волна 4).
                try:
                    from app.services import client_service
                    made = client_service.run_autotask_tick(db)
                    if made:
                        logger.info("Планировщик: создано авто-задач «молчит»: %s.", made)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Планировщик: ошибка авто-задач: %s", exc)
                # Суточный дайджест совпадений (Волна 8) — для агентов с выбором 'daily'.
                global _last_digest
                if _last_digest is None or (now_ts - _last_digest) >= _DIGEST_INTERVAL:
                    try:
                        from app.services import client_service as _cs
                        since = _last_digest or (now_ts - _DIGEST_INTERVAL)
                        sent = _cs.run_match_digest(db, since)
                        if sent:
                            logger.info("Планировщик: отправлено дайджестов совпадений: %s.", sent)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Планировщик: ошибка дайджеста совпадений: %s", exc)
                    _last_digest = now_ts
            finally:
                db.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Планировщик: ошибка проверки подписок: %s", exc)
        time.sleep(CHECK_INTERVAL_SECONDS)


# Как часто синхронизировать Google-таблицы (двусторонне). Частый цикл сужает
# окно одновременных правок (вариант A разрешения конфликтов по времени).
SHEETS_SYNC_INTERVAL_SECONDS = 45


def _sheets_loop() -> None:
    from app.services import sheets_service  # ленивый импорт (без круговых зависимостей)

    logger.info("Планировщик: синхронизация Google Sheets (раз в %s с).", SHEETS_SYNC_INTERVAL_SECONDS)
    while True:
        try:
            db = SessionLocal()
            try:
                sheets_service.sync_all_connected(db)
            finally:
                db.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Планировщик: ошибка синхронизации Google Sheets: %s", exc)
        time.sleep(SHEETS_SYNC_INTERVAL_SECONDS)


# Как часто проверять «слушаемые» Telegram-каналы и добавлять новые посты.
# 30 минут (по просьбе владельца, 2026-07): реже опрос = меньше нагрузка на общий
# ключ Gemini; новые посты появляются в базе с задержкой до ~30 мин.
AUTOIMPORT_INTERVAL_SECONDS = 1800


def _autoimport_loop() -> None:
    import asyncio

    from app.services import telegram_channel_service as tg

    logger.info("Планировщик: авто-импорт Telegram (раз в %s с).", AUTOIMPORT_INTERVAL_SECONDS)
    while True:
        try:
            db = SessionLocal()
            try:
                created = asyncio.run(tg.auto_import_all(db))
                if created:
                    logger.info("Планировщик: авто-импорт добавил объектов: %s.", created)
            finally:
                db.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Планировщик: ошибка авто-импорта Telegram: %s", exc)
        time.sleep(AUTOIMPORT_INTERVAL_SECONDS)


# Как часто подбирать новые объекты под активные заявки клиентов.
MATCHING_INTERVAL_SECONDS = 120


def _matching_loop() -> None:
    from app.services import client_service

    logger.info("Планировщик: авто-подбор по заявкам клиентов (раз в %s с).", MATCHING_INTERVAL_SECONDS)
    while True:
        try:
            db = SessionLocal()
            try:
                created = client_service.run_matching_tick(db)
                if created:
                    logger.info("Планировщик: новых совпадений по заявкам: %s.", created)
            finally:
                db.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Планировщик: ошибка авто-подбора по заявкам: %s", exc)
        time.sleep(MATCHING_INTERVAL_SECONDS)


def start_scheduler() -> None:
    """Запустить фоновые задачи (демон-потоки). Безопасно при любом окружении."""
    threading.Thread(target=_loop, name="realty-scheduler", daemon=True).start()
    threading.Thread(target=_sheets_loop, name="realty-sheets-sync", daemon=True).start()
    threading.Thread(target=_autoimport_loop, name="realty-tg-autoimport", daemon=True).start()
    threading.Thread(target=_matching_loop, name="realty-client-matching", daemon=True).start()
