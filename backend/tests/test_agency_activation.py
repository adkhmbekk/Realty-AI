"""Создание агентства «по ссылке» (черновик) + активация.

Владелец платформы создаёт агентство одним названием (без Telegram ID), получает
ссылку активации; кто откроет её в Telegram — становится главным админом, и
подписка запускается с этого момента. Уровень сервисов, SQLite в памяти.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.errors import AppError
from app.repositories import user_repo
from app.schemas.agency import AgencyDraftCreate
from app.services import agency_service, invite_service

# Переиспользуем подпись initData и помощников из соседнего теста.
from tests.test_personal_agencies import _TEST_BOT_TOKEN, _sign_init_data, _superadmin


def _draft(db, owner, name="Клиент", days=30):
    return agency_service.create_agency_draft(
        db, AgencyDraftCreate(name=name, subscription_days=days), actor=owner
    )


def test_draft_is_pending_with_owner_invite(db):
    owner = _superadmin(db)
    agency, invite = _draft(db, owner)
    assert agency.status == "pending"
    assert agency.subscription_expires_at is None
    assert agency.pending_days == 30
    assert invite.role == "owner"
    active = invite_service.get_active_owner_invite(db, agency.id)
    assert active is not None and active.code == invite.code


def test_claim_activates_agency_and_makes_owner(db, monkeypatch):
    from app.config import settings
    from app.core import security

    monkeypatch.setattr(settings, "bot_token", _TEST_BOT_TOKEN, raising=False)
    security._seen_init_data.clear()

    owner = _superadmin(db)
    agency, invite = _draft(db, owner, days=15)

    init_data = _sign_init_data(telegram_id=900100, username="boss")
    before = datetime.now(timezone.utc)
    invite_service.redeem_invite(db, init_data, invite.code)

    # Открывший ссылку стал главным админом этого агентства.
    u = user_repo.get_by_telegram_id(db, 900100)
    assert u is not None
    assert u.role == "agency_admin" and u.is_owner is True and u.agency_id == agency.id
    # Агентство активировано, подписка запущена на pending_days (15) дней, сброс.
    db.refresh(agency)
    assert agency.status == "active"
    assert agency.pending_days is None
    exp = agency.subscription_expires_at
    assert exp is not None
    if exp.tzinfo is None:  # SQLite отдаёт наивные даты
        exp = exp.replace(tzinfo=timezone.utc)
    delta = exp - before
    assert timedelta(days=15) - timedelta(minutes=2) <= delta <= timedelta(days=15) + timedelta(minutes=2)


def test_claim_second_agency_allowed_multiagency(db, monkeypatch):
    """Мультиагентство (2026-07): человек из агентства A может активировать
    (стать владельцем) ВТОРОГО агентства B по owner-приглашению. Раньше это
    блокировалось (один человек — одно агентство); теперь разрешено. Домашнее
    агентство при этом не перезаписывается."""
    from app.config import settings
    from app.core import security
    from app.db.models.agency import Agency
    from app.repositories import agency_membership_repo

    monkeypatch.setattr(settings, "bot_token", _TEST_BOT_TOKEN, raising=False)
    security._seen_init_data.clear()

    owner = _superadmin(db)
    agency, invite = _draft(db, owner)
    # Человек уже состоит в другом (реальном) агентстве A + членство в A.
    other = Agency(name="Другое", status="active", timezone="Asia/Tashkent", default_currency="USD")
    db.add(other)
    db.commit()
    u = user_repo.create(db, telegram_id=900200, role="agent", agency_id=other.id)
    agency_membership_repo.create(
        db, user_id=u.id, agency_id=other.id, role="agent", is_owner=False,
    )
    db.commit()

    init_data = _sign_init_data(telegram_id=900200, username="busy")
    invite_service.redeem_invite(db, init_data, invite.code)

    # Агентство B активировалось.
    db.refresh(agency)
    assert agency.status == "active"
    # Домашнее агентство (A) не изменилось; в B — членство владельца.
    u2 = user_repo.get_by_telegram_id(db, 900200)
    assert u2.agency_id == other.id
    m_b = agency_membership_repo.get(db, u2.id, agency.id)
    assert m_b is not None and m_b.is_owner is True and m_b.role == "agency_admin"


def test_reissue_replaces_link(db, monkeypatch):
    from app.config import settings
    from app.core import security

    monkeypatch.setattr(settings, "bot_token", _TEST_BOT_TOKEN, raising=False)
    security._seen_init_data.clear()

    owner = _superadmin(db)
    agency, invite = _draft(db, owner)
    new = agency_service.reissue_activation(db, agency.id, actor=owner)
    assert new.code != invite.code
    active = invite_service.get_active_owner_invite(db, agency.id)
    assert active is not None and active.code == new.code
    # Старая ссылка больше НЕ действует (одноразовый отзыв).
    with pytest.raises(AppError) as exc:
        invite_service.redeem_invite(db, _sign_init_data(telegram_id=900300, username="old"), invite.code)
    assert exc.value.key == "invite_not_found"


def test_revoke_removes_link(db, monkeypatch):
    from app.config import settings
    from app.core import security

    monkeypatch.setattr(settings, "bot_token", _TEST_BOT_TOKEN, raising=False)
    security._seen_init_data.clear()

    owner = _superadmin(db)
    agency, invite = _draft(db, owner)
    agency_service.revoke_activation(db, agency.id, actor=owner)
    assert invite_service.get_active_owner_invite(db, agency.id) is None
    # Отозванный код активировать нельзя.
    with pytest.raises(AppError) as exc:
        invite_service.redeem_invite(db, _sign_init_data(telegram_id=900400, username="rev"), invite.code)
    assert exc.value.key == "invite_not_found"


def test_activation_actions_blocked_when_active(db):
    # У активного агентства ссылки активации быть не должно (нечего активировать).
    owner = _superadmin(db)
    agency, invite = _draft(db, owner)
    agency.status = "active"
    db.commit()
    with pytest.raises(AppError) as exc:
        agency_service.reissue_activation(db, agency.id, actor=owner)
    assert exc.value.key == "agency_already_active"
