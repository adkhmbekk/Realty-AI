"""Создание агентства «по ссылке» (черновик) + активация.

Владелец платформы создаёт агентство одним названием (без Telegram ID), получает
ссылку активации; кто откроет её в Telegram — становится главным админом, и
подписка запускается с этого момента. Уровень сервисов, SQLite в памяти.
"""
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
    invite_service.redeem_invite(db, init_data, invite.code)

    # Открывший ссылку стал главным админом этого агентства.
    u = user_repo.get_by_telegram_id(db, 900100)
    assert u is not None
    assert u.role == "agency_admin" and u.is_owner is True and u.agency_id == agency.id
    # Агентство активировано, подписка запущена, pending_days сброшен.
    db.refresh(agency)
    assert agency.status == "active"
    assert agency.subscription_expires_at is not None
    assert agency.pending_days is None


def test_claim_blocked_if_already_in_agency(db, monkeypatch):
    from app.config import settings
    from app.core import security

    monkeypatch.setattr(settings, "bot_token", _TEST_BOT_TOKEN, raising=False)
    security._seen_init_data.clear()

    owner = _superadmin(db)
    agency, invite = _draft(db, owner)
    # Человек уже состоит в другом (реальном) агентстве — активировать не должен.
    from app.db.models.agency import Agency

    other = Agency(name="Другое", status="active", timezone="Asia/Tashkent", default_currency="USD")
    db.add(other)
    db.commit()
    user_repo.create(db, telegram_id=900200, role="agent", agency_id=other.id)
    db.commit()

    init_data = _sign_init_data(telegram_id=900200, username="busy")
    with pytest.raises(AppError) as exc:
        invite_service.redeem_invite(db, init_data, invite.code)
    assert exc.value.key == "already_in_agency"
    # Агентство осталось черновиком.
    db.refresh(agency)
    assert agency.status == "pending"


def test_reissue_replaces_link(db):
    owner = _superadmin(db)
    agency, invite = _draft(db, owner)
    new = agency_service.reissue_activation(db, agency.id, actor=owner)
    assert new.code != invite.code
    active = invite_service.get_active_owner_invite(db, agency.id)
    assert active is not None and active.code == new.code


def test_revoke_removes_link(db):
    owner = _superadmin(db)
    agency, _invite = _draft(db, owner)
    agency_service.revoke_activation(db, agency.id, actor=owner)
    assert invite_service.get_active_owner_invite(db, agency.id) is None


def test_activation_actions_blocked_when_active(db):
    # У активного агентства ссылки активации быть не должно (нечего активировать).
    owner = _superadmin(db)
    agency, invite = _draft(db, owner)
    agency.status = "active"
    db.commit()
    with pytest.raises(AppError) as exc:
        agency_service.reissue_activation(db, agency.id, actor=owner)
    assert exc.value.key == "agency_already_active"
