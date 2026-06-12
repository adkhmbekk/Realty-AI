"""
Тесты защиты от SSRF в импорте объявления по ссылке.

Закрывают находки security-ревью 2026-06: запасной путь через браузер
(Playwright) и автоследование редиректам не должны давать достучаться до
внутренних адресов или локальных файлов (file://, localhost, 169.254.x и т.п.).
"""
import pytest

from app.core.errors import AppError
from app.services import browser_render_service, listing_import_service as li


# Адреса, которые НИКОГДА не должны загружаться сервером.
_INTERNAL_URLS = [
    "file:///etc/passwd",
    "file:///app/.env",
    "http://localhost:8000/health",
    "http://127.0.0.1:4040/",
    "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.5/",
    "http://192.168.1.1/",
    "ftp://example.com/x",
]


@pytest.mark.parametrize("url", _INTERNAL_URLS)
def test_fetch_listing_rejects_internal_before_browser(url, monkeypatch):
    """_fetch_listing обязан отклонить внутренний/непубличный адрес ДО того, как
    дело дойдёт до браузерного рендера. Если страж не сработает — тест явно
    провалится, потому что мы подменяем try_render на «взрыв»."""
    def _boom(_url):  # pragma: no cover — не должно вызываться
        raise AssertionError(f"браузер не должен запускаться для {_url}")

    monkeypatch.setattr(browser_render_service, "try_render", _boom)

    with pytest.raises(AppError):
        li._fetch_listing(url)


def test_render_guard_blocks_internal_directly():
    """Даже при прямом вызове _render внутренний адрес отклоняется (защита в
    глубину: _render не полагается на проверку вызывающего кода)."""
    with pytest.raises((AppError, ValueError)):
        browser_render_service._render("http://127.0.0.1:8000/", 1000)
    with pytest.raises((AppError, ValueError)):
        browser_render_service._render("file:///etc/passwd", 1000)


def test_fetch_html_does_not_follow_redirect_to_internal(monkeypatch):
    """_fetch_html не следует за Location на внутренний адрес: каждый хоп
    проходит _assert_public_url, поэтому редирект на localhost → AppError."""
    import httpx

    class _Resp:
        def __init__(self, status_code, headers=None):
            self.status_code = status_code
            self.headers = headers or {}
            self.url = "https://safe.example/"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def iter_bytes(self):
            yield b""

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def stream(self, method, url, headers=None):
            # Внешний адрес отвечает редиректом на внутренний.
            return _Resp(302, {"Location": "http://127.0.0.1:8000/secret"})

    # внешний хост резолвится «нормально», внутренний поймает _assert_public_url
    monkeypatch.setattr(httpx, "Client", _Client)
    monkeypatch.setattr(
        li.photo_service, "_assert_public_url",
        lambda u: (_ for _ in ()).throw(AppError("link_internal_blocked", 400))
        if "127.0.0.1" in u or "localhost" in u else None,
    )

    with pytest.raises(AppError):
        li._fetch_html("https://safe.example/start")
