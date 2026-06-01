"""
Тесты фоновой задачи предупреждений об окончании подписки.

Проверяем, что предупреждение уходит ТОЛЬКО владельцам активных агентств,
у которых подписка истекает в окне предупреждения, и что повторные проверки
не дублируют сообщение (троттлинг). На SQLite в памяти (фикстура db из conftest).
"""
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.db.models.agency import Agency
from app.db.models.user import User
from app.services import scheduler, telegram_service

NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def _agency(db, name, *, status="active", expires_in_days=None, warned_at=None):
    exp = NOW + timedelta(days=expires_in_days) if expires_in_days is not None else None
    a = Agency(
        name=name,
        status=status,
        timezone="Asia/Tashkent",
        default_currency="USD",
        subscription_expires_at=exp,
        subscription_warned_at=warned_at,
    )
    db.add(a)
    db.flush()
    return a


def _owner(db, agency_id, telegram_id):
    u = User(telegram_id=telegram_id, role="agency_admin", agency_id=agency_id,
             is_owner=True, is_active=True)
    db.add(u)
    db.flush()
    return u


def _patch_bot(monkeypatch):
    """Сделать вид, что бот настроен, и перехватывать отправленные сообщения."""
    sent = []
    monkeypatch.setattr(telegram_service, "is_configured", lambda: True)
    monkeypatch.setattr(telegram_service, "send_message",
                        lambda chat_id, text: sent.append((chat_id, text)) or True)
    monkeypatch.setattr(settings, "subscription_warn_days", 3)
    return sent


def test_warns_only_expiring_active_with_owner(db, monkeypatch):
    sent = _patch_bot(monkeypatch)

    soon = _agency(db, "Истекает скоро", expires_in_days=2)   # ← должен предупредить
    _owner(db, soon.id, 111)
    far = _agency(db, "Ещё долго", expires_in_days=30)        # вне окна
    _owner(db, far.id, 222)
    expired = _agency(db, "Уже истекла", expires_in_days=-1)  # уже истекла
    _owner(db, expired.id, 333)
    frozen = _agency(db, "Заморожена", status="frozen", expires_in_days=1)  # не активна
    _owner(db, frozen.id, 444)
    db.commit()

    count = scheduler.run_subscription_warnings(db, now=NOW)

    assert count == 1, sent
    assert len(sent) == 1 and sent[0][0] == 111
    # Метка предупреждения проставлена только у «истекающего» агентства.
    db.refresh(soon)
    assert soon.subscription_warned_at is not None


def test_throttle_prevents_duplicate(db, monkeypatch):
    sent = _patch_bot(monkeypatch)
    a = _agency(db, "Истекает", expires_in_days=2)
    _owner(db, a.id, 555)
    db.commit()

    assert scheduler.run_subscription_warnings(db, now=NOW) == 1
    # Через час повторная проверка не должна слать снова (троттлинг ~сутки).
    assert scheduler.run_subscription_warnings(db, now=NOW + timedelta(hours=1)) == 0
    assert len(sent) == 1


def test_no_owner_still_marks_but_does_not_send(db, monkeypatch):
    sent = _patch_bot(monkeypatch)
    a = _agency(db, "Без владельца", expires_in_days=1)  # админа нет
    db.commit()

    count = scheduler.run_subscription_warnings(db, now=NOW)
    assert count == 0 and sent == []
    db.refresh(a)
    # Метку всё равно ставим, чтобы не проверять его снова каждые 6 часов.
    assert a.subscription_warned_at is not None


def test_disabled_when_warn_days_zero(db, monkeypatch):
    sent = _patch_bot(monkeypatch)
    monkeypatch.setattr(settings, "subscription_warn_days", 0)
    a = _agency(db, "Истекает", expires_in_days=2)
    _owner(db, a.id, 777)
    db.commit()

    assert scheduler.run_subscription_warnings(db, now=NOW) == 0
    assert sent == []
