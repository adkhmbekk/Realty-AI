"""
Простой ограничитель частоты запросов (rate limiting) на чистом Python,
без внешних зависимостей.

Зачем: публичные эндпоинты (вход через Telegram, вступление по коду) и тяжёлые
операции (загрузка фото) без ограничений можно «долбить» бесконечно — это
открывает путь к подбору, спаму и отказу в обслуживании (DoS).

Как работает: фиксированное окно (fixed window) на каждый ключ
«<область>:<IP-клиента>». Счётчик в памяти процесса (за туннелем у нас один
процесс — этого достаточно; при горизонтальном масштабировании стоит заменить
на общий Redis).

Использование — как зависимость FastAPI на конкретном маршруте:

    from app.core.ratelimit import rate_limit

    @router.post("/telegram", dependencies=[Depends(rate_limit(10, 60, "auth"))])
    def telegram_login(...):
        ...
"""
import threading
import time
from typing import Callable

from fastapi import Request, status

from app.core.errors import AppError

_lock = threading.Lock()
# ключ -> (начало_текущего_окна, счётчик)
_hits: "dict[str, tuple[float, int]]" = {}


def _client_ip(request: Request) -> str:
    """
    Определить IP клиента. Приложение работает за обратным прокси (Caddy) и
    туннелем (ngrok), поэтому реальный адрес — в X-Forwarded-For (берём первый,
    самый левый — это исходный клиент). Если заголовка нет — адрес соединения.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    client = request.client
    return client.host if client else "unknown"


def rate_limit(max_requests: int, window_seconds: int, scope: str) -> Callable:
    """
    Вернуть зависимость FastAPI, которая разрешает не более max_requests
    запросов за window_seconds секунд на каждый IP в рамках области scope.
    При превышении — 429 Too Many Requests (локализованное сообщение).
    """

    def dependency(request: Request) -> None:
        now = time.time()
        key = f"{scope}:{_client_ip(request)}"
        with _lock:
            window_start, count = _hits.get(key, (now, 0))
            if now - window_start >= window_seconds:
                window_start, count = now, 0
            count += 1
            _hits[key] = (window_start, count)
            # Периодическая чистка устаревших ключей, чтобы словарь не рос.
            if len(_hits) > 10000:
                for k, (started, _c) in list(_hits.items()):
                    if now - started >= window_seconds:
                        _hits.pop(k, None)
        if count > max_requests:
            raise AppError(
                "rate_limited",
                status.HTTP_429_TOO_MANY_REQUESTS,
                headers={"Retry-After": str(window_seconds)},
            )

    return dependency
