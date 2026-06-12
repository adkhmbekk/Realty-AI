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


# ─── Регрессия: вступление сотрудника по коду после 403 на входе ────────────

_TEST_BOT_TOKEN = "123456:TEST_BOT_TOKEN"


def _sign_init_data(telegram_id: int, *, username=None, first_name="New",
                    auth_date=None) -> str:
    """Собрать и подписать initData ровно так, как это делает Telegram."""
    import hashlib
    import hmac
    import json
    import time
    from urllib.parse import urlencode

    user_json = json.dumps(
        {"id": telegram_id, "username": username, "first_name": first_name},
        separators=(",", ":"),
    )
    fields = {"auth_date": str(auth_date or int(time.time())), "user": user_json}
    data_check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret_key = hmac.new(b"WebAppData", _TEST_BOT_TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    return urlencode(fields)


def test_new_employee_can_join_personal_agency_after_login_403(db, monkeypatch):
    """
    Корневой баг: фронтенд сначала шлёт initData на /auth/telegram (незнакомец →
    403), затем ТОТ ЖЕ initData на /invites/redeem. Анти-повтор не должен «гасить»
    подпись на входе, иначе вступление по коду ложно считается повтором и новый
    сотрудник не может войти в (личное) агентство владельца платформы.
    """
    from app.config import settings
    from app.core import security
    from app.repositories import user_repo
    from app.schemas.invite import InviteCreate
    from app.services import invite_service

    monkeypatch.setattr(settings, "bot_token", _TEST_BOT_TOKEN, raising=False)
    # Чистим хранилище повторов между тестами (оно в памяти процесса).
    security._seen_init_data.clear()

    # 1. Владелец платформы создаёт личное агентство и приглашение (acting).
    owner = _superadmin(db, telegram_id=196135282)
    agency = agency_service.create_personal_agency(db, "Navruz Real Estate", owner)
    invite = invite_service.create_invite(
        db, agency.id, created_by=owner.id,
        payload=InviteCreate(role="agent", expires_in_days=30), is_owner=True,
    )

    # 2. Новый сотрудник открывает ссылку: тот же initData используется дважды.
    init_data = _sign_init_data(telegram_id=777001, username="employee")

    # 2a. Сначала вход — незнакомца ещё нет в базе → 403 (но initData НЕ сгорает).
    with pytest.raises(AppError) as exc:
        auth_service.login_with_init_data(db, init_data)
    assert exc.value.key == "not_in_agency"

    # 2b. Затем вступление по коду с ТЕМ ЖЕ initData — должно пройти.
    resp = invite_service.redeem_invite(db, init_data, invite.code)
    assert resp["user"].role == "agent"
    assert resp["user"].agency_id == agency.id

    # Сотрудник реально привязан к агентству владельца.
    joined = user_repo.get_by_telegram_id(db, 777001)
    assert joined is not None and joined.agency_id == agency.id


def test_login_still_blocks_replayed_init_data(db, monkeypatch):
    """Защита от повторов сохраняется: второй вход тем же initData отклоняется."""
    from app.config import settings
    from app.core import security

    monkeypatch.setattr(settings, "bot_token", _TEST_BOT_TOKEN, raising=False)
    security._seen_init_data.clear()

    # Существующий сотрудник агентства.
    client = Agency(name="Клиент", status="active", timezone="Asia/Tashkent",
                    default_currency="USD")
    db.add(client)
    db.commit()
    user_repo.create(db, telegram_id=888002, role="agent", agency_id=client.id)
    db.commit()

    init_data = _sign_init_data(telegram_id=888002, username="member")

    # Первый вход — успешно (подпись «гасится»).
    resp = auth_service.login_with_init_data(db, init_data)
    assert resp["user"].telegram_id == 888002

    # Повтор того же initData — отклонён.
    with pytest.raises(AppError) as exc:
        auth_service.login_with_init_data(db, init_data)
    assert exc.value.key == "init_data_replayed"
