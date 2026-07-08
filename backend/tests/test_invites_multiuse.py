"""
Многоразовые приглашения (2026-07): по одному коду может вступить несколько
человек — в пределах лимита max_uses и до истечения срока. Проверяем счётчик
использований, исчерпание лимита и защиту от «занятия» при отказе.

Уровень сервисов, SQLite в памяти. Подпись initData и помощники переиспользуем
из соседних тестов.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.errors import AppError
from app.db.models.agency import Agency
from app.repositories import invite_repo, user_repo
from app.schemas.invite import InviteCreate
from app.services import invite_service

from tests.test_personal_agencies import _TEST_BOT_TOKEN, _sign_init_data


def _agency_with_admin(db):
    agency = Agency(
        name="Клиент", status="active", timezone="Asia/Tashkent",
        default_currency="USD",
    )
    db.add(agency)
    db.commit()
    admin = user_repo.create(
        db, telegram_id=700000, role="agency_admin", agency_id=agency.id,
        is_owner=True,
    )
    db.commit()
    return agency, admin


def _prep(monkeypatch):
    from app.config import settings
    from app.core import security

    monkeypatch.setattr(settings, "bot_token", _TEST_BOT_TOKEN, raising=False)
    security._seen_init_data.clear()


def test_multiuse_invite_allows_several_joins(db, monkeypatch):
    _prep(monkeypatch)
    agency, admin = _agency_with_admin(db)
    inv = invite_service.create_invite(
        db, agency.id, created_by=admin.id,
        payload=InviteCreate(role="agent", expires_in_days=7, max_uses=3),
        is_owner=True,
    )
    assert inv.max_uses == 3 and inv.used_count == 0 and inv.status == "active"

    # Три разных человека вступают по одному коду.
    for i, tg in enumerate((701001, 701002, 701003), start=1):
        invite_service.redeem_invite(db, _sign_init_data(telegram_id=tg), inv.code)
        u = user_repo.get_by_telegram_id(db, tg)
        assert u is not None and u.agency_id == agency.id and u.role == "agent"
        # Счётчик использований растёт.
        row = invite_repo.get_by_code(db, inv.code)
        assert row.used_count == i

    # Лимит исчерпан — четвёртый уже не может.
    row = invite_repo.get_by_code(db, inv.code)
    assert invite_service._status_of(row) == "used"
    with pytest.raises(AppError) as exc:
        invite_service.redeem_invite(db, _sign_init_data(telegram_id=701004), inv.code)
    assert exc.value.key == "invite_already_used"
    # Четвёртый пользователь НЕ привязан к агентству.
    assert user_repo.get_by_telegram_id(db, 701004) is None
    # Счётчик не превысил лимит.
    assert invite_repo.get_by_code(db, inv.code).used_count == 3


def test_single_use_is_default(db, monkeypatch):
    _prep(monkeypatch)
    agency, admin = _agency_with_admin(db)
    inv = invite_service.create_invite(
        db, agency.id, created_by=admin.id,
        payload=InviteCreate(role="agent"),  # max_uses по умолчанию = 1
        is_owner=True,
    )
    assert inv.max_uses == 1
    invite_service.redeem_invite(db, _sign_init_data(telegram_id=702001), inv.code)
    with pytest.raises(AppError) as exc:
        invite_service.redeem_invite(db, _sign_init_data(telegram_id=702002), inv.code)
    assert exc.value.key == "invite_already_used"


def test_rejected_join_does_not_consume_use(db, monkeypatch):
    _prep(monkeypatch)
    agency, admin = _agency_with_admin(db)
    inv = invite_service.create_invite(
        db, agency.id, created_by=admin.id,
        payload=InviteCreate(role="agent", max_uses=2),
        is_owner=True,
    )
    # Человек уже состоит в ДРУГОМ агентстве — вступление отклоняется.
    other = Agency(name="Другое", status="active", timezone="Asia/Tashkent",
                   default_currency="USD")
    db.add(other)
    db.commit()
    user_repo.create(db, telegram_id=703001, role="agent", agency_id=other.id)
    db.commit()
    with pytest.raises(AppError) as exc:
        invite_service.redeem_invite(db, _sign_init_data(telegram_id=703001), inv.code)
    assert exc.value.key == "already_in_agency"
    # Лимит НЕ израсходован (отказ не занял использование).
    assert invite_repo.get_by_code(db, inv.code).used_count == 0


def test_expired_multiuse_invite_blocked(db, monkeypatch):
    _prep(monkeypatch)
    agency, admin = _agency_with_admin(db)
    inv = invite_service.create_invite(
        db, agency.id, created_by=admin.id,
        payload=InviteCreate(role="agent", max_uses=5),
        is_owner=True,
    )
    # Просрочим приглашение вручную.
    row = invite_repo.get_by_code(db, inv.code)
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    with pytest.raises(AppError) as exc:
        invite_service.redeem_invite(db, _sign_init_data(telegram_id=704001), inv.code)
    assert exc.value.key == "invite_expired"


def test_uses_range_validation():
    with pytest.raises(Exception):
        InviteCreate(role="agent", max_uses=0)
    with pytest.raises(Exception):
        InviteCreate(role="agent", max_uses=101)
