"""
Тесты личных агентств владельца платформы и acting-контекста (вход суперадмина
в своё агентство как главного админа). Уровень сервисов, SQLite в памяти.
"""
from types import SimpleNamespace

import pytest

from app.core import dependencies
from app.core.errors import AppError
from app.db.models.agency import Agency
from app.repositories import agency_repo, user_repo
from app.services import agency_service, auth_service


def _superadmin(db, telegram_id=500):
    u = user_repo.create(db, telegram_id=telegram_id, role="superadmin", agency_id=None)
    db.commit()
    return u


def test_create_personal_agency_sets_owner(db):
    owner = _superadmin(db)
    agency = agency_service.create_personal_agency(db, "Моё агентство", owner)
    assert agency.owner_telegram_id == owner.telegram_id
    assert agency.name == "Моё агентство"
    # Появилось в списке «моих».
    mine = agency_service.list_personal_agencies(db, owner.telegram_id)
    assert [a.id for a in mine] == [agency.id]


def test_platform_list_excludes_personal(db):
    owner = _superadmin(db)
    personal = agency_service.create_personal_agency(db, "Личное", owner)
    client = Agency(name="Клиент", status="active", timezone="Asia/Tashkent",
                    default_currency="USD")
    db.add(client)
    db.commit()

    client_ids = [a.id for a in agency_repo.get_clients(db)]
    owner_ids = [a.id for a in agency_repo.get_by_owner(db, owner.telegram_id)]
    # В платформенном списке — только клиент, личное — только в «моих».
    assert client.id in client_ids and personal.id not in client_ids
    assert owner_ids == [personal.id]


def test_create_personal_agency_requires_name(db):
    owner = _superadmin(db)
    with pytest.raises(AppError) as exc:
        agency_service.create_personal_agency(db, "   ", owner)
    assert exc.value.key == "personal_agency_name_required"


def test_enter_builds_acting_session(db):
    owner = _superadmin(db)
    agency = agency_service.create_personal_agency(db, "Личное", owner)

    resp = auth_service.build_auth_response(db, owner, act_as_agency_id=agency.id)
    user = resp["user"]
    assert user["role"] == "agency_admin"
    assert user["is_owner"] is True
    assert user["agency_id"] == agency.id
    assert user["acting_as_agency_id"] == agency.id
    assert user["real_role"] == "superadmin"
    # Личное агентство подписке не подчиняется.
    assert resp["subscription_active"] is True
    # В токене проставлен claim act_as_agency_id.
    from app.core import security
    payload = security.decode_access_token(resp["access_token"])
    assert payload["act_as_agency_id"] == agency.id
    assert payload["role"] == "agency_admin"


def test_cannot_act_in_foreign_agency(db):
    owner = _superadmin(db)
    # Обычное клиентское агентство (owner_telegram_id = NULL).
    client = Agency(name="Клиент", status="active", timezone="Asia/Tashkent",
                    default_currency="USD")
    db.add(client)
    db.commit()

    resp = auth_service.build_auth_response(db, owner, act_as_agency_id=client.id)
    # Acting НЕ применился — это обычная сессия суперадмина.
    assert resp["user"].role == "superadmin"


def test_personal_agency_bypasses_subscription(db):
    owner = _superadmin(db)
    agency = agency_service.create_personal_agency(db, "Личное", owner)
    # Даже если статус заморожен — личное агентство остаётся доступным.
    agency.status = "frozen"
    db.commit()

    fake = SimpleNamespace(agency_id=agency.id)
    # Не должно бросить subscription_suspended.
    dependencies._ensure_subscription_active(db, fake)


def test_client_agency_subscription_still_enforced(db):
    client = Agency(name="Клиент", status="frozen", timezone="Asia/Tashkent",
                    default_currency="USD")
    db.add(client)
    db.commit()
    fake = SimpleNamespace(agency_id=client.id)
    with pytest.raises(AppError) as exc:
        dependencies._ensure_subscription_active(db, fake)
    assert exc.value.key == "subscription_suspended"
