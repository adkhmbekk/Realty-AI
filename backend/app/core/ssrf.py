"""
Единая защита от SSRF для исходящих запросов по ПОЛЬЗОВАТЕЛЬСКИМ ссылкам
(импорт объявления по ссылке, импорт фото, скачивание изображений).

Проблема (H1, DNS-rebinding / TOCTOU): раньше адрес проверялся отдельно
(резолвили хост, смотрели класс IP), а затем httpx РЕЗОЛВИЛ хост заново уже
при установке соединения. Между этими двумя резолвами вредоносный DNS мог
подменить публичный IP на внутренний (169.254.169.254, 127.0.0.1, 10.x и т.п.),
и запрос уходил во внутреннюю сеть В ОБХОД проверки.

Решение: резолвим и валидируем ОДИН раз, затем соединяемся строго по
проверенному IP (пиннинг), сохраняя оригинальный Host и SNI. Так проверенный
адрес и адрес фактического соединения гарантированно совпадают — переиграть
резолв между проверкой и соединением уже нельзя.

Использование: создавать httpx-клиент с нашим транспортом —
    httpx.Client(transport=sync_transport(), follow_redirects=False, ...)
    httpx.AsyncClient(transport=async_transport(), follow_redirects=False, ...)
Дополнительно (defense-in-depth) можно звать assert_public_url(url) до запроса.
"""
import ipaddress
import socket
import time
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import status

from app.core.errors import AppError

# Внутри Docker/WSL встроенный DNS изредка кратковременно «проваливается»
# (getaddrinfo: Temporary failure in name resolution) — несколько раз повторяем.
_DNS_RETRY_BACKOFF = (0.5, 1.5, 3.0)


def _resolve_infos(host: str):
    """getaddrinfo с повторами при кратковременном сбое DNS (Docker/WSL)."""
    last_exc: Optional[Exception] = None
    for delay in (0.0,) + _DNS_RETRY_BACKOFF:
        if delay:
            time.sleep(delay)
        try:
            return socket.getaddrinfo(host, None)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
    raise AppError("link_host_unresolved", status.HTTP_400_BAD_REQUEST) from last_exc


def _is_forbidden_ip(ip: str) -> bool:
    """True, если адрес ведёт во внутреннюю сеть/служебный диапазон (или неразбираем)."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True  # не смогли разобрать — блокируем на всякий случай
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def resolve_public_ip(host: str) -> str:
    """
    Разрешить host и вернуть ПРОВЕРЕННЫЙ публичный IP для пиннинга соединения.

    ВАЖНО: если ХОТЯ БЫ один из адресов host ведёт во внутреннюю сеть — блокируем
    хост целиком (а не просто выбираем «хороший» адрес). Иначе rebind между
    несколькими A-записями мог бы проскользнуть. Возвращаем первый публичный
    адрес — именно к нему затем и подключаемся.
    """
    infos = _resolve_infos(host)
    public: Optional[str] = None
    for info in infos:
        ip = info[4][0]
        if _is_forbidden_ip(ip):
            raise AppError("link_internal_blocked", status.HTTP_400_BAD_REQUEST)
        if public is None:
            public = ip
    if public is None:
        raise AppError("invalid_link", status.HTTP_400_BAD_REQUEST)
    return public


def assert_public_url(url: str) -> str:
    """
    Проверить схему (только http/https) и адрес; вернуть проверенный публичный IP.
    Бросает AppError при непубличном/непроверяемом адресе.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise AppError("only_http_links", status.HTTP_400_BAD_REQUEST)
    host = parsed.hostname
    if not host:
        raise AppError("invalid_link", status.HTTP_400_BAD_REQUEST)
    return resolve_public_ip(host)


def _pin(request: httpx.Request) -> None:
    """
    Привязать (pin) соединение к ПРОВЕРЕННОМУ IP хоста запроса.

    Хост URL заменяем на проверенный IP (соединение идёт строго туда, без
    повторного DNS), а оригинальное имя сохраняем в заголовке Host и в SNI —
    чтобы TLS-сертификат проверялся против настоящего доменного имени.
    """
    host = request.url.host
    if not host:
        raise AppError("invalid_link", status.HTTP_400_BAD_REQUEST)

    # Если в URL уже указан IP-литерал — DNS не участвует, просто валидируем его.
    try:
        ipaddress.ip_address(host)
        if _is_forbidden_ip(host):
            raise AppError("link_internal_blocked", status.HTTP_400_BAD_REQUEST)
        return
    except ValueError:
        pass  # обычное доменное имя — резолвим и пиннуем ниже

    ip = resolve_public_ip(host)
    port = request.url.port
    # Оригинальный Host — в заголовок; SNI — через extensions; хост URL → IP.
    request.headers["Host"] = host if port is None else f"{host}:{port}"
    ext = dict(request.extensions or {})
    ext["sni_hostname"] = host
    request.extensions = ext
    request.url = request.url.copy_with(host=ip)


class _PinnedTransport(httpx.HTTPTransport):
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        _pin(request)
        return super().handle_request(request)


class _AsyncPinnedTransport(httpx.AsyncHTTPTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        _pin(request)
        return await super().handle_async_request(request)


def sync_transport() -> httpx.HTTPTransport:
    """Транспорт с пиннингом IP для httpx.Client (retries на уровне вызова)."""
    return _PinnedTransport()


def async_transport() -> httpx.AsyncHTTPTransport:
    """Транспорт с пиннингом IP для httpx.AsyncClient."""
    return _AsyncPinnedTransport()
