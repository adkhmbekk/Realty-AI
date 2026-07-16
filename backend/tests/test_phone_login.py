"""Вход по номеру телефона (SMS-код): request/verify, троттлинг, перебор, резолв.

SMS наружу не шлём: sms_service подменяется заглушкой (записываем отправленное).
"""
from datetime import timedelta

import pytest

from app.core.errors import AppError
from app.repositories import phone_otp_repo, user_repo
from app.services import phone_login_service, sms_service


@pytest.fixture()
def sent(monkeypatch):
    """Включает «настроенный» SMS-шлюз и собирает отправленные сообщения."""
    box: list = []
    monkeypatch.setattr(sms_service, "is_configured", lambda: True)
    monkeypatch.setattr(
        sms_service, "send_sms", lambda phone, text: box.append((phone, text)) or True
    )
    return box


def _code_for(db, phone: str) -> str:
    row = phone_otp_repo.latest_pending(db, phone)
    assert row is not None
    return row.code


def test_request_not_configured_returns_503(db, monkeypatch):
    monkeypatch.setattr(sms_service, "is_configured", lambda: False)
    with pytest.raises(AppError) as exc:
        phone_login_service.request_code(db, "+998901234567")
    assert exc.value.status_code == 503


def test_request_sends_code_and_commits(db, sent):
    out = phone_login_service.request_code(db, "+998 90 123 45 67")
    assert out["expires_in"] == phone_login_service.CODE_TTL_SECONDS
    # SMS ушло на нормализованный номер и содержит код.
    assert sent and sent[0][0] == "+998901234567"
    code = _code_for(db, "+998901234567")
    assert len(code) == 6 and code.isdigit() and code in sent[0][1]
    # РЕГРЕССИЯ (урок tg-login): код обязан пережить rollback — commit был.
    db.rollback()
    assert phone_otp_repo.latest_pending(db, "+998901234567") is not None


def test_request_cooldown_and_replaces_old_code(db, sent):
    phone_login_service.request_code(db, "+998901234567")
    # Сразу второй запрос — троттлинг.
    with pytest.raises(AppError) as exc:
        phone_login_service.request_code(db, "+998901234567")
    assert exc.value.status_code == 429
    # «Состарим» первый код за пределы кулдауна → новый выдаётся, старый гаснет.
    old = phone_otp_repo.latest_pending(db, "+998901234567")
    old.created_at = old.created_at - timedelta(seconds=90)
    db.commit()
    old_code = old.code
    phone_login_service.request_code(db, "+998901234567")
    fresh = phone_otp_repo.latest_pending(db, "+998901234567")
    assert fresh.id != old.id
    db.refresh(old)
    assert old.status == "expired"
    # Старый код больше не принимается (активен только новый).
    if old_code != fresh.code:
        with pytest.raises(AppError):
            phone_login_service.verify_code(db, "+998901234567", old_code)


def test_verify_creates_new_personal_account(db, sent):
    phone_login_service.request_code(db, "+998901234567")
    resp = phone_login_service.verify_code(db, "998901234567", _code_for(db, "+998901234567"))
    u = resp["user"]
    assert u.role == "user" and u.agency_id is None
    assert u.phone == "+998901234567" and u.phone_verified is True
    assert u.telegram_id is None
    assert resp.get("refresh_token")
    # Код одноразовый: повторный verify тем же кодом не проходит.
    with pytest.raises(AppError):
        phone_login_service.verify_code(db, "+998901234567", "000000")


def test_verify_logs_into_existing_account_by_phone(db, sent):
    existing = user_repo.create(db, telegram_id=777, role="user")
    existing.phone = "+998907654321"
    db.commit()
    phone_login_service.request_code(db, "+998907654321")
    resp = phone_login_service.verify_code(db, "+998907654321", _code_for(db, "+998907654321"))
    # Вошли в СУЩЕСТВУЮЩИЙ аккаунт (телефон — якорь), а не создали новый.
    assert resp["user"].id == existing.id


def test_verify_wrong_code_attempts_then_lockout(db, sent):
    phone_login_service.request_code(db, "+998901234567")
    real = _code_for(db, "+998901234567")
    wrong = "000000" if real != "000000" else "111111"
    for _ in range(phone_login_service.MAX_ATTEMPTS):
        with pytest.raises(AppError) as exc:
            phone_login_service.verify_code(db, "+998901234567", wrong)
        assert exc.value.status_code == 401
    # Лимит исчерпан — даже ПРАВИЛЬНЫЙ код больше не принимается (код погашен).
    with pytest.raises(AppError):
        phone_login_service.verify_code(db, "+998901234567", real)


def test_verify_expired_code(db, sent):
    phone_login_service.request_code(db, "+998901234567")
    row = phone_otp_repo.latest_pending(db, "+998901234567")
    row.expires_at = row.expires_at - timedelta(seconds=phone_login_service.CODE_TTL_SECONDS + 60)
    db.commit()
    with pytest.raises(AppError) as exc:
        phone_login_service.verify_code(db, "+998901234567", row.code)
    assert exc.value.status_code == 401


def test_bad_phone_rejected(db, sent):
    with pytest.raises(AppError) as exc:
        phone_login_service.request_code(db, "12345")
    assert exc.value.status_code == 400
