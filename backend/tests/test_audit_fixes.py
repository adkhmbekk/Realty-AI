"""
Тесты исправлений по аудиту:
  1.1 — удаление агентства с фотографиями больше не падает;
  1.2 — нельзя «украсть» сотрудника другого агентства при создании;
  1.3 — просроченные агентства переводятся в статус 'expired';
  1.5 — сотрудника можно исключить из агентства (agency_id → NULL);
  1.4 — refresh-токен (валиден только как refresh; access им не считается);
  2.5 — IP клиента берётся справа из X-Forwarded-For (нельзя подделать слева).
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.core import security
from app.core.errors import AppError
from app.db.models.agency import Agency
from app.repositories import apartment_photo_repo, user_repo
from app.schemas.agency import AgencyCreate
from app.schemas.apartment import ApartmentCreate
from app.services import agency_service, apartment_service, member_service, scheduler


def _agency(db, name="A", status="active"):
    a = Agency(name=name, status=status, timezone="Asia/Tashkent", default_currency="USD")
    db.add(a)
    db.flush()
    return a


# ── 1.1 удаление агентства с фото ────────────────────────────────────────
def test_delete_agency_with_photos_does_not_crash(db):
    a = _agency(db)
    admin = user_repo.create(db, telegram_id=1, role="agency_admin", agency_id=a.id, is_owner=True)
    apt = apartment_service.create_apartment(
        db, a.id, created_by=admin.id, payload=ApartmentCreate(name="Тест", price=1000)
    )
    apartment_photo_repo.create(db, a.id, apt.id, "key_abc", "image/jpeg", 0)
    db.commit()

    # Раньше падало с FOREIGN KEY constraint failed. Теперь — чисто.
    agency_service.delete_agency(db, a.id)

    from app.repositories import agency_repo, apartment_repo
    assert agency_repo.get_by_id(db, a.id) is None
    items, total = apartment_repo.search(db, a.id, status=None)
    assert total == 0
    assert apartment_photo_repo.list_keys_for_agency(db, a.id) == []


# ── 1.2 защита от кражи сотрудника ───────────────────────────────────────
def test_create_agency_rejects_user_from_another_agency(db):
    a = _agency(db, "Старое")
    user_repo.create(db, telegram_id=777, role="agency_admin", agency_id=a.id, is_owner=True)
    db.commit()

    with pytest.raises(AppError) as ei:
        agency_service.create_agency_with_admin(
            db, AgencyCreate(name="Новое", admin_telegram_id=777, subscription_days=30)
        )
    assert ei.value.status_code == 400
    # Пользователь остался в своём агентстве.
    u = user_repo.get_by_telegram_id(db, 777)
    assert u.agency_id == a.id


# ── 1.3 истечение подписки ───────────────────────────────────────────────
def test_expire_due_subscriptions(db):
    # ПОДПИСКА ОТКЛЮЧЕНА (тарифы, 2026-07): функция — стаб, статусы не трогает.
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    overdue = _agency(db, "Просрочена", status="active")
    overdue.subscription_expires_at = now - timedelta(days=1)
    db.commit()

    assert scheduler.expire_due_subscriptions(db, now=now) == 0
    db.refresh(overdue)
    assert overdue.status == "active"  # статус не меняется — гейтинг убран


# ── 1.5 исключение сотрудника ────────────────────────────────────────────
def test_remove_member_unbinds_from_agency(db):
    a = _agency(db)
    owner = user_repo.create(db, telegram_id=1, role="agency_admin", agency_id=a.id, is_owner=True)
    agent = user_repo.create(db, telegram_id=2, role="agent", agency_id=a.id)
    db.commit()

    member_service.remove_member(db, a.id, owner, agent.id)
    db.refresh(agent)
    assert agent.agency_id is None and agent.is_active is False


def test_remove_member_requires_owner(db):
    a = _agency(db)
    admin = user_repo.create(db, telegram_id=1, role="agency_admin", agency_id=a.id, is_owner=False)
    agent = user_repo.create(db, telegram_id=2, role="agent", agency_id=a.id)
    db.commit()
    with pytest.raises(AppError):
        member_service.remove_member(db, a.id, admin, agent.id)


def test_transfer_ownership_syncs_membership(db):
    """HI-1 (аудит 2026-07-11): передача владения должна обновлять agency_memberships
    (источник правды), иначе владельческие операции платформы читают устаревшего владельца."""
    from app.repositories import agency_membership_repo

    a = _agency(db)
    owner = user_repo.create(db, telegram_id=1, role="agency_admin", agency_id=a.id, is_owner=True)
    agent = user_repo.create(db, telegram_id=2, role="agent", agency_id=a.id)
    agency_membership_repo.create(db, user_id=owner.id, agency_id=a.id, role="agency_admin", is_owner=True)
    agency_membership_repo.create(db, user_id=agent.id, agency_id=a.id, role="agent", is_owner=False)
    db.commit()

    member_service.transfer_ownership(db, a.id, owner, agent.id)

    # Членства отражают нового владельца, а не старого.
    assert agency_membership_repo.get(db, agent.id, a.id).is_owner is True
    assert agency_membership_repo.get(db, owner.id, a.id).is_owner is False


def test_remove_member_drops_membership(db):
    """HI-1: исключение сотрудника убирает и строку членства (не только User.agency_id)."""
    from app.repositories import agency_membership_repo

    a = _agency(db)
    owner = user_repo.create(db, telegram_id=1, role="agency_admin", agency_id=a.id, is_owner=True)
    agent = user_repo.create(db, telegram_id=2, role="agent", agency_id=a.id)
    agency_membership_repo.create(db, user_id=agent.id, agency_id=a.id, role="agent", is_owner=False)
    db.commit()

    member_service.remove_member(db, a.id, owner, agent.id)
    assert agency_membership_repo.get(db, agent.id, a.id) is None


# ── 1.4 refresh-токен ────────────────────────────────────────────────────
def test_refresh_token_roundtrip():
    refresh = security.create_refresh_token({"user_id": 42})
    payload = security.decode_refresh_token(refresh)
    assert payload is not None and payload["user_id"] == 42
    # Access-токен НЕ принимается как refresh.
    access = security.create_access_token({"user_id": 42})
    assert security.decode_refresh_token(access) is None


# ── 2.5 определение IP за прокси ──────────────────────────────────────────
def test_client_ip_takes_rightmost_trusted(monkeypatch):
    from app.config import settings
    from app.core import ratelimit

    class _Req:
        def __init__(self, xff):
            self.headers = {"x-forwarded-for": xff} if xff else {}
            self.client = type("C", (), {"host": "10.0.0.1"})()

    monkeypatch.setattr(settings, "trusted_proxy_count", 1)
    # Клиент подделал левую часть; берём правый (выставленный нашим прокси).
    assert ratelimit._client_ip(_Req("1.1.1.1, 2.2.2.2, 9.9.9.9")) == "9.9.9.9"
    # Один реальный клиент.
    assert ratelimit._client_ip(_Req("8.8.8.8")) == "8.8.8.8"
    # Нет заголовка — адрес соединения.
    assert ratelimit._client_ip(_Req("")) == "10.0.0.1"


# ── QW23: продление подписки требует явную сумму ─────────────────────────
def test_extend_requires_explicit_amount(db):
    # Без суммы — отказ (честный учёт выручки).
    a1 = _agency(db, "A1")
    db.commit()
    with pytest.raises(AppError) as ei:
        agency_service.update_subscription(db, a1.id, "extend", days=30)
    assert ei.value.status_code == 400

    # Ненулевая сумма без валюты — отказ.
    a2 = _agency(db, "A2")
    db.commit()
    with pytest.raises(AppError):
        agency_service.update_subscription(db, a2.id, "extend", days=30, amount=50)

    # Сумма 0 (бесплатное продление) — допустимо.
    a3 = _agency(db, "A3")
    db.commit()
    agency_service.update_subscription(db, a3.id, "extend", days=30, amount=0)

    # Ненулевая сумма с валютой — ок.
    a4 = _agency(db, "A4")
    db.commit()
    agency_service.update_subscription(db, a4.id, "extend", days=30, amount=50, currency="usd")
