"""
SSRF-пиннинг (H1): резолвим и валидируем адрес ОДИН раз, соединяемся строго по
проверенному IP. Закрывает DNS-rebinding (проверили публичный IP — а httpx
резолвил заново и уходил на внутренний) и прямые IP-литералы во внутреннюю сеть.
"""
import httpx
import pytest

from app.core import ssrf
from app.core.errors import AppError


def _addrinfo(*ips):
    # Формат socket.getaddrinfo: (family, type, proto, canonname, (ip, port)).
    return [(2, 1, 6, "", (ip, 0)) for ip in ips]


def test_resolve_public_ip_ok(monkeypatch):
    monkeypatch.setattr(ssrf.socket, "getaddrinfo", lambda h, p: _addrinfo("93.184.216.34"))
    assert ssrf.resolve_public_ip("example.com") == "93.184.216.34"


def test_resolve_blocks_if_any_address_internal(monkeypatch):
    # Rebind-защита: если ХОТЯ БЫ один адрес внутренний — блокируем хост целиком.
    monkeypatch.setattr(
        ssrf.socket, "getaddrinfo",
        lambda h, p: _addrinfo("93.184.216.34", "10.0.0.5"),
    )
    with pytest.raises(AppError) as e:
        ssrf.resolve_public_ip("rebind.evil")
    assert e.value.key == "link_internal_blocked"


def test_assert_public_url_rejects_non_http():
    with pytest.raises(AppError) as e:
        ssrf.assert_public_url("file:///etc/passwd")
    assert e.value.key == "only_http_links"


def test_pin_rewrites_connection_to_validated_ip(monkeypatch):
    monkeypatch.setattr(ssrf, "resolve_public_ip", lambda host: "93.184.216.34")
    req = httpx.Request("GET", "https://example.com/a.jpg")
    ssrf._pin(req)
    # Соединение идёт на проверенный IP…
    assert req.url.host == "93.184.216.34"
    # …но имя хоста сохранено в Host и в SNI (для проверки TLS-сертификата).
    assert req.headers["Host"] == "example.com"
    assert req.extensions.get("sni_hostname") == "example.com"


def test_pin_blocks_loopback_ip_literal():
    req = httpx.Request("GET", "http://127.0.0.1/x")
    with pytest.raises(AppError) as e:
        ssrf._pin(req)
    assert e.value.key == "link_internal_blocked"


def test_pin_blocks_cloud_metadata_ip_literal():
    req = httpx.Request("GET", "http://169.254.169.254/latest/meta-data/")
    with pytest.raises(AppError) as e:
        ssrf._pin(req)
    assert e.value.key == "link_internal_blocked"
