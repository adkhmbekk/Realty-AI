"""
Запасной провайдер при сбое основного.

Если Gemini «икнул» (перегрузка 503 или лимит 429 → _post_with_retry бросает
import_ai_rate_limited), разбор объявления должен УЙТИ на OpenRouter, а не упасть.
Именно из-за этого массовый импорт «отказывал» при всплесках 503 у Gemini.
Сетевых вызовов нет — провайдеры замоканы.
"""
import pytest
from fastapi import status

from app.config import settings
from app.core.errors import AppError
from app.services import listing_import_service as lis


def _force_providers(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "x", raising=False)
    monkeypatch.setattr(settings, "openrouter_api_key", "y", raising=False)
    monkeypatch.setattr(settings, "import_ai_providers", "gemini,openrouter", raising=False)


def _boom(*_a, **_k):
    raise AppError("import_ai_rate_limited", status.HTTP_429_TOO_MANY_REQUESTS)


def test_gemini_failure_falls_back_to_openrouter(monkeypatch):
    _force_providers(monkeypatch)
    monkeypatch.setattr(lis, "_extract_gemini", _boom)
    monkeypatch.setattr(
        lis, "_extract_openrouter",
        lambda *a, **k: {"type": "Квартира", "price": 50000, "currency": "USD"},
    )
    out = lis._extract_with_ai("текст объявления", ["Юнусабад"])
    assert out["type"] == "Квартира" and out["price"] == 50000


def test_both_providers_fail_raises_rate_limited(monkeypatch):
    _force_providers(monkeypatch)
    monkeypatch.setattr(lis, "_extract_gemini", _boom)
    monkeypatch.setattr(lis, "_extract_openrouter", _boom)
    with pytest.raises(AppError) as exc:
        lis._extract_with_ai("текст объявления", ["Юнусабад"])
    assert exc.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS


def test_gemini_overload_503_waits_and_does_not_use_openrouter(monkeypatch):
    """503 у Gemini = временная перегрузка: ждём Gemini (пауза-повтор), на запасной
    НЕ уходим. Это и есть пожелание — OpenRouter только при 429 (кончились деньги)."""
    _force_providers(monkeypatch)
    or_calls = {"n": 0}

    def _gemini_503(*_a, **_k):
        raise AppError("import_ai_rate_limited", status.HTTP_503_SERVICE_UNAVAILABLE)

    def _or(*_a, **_k):
        or_calls["n"] += 1
        return {"type": "Квартира", "price": 1}

    monkeypatch.setattr(lis, "_extract_gemini", _gemini_503)
    monkeypatch.setattr(lis, "_extract_openrouter", _or)
    with pytest.raises(AppError) as exc:
        lis._extract_with_ai("текст объявления", ["Юнусабад"])
    # Пауза массового импорта (429), а не падение; OpenRouter НЕ вызван.
    assert exc.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert or_calls["n"] == 0
