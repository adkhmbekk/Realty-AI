"""
Рендер JS-страниц безголовым браузером (Playwright + Chromium).

Зачем: многие современные сайты объявлений (joymee, OLX и т.п.) — это
«одностраничники» (SPA). Сервер отдаёт пустой каркас, а данные объекта
(цена, комнаты, фото) дорисовываются скриптами уже в браузере. Обычный
HTTP-запрос видит только каркас, поэтому AI нечего разбирать.

Этот сервис открывает страницу настоящим Chromium, дожидается появления
контента и отдаёт готовый текст + ссылки на картинки. Используется как
ЗАПАСНОЙ путь: если быстрый HTTP-разбор дал мало текста — добираем браузером.

Надёжность: всё обёрнуто так, чтобы любая ошибка (браузер не установлен,
таймаут, падение) приводила к возврату None, а не к сбою импорта.
"""
from __future__ import annotations

import logging
import threading
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from app.config import settings
from app.services import photo_service

logger = logging.getLogger("uvicorn.error")

# Рендерим не больше одной страницы одновременно — каждый Chromium ест сотни МБ,
# а импорт у нас редкий и однопользовательский. Серилизация бережёт память.
_RENDER_LOCK = threading.Lock()
_LOCK_WAIT_SECONDS = 30

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
# Сколько непробельных символов в тексте считаем признаком «контент подгрузился».
_CONTENT_CHARS = 700


def is_available() -> bool:
    """Установлен ли Playwright (пакет). Браузер проверяется уже при запуске."""
    try:
        import playwright  # noqa: F401
        return True
    except Exception:
        return False


def try_render(url: str) -> Optional[Tuple[str, str, List[str]]]:
    """
    Открыть страницу в Chromium и вернуть (видимый_текст, финальный_url, картинки).
    При любой проблеме — None (вызывающий код откатится на обычный HTTP-разбор).
    """
    if not settings.import_browser_render or not is_available():
        return None
    if not _RENDER_LOCK.acquire(timeout=_LOCK_WAIT_SECONDS):
        logger.info("Рендер браузером занят, пропускаю: %s", url)
        return None
    try:
        return _render(url, settings.import_browser_timeout_ms)
    except Exception as exc:  # noqa: BLE001
        logger.info("Рендер браузером не удался (%s): %s", url, exc)
        return None
    finally:
        _RENDER_LOCK.release()


def _block_heavy(route):
    """Не качать сами картинки/шрифты/видео — ссылки в DOM остаются, а грузится
    страница в разы быстрее и стабильнее.

    ЗАЩИТА от SSRF: (1) режем любые схемы кроме http/https (file:, data:, blob:,
    ftp:); (2) проверяем КАЖДЫЙ под-запрос на публичность адреса — открытая
    страница могла бы через xhr/fetch/img/redirect заставить наш Chromium сходить
    на внутренний адрес (localhost, 10.x, link-local, *.internal и т.п.). Любой
    непубличный/непроверяемый запрос обрываем."""
    try:
        url = route.request.url
        if urlparse(url).scheme.lower() not in ("http", "https"):
            route.abort()
            return
        if route.request.resource_type in ("image", "media", "font"):
            route.abort()
            return
        # Резолвим хост и режем приватные/loopback/link-local диапазоны (бросает).
        try:
            photo_service._assert_public_url(url)
        except Exception:  # noqa: BLE001
            route.abort()
            return
        route.continue_()
    except Exception:  # noqa: BLE001
        # Не смогли проверить/обработать — безопаснее оборвать, чем пропустить.
        try:
            route.abort()
        except Exception:  # noqa: BLE001
            pass


def _render(url: str, timeout_ms: int) -> Tuple[str, str, List[str]]:
    from playwright.sync_api import sync_playwright

    # ЗАЩИТА от SSRF/чтения файлов: повторно убеждаемся, что адрес публичный и
    # по http/https, прежде чем отдать его браузеру (вызывающий код уже проверял,
    # но _render не должен полагаться на это — Playwright сам адрес не проверяет).
    if urlparse(url).scheme not in ("http", "https"):
        raise ValueError("browser render: only http/https allowed")
    photo_service._assert_public_url(url)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        try:
            page = browser.new_page(user_agent=_UA, locale="ru-RU")
            page.route("**/*", _block_heavy)
            # Не ждём networkidle: SPA шлют фоновые запросы без конца. Ждём DOM,
            # потом ждём, пока текст в теле перестанет расти (контент дорисован).
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            prev = -1
            for _ in range(15):  # до ~12 секунд ожидания контента
                text = page.inner_text("body") or ""
                n = len(text.replace(" ", "").replace("\n", ""))
                if n >= _CONTENT_CHARS and n == prev:
                    break  # текст стабилизировался — контент догрузился
                prev = n
                page.wait_for_timeout(800)
            text = page.inner_text("body") or ""
            final_url = page.url or url
            imgs = page.eval_on_selector_all(
                "img",
                "els => els.map(e => e.currentSrc || e.getAttribute('src') || '')",
            ) or []
            return text, final_url, [u for u in imgs if u]
        finally:
            browser.close()
