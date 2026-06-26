"""
Мгновенный отзыв доступа через «версию сессии» (session_epoch).

Бамп session_epoch обесценивает все ранее выданные пропуска (access+refresh):
- отключение сотрудника гасит его сессии сразу (и они не «воскресают»);
- исключение — тоже;
- «выйти со всех устройств» завершает сеансы, НЕ отключая сотрудника.
Уровень сервисов, SQLite в памяти (фикстура db из conftest).
"""
import pytest

from app.core.errors import AppError
from app.db.models.agency import Agency
from app.repositories import user_repo
from app.schemas.team import MemberUpdate
from app.services import auth_service, member_service


def _agency_owner_agent(db):
    agency = Agency(name="A", status="active", timezone="Asia/Tashkent", default_currency="USD")
    db.add(agency)
    db.flush()
    owner = user_repo.create(db, telegram_id=1, role="agency_admin", agency_id=agency.id, is_owner=True)
    agent = user_repo.create(db, telegram_id=2, role="agent", agency_id=agency.id)
    db.commit()
    return agency, owner, agent


def test_refresh_token_carries_and_checks_epoch(db):
    agency, owner, agent = _agency_owner_agent(db)
    resp = auth_service.build_auth_response(db, agent)
    refresh = resp["refresh_token"]
    # Пока эпоха не менялась — продление сессии работает.
    assert auth_service.refresh_session(db, refresh)["user"].id == agent.id
    # Бамп эпохи — старый refresh-пропуск становится недействительным.
    agent.session_epoch = (agent.session_epoch or 0) + 1
    db.commit()
    with pytest.raises(AppError) as exc:
        auth_service.refresh_session(db, refresh)
    assert exc.value.key == "session_revoked"


def test_disable_member_bumps_epoch(db):
    agency, owner, agent = _agency_owner_agent(db)
    resp = auth_service.build_auth_response(db, agent)
    before = agent.session_epoch or 0
    member_service.update_member(db, agency.id, owner, agent.id, MemberUpdate(is_active=False))
    db.refresh(agent)
    assert (agent.session_epoch or 0) == before + 1
    # Старый refresh больше не действует (отключён + сменилась эпоха).
    with pytest.raises(AppError):
        auth_service.refresh_session(db, resp["refresh_token"])


def test_remove_member_bumps_epoch(db):
    agency, owner, agent = _agency_owner_agent(db)
    resp = auth_service.build_auth_response(db, agent)
    member_service.remove_member(db, agency.id, owner, agent.id)
    with pytest.raises(AppError):
        auth_service.refresh_session(db, resp["refresh_token"])


def test_revoke_sessions_keeps_member_active(db):
    agency, owner, agent = _agency_owner_agent(db)
    resp = auth_service.build_auth_response(db, agent)
    member_service.revoke_sessions(db, agency.id, owner, agent.id)
    db.refresh(agent)
    # Сотрудник остаётся активным, но старые сессии мертвы.
    assert agent.is_active is True
    with pytest.raises(AppError) as exc:
        auth_service.refresh_session(db, resp["refresh_token"])
    assert exc.value.key == "session_revoked"
    # Может снова войти — новый пропуск с актуальной эпохой работает.
    fresh = auth_service.build_auth_response(db, agent)
    assert auth_service.refresh_session(db, fresh["refresh_token"])["user"].id == agent.id


def test_agent_cannot_revoke_admin_sessions(db):
    agency, owner, agent = _agency_owner_agent(db)
    # Рядовой админ (не главный) не может завершать сессии админа.
    plain_admin = user_repo.create(db, telegram_id=3, role="agency_admin", agency_id=agency.id)
    target_admin = user_repo.create(db, telegram_id=4, role="agency_admin", agency_id=agency.id)
    db.commit()
    with pytest.raises(AppError) as exc:
        member_service.revoke_sessions(db, agency.id, plain_admin, target_admin.id)
    assert exc.value.key == "only_owner_manage_admins"
