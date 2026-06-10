"""
Тесты лёгкого мониторинга сбоев: логируем и уведомляем суперадмина в бот,
с защитой от спама (троттлинг) и переключателем.
"""
import app.core.monitoring as monitoring
from app.config import settings
from app.services import telegram_service


def _patch(monkeypatch, *, enabled=True, superadmin=12345, configured=True):
    sent = []
    monkeypatch.setattr(settings, "error_alerts_enabled", enabled)
    monkeypatch.setattr(settings, "superadmin_telegram_id", superadmin)
    # Второй источник (список) держим пустым — тесты детерминированы.
    monkeypatch.setattr(settings, "superadmin_telegram_ids", None)
    monkeypatch.setattr(telegram_service, "is_configured", lambda: configured)
    monkeypatch.setattr(telegram_service, "notify_async",
                        lambda chat_ids, text: sent.append((list(chat_ids), text)))
    # Чистим внутренний троттлинг между тестами.
    monkeypatch.setattr(monitoring, "_last_sent", {})
    return sent


def test_reports_and_notifies_superadmin(monkeypatch):
    sent = _patch(monkeypatch)
    ok = monitoring.report_error(ValueError("boom"), path="/api/v1/x", method="POST", now=1000.0)
    assert ok is True
    assert len(sent) == 1
    chat_ids, text = sent[0]
    assert chat_ids == [12345]
    assert "boom" in text and "/api/v1/x" in text


def test_throttles_duplicate_errors(monkeypatch):
    sent = _patch(monkeypatch)
    assert monitoring.report_error(ValueError("boom"), path="/p", now=1000.0) is True
    # Та же ошибка спустя минуту — не шлём повторно.
    assert monitoring.report_error(ValueError("boom"), path="/p", now=1060.0) is False
    # А вот спустя >5 минут — снова можно.
    assert monitoring.report_error(ValueError("boom"), path="/p", now=1000.0 + 301) is True
    assert len(sent) == 2


def test_different_errors_not_throttled_together(monkeypatch):
    sent = _patch(monkeypatch)
    assert monitoring.report_error(ValueError("a"), path="/p", now=1000.0) is True
    assert monitoring.report_error(KeyError("b"), path="/p", now=1000.0) is True
    assert len(sent) == 2


def test_disabled_switch(monkeypatch):
    sent = _patch(monkeypatch, enabled=False)
    assert monitoring.report_error(ValueError("x"), now=1000.0) is False
    assert sent == []


def test_no_superadmin_no_send(monkeypatch):
    sent = _patch(monkeypatch, superadmin=None)
    assert monitoring.report_error(ValueError("x"), now=1000.0) is False
    assert sent == []
