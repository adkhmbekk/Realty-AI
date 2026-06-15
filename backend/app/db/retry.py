"""
Бесшовный повтор запроса при обрыве соединения с базой данных.

ЗАЧЕМ. pool_pre_ping (см. app/db/session.py) проверяет соединение ПЕРЕД выдачей
из пула и спасает все запросы, кроме одного — того, что держал соединение прямо
в момент падения/перезапуска БД (например, при перезагрузке сервера). Такой
«летящий» запрос получает ошибку:
    OperationalError: server closed the connection unexpectedly

Здесь мы один раз тихо повторяем именно такой запрос. SQLAlchemy при обрыве
помечает ошибку флагом connection_invalidated и убирает мёртвое соединение из
пула — поэтому повтор берёт уже СВЕЖЕЕ, живое соединение и проходит нормально.

ПОЧЕМУ ЭТО БЕЗОПАСНО. Оборванная транзакция не зафиксировалась (commit не
прошёл) — БД её откатила, «половины» записи не остаётся. Тело запроса повтор
берёт из кэша Request (FastAPI кэширует разобранное тело), так что данные те же.

Повторяем ТОЛЬКО настоящий обрыв связи (connection_invalidated). Обычные ошибки
(битые данные, конфликт, нарушение ограничений) НЕ трогаем — у них повтор смысла
не имеет и может навредить.
"""
import asyncio
import logging

from fastapi import FastAPI
from fastapi.routing import APIRoute
from sqlalchemy.exc import DBAPIError
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import request_response

logger = logging.getLogger("uvicorn.error")

# Короткая пауза перед повтором: даёт пулу отдать новое соединение и чуть-чуть
# переждать момент, когда БД только-только поднимается.
_RETRY_DELAY_SECONDS = 0.5


def _is_db_disconnect(exc: Exception) -> bool:
    """True, если ошибка — именно разрыв соединения с БД (а не логическая)."""
    return isinstance(exc, DBAPIError) and bool(getattr(exc, "connection_invalidated", False))


def _wrap_route(route: APIRoute):
    """Обернуть штатный обработчик маршрута авто-повтором при обрыве БД."""
    original = route.get_route_handler()

    async def handler(request: Request) -> Response:
        try:
            return await original(request)
        except DBAPIError as exc:
            if not _is_db_disconnect(exc):
                raise
            logger.warning(
                "Обрыв соединения с БД на %s %s — повторяю запрос один раз.",
                request.method,
                request.url.path,
            )
            await asyncio.sleep(_RETRY_DELAY_SECONDS)
            return await original(request)

    return handler


def install_db_retry(app: FastAPI) -> None:
    """
    Обернуть ВСЕ HTTP-маршруты приложения единым авто-повтором при обрыве БД.

    Вызывать ОДИН раз — после того, как все маршруты зарегистрированы.
    """
    for route in app.routes:
        if isinstance(route, APIRoute):
            route.app = request_response(_wrap_route(route))
