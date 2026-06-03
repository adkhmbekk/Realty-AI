"""
Точка входа backend-приложения Realty SaaS.

При старте:
  - применяем миграции БД (Alembic) — см. app/db/migrate.py;
  - при необходимости создаём суперадмина (если задан SUPERADMIN_TELEGRAM_ID);
  - GET /        — главная;
  - GET /health  — проверка сервиса и базы;
  - /api/v1/...  — рабочее API.

Одноразовые процедуры миграции данных (нормализация старых номеров объектов,
назначение главных админов в старых агентствах) теперь выполняются ровно один
раз — как миграция Alembic, а не при каждом запуске.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.router import api_router
from app.config import settings
from app.core.errors import MESSAGES, LanguageMiddleware, translate
from app.core.monitoring import report_error
from app.db import models  # noqa: F401  — нужен, чтобы модели зарегистрировались
from app.db.migrate import run_migrations
from app.db.models.user import User
from app.db.session import SessionLocal, get_db
from app.repositories import user_repo
from app.services.scheduler import start_scheduler

logger = logging.getLogger("uvicorn.error")


def bootstrap_superadmin() -> None:
    """
    Если в настройках задан SUPERADMIN_TELEGRAM_ID — сделать этого человека
    суперадмином (создать или повысить). Так владелец платформы получает
    доступ без ручного редактирования базы.
    """
    if not settings.superadmin_telegram_id:
        logger.info("SUPERADMIN_TELEGRAM_ID не задан — суперадмин не создаётся.")
        return

    db = SessionLocal()
    try:
        existing = user_repo.get_by_telegram_id(db, settings.superadmin_telegram_id)
        if existing is None:
            user_repo.create(
                db,
                telegram_id=settings.superadmin_telegram_id,
                role="superadmin",
                agency_id=None,
            )
            logger.info("Создан суперадмин (telegram_id=%s).", settings.superadmin_telegram_id)
        elif existing.role != "superadmin":
            existing.role = "superadmin"
            existing.agency_id = None
            existing.is_active = True
            logger.info("Пользователь повышен до суперадмина.")

        # Владелец платформы должен быть ОДИН. Если раньше суперадмином был
        # другой человек (сменили SUPERADMIN_TELEGRAM_ID) — снимаем у него права,
        # иначе суперадминов оказалось бы двое.
        others = db.execute(
            select(User).where(
                User.role == "superadmin",
                User.telegram_id != settings.superadmin_telegram_id,
            )
        ).scalars().all()
        for u in others:
            u.role = "agent"
            u.agency_id = None
            u.is_active = False
            logger.info(
                "Сняты права суперадмина с прежнего владельца (telegram_id=%s).",
                u.telegram_id,
            )

        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations()
    bootstrap_superadmin()
    # Папка для фотографий объектов (на Docker-томе).
    try:
        import os
        os.makedirs(settings.photos_dir, exist_ok=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Не удалось создать папку для фото (%s): %s", settings.photos_dir, exc)
    # Фоновые задачи по расписанию (предупреждение об окончании подписки).
    start_scheduler()
    yield


app = FastAPI(
    title="Realty SaaS API",
    description="Backend для Telegram Mini App риелторских агентств",
    version="0.3.0",
    lifespan=lifespan,
    # Интерактивная документация по умолчанию ВЫКЛЮЧЕНА (безопасно для прода).
    # Включить локально: ENABLE_DOCS=true.
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url="/redoc" if settings.enable_docs else None,
    openapi_url="/openapi.json" if settings.enable_docs else None,
)

# Максимальный размер тела запроса (защита от исчерпания памяти/DoS). Жёсткое
# ограничение по объёму ставится на крае (Caddy: request_body max_size); здесь —
# дополнительный заслон по заголовку Content-Length.
_MAX_BODY_BYTES = 25 * 1024 * 1024


@app.middleware("http")
async def _limit_body_size(request, call_next):
    cl = request.headers.get("content-length")
    if cl is not None:
        try:
            if int(cl) > _MAX_BODY_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={"detail": translate("file_too_large", request.headers.get("x-lang"))},
                )
        except ValueError:
            pass
    return await call_next(request)

# Подключаем рабочее API под префиксом /api/v1.
app.include_router(api_router)

# Определение языка запроса по заголовку X-Lang (для локализации ошибок).
app.add_middleware(LanguageMiddleware)


@app.exception_handler(RequestValidationError)
async def _localized_validation_handler(request, exc: RequestValidationError):
    """
    Локализуем ошибки проверки форм (422). Наши валидаторы бросают
    ValueError("<ключ>") — переводим такой ключ на язык запроса. Остальные
    (встроенные) ошибки оставляем как есть.
    """
    out = []
    for err in exc.errors():
        msg = err.get("msg", "")
        ctx = err.get("ctx") or {}
        err_obj = ctx.get("error")
        key = str(err_obj) if err_obj is not None else None
        if key and key in MESSAGES:
            msg = translate(key)
        out.append(
            {
                "loc": list(err.get("loc", [])),
                "msg": msg,
                "type": err.get("type", ""),
            }
        )
    return JSONResponse(status_code=422, content={"detail": out})


@app.exception_handler(Exception)
async def _unhandled_error_handler(request, exc: Exception):
    """
    Перехват НЕПРЕДВИДЕННЫХ ошибок (500): логируем и уведомляем суперадмина в
    бот (см. app/core/monitoring.py). Пользователю отдаём аккуратное сообщение
    на его языке. Ожидаемые ошибки (AppError/HTTPException) сюда не попадают —
    у них свой обработчик.
    """
    report_error(exc, path=request.url.path, method=request.method)
    # Язык берём прямо из заголовка запроса: обработчик 500 срабатывает выше
    # LanguageMiddleware (вне его контекста), поэтому ContextVar тут уже сброшен.
    lang = request.headers.get("x-lang")
    return JSONResponse(
        status_code=500, content={"detail": translate("internal_error", lang)}
    )


@app.get("/")
def root():
    """Главная страница. Если ты видишь это в браузере — backend работает."""
    return {
        "status": "ok",
        "service": "Realty SaaS backend",
        "message": "Поздравляю! Backend успешно запущен и работает.",
    }


@app.get("/health")
def health(db: Session = Depends(get_db)):
    """Проверка: жив ли сервис и доступна ли база данных."""
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "unavailable",
    }
