"""
Архивация/восстановление/удаление юзеров владельцем платформы (2026-07).
Уровень сервисов, SQLite в памяти.
"""
from types import SimpleNamespace

import pytest

from app.core import dependencies
from app.core.errors import AppError
from app.db.models.agency import Agency
from app.repositories import agency_membership_repo, agency_repo, user_repo
from app.services import platform_service


def _user(db, telegram_id, role="agency_admin", agency_id=None):
    u = user_repo.create(
        db, telegram_id=telegram_id, role=role, agency_id=agency_id,
        is_owner=(role == "agency_admin"),
    )
    db.commit()
    return u


def _agency(db, name="A"):
    a = Agency(name=name, status="active", timezone="Asia/Tashkent", default_currency="USD")
    db.add(a)
    db.commit()
    return a


def _own(db, user, agency, *, is_owner=True, role="agency_admin"):
    agency_membership_repo.create(
        db, user_id=user.id, agency_id=agency.id, role=role, is_owner=is_owner,
    )
    db.commit()


def test_archive_frees_telegram_and_bumps_epoch(db):
    u = _user(db, 700, role="user")
    ep = u.session_epoch
    platform_service.archive_user(db, u.id)
    db.refresh(u)
    assert u.archived_at is not None
    assert u.is_active is False
    assert u.session_epoch == ep + 1
    # Вход по тому же telegram_id больше НЕ находит архивного → заведётся новый.
    assert user_repo.get_by_telegram_id(db, 700) is None


def test_cannot_archive_superadmin(db):
    su = user_repo.create(db, telegram_id=705, role="superadmin", agency_id=None)
    db.commit()
    with pytest.raises(AppError) as exc:
        platform_service.archive_user(db, su.id)
    assert exc.value.key == "cannot_archive_superadmin"


def test_archive_freeze_blocks_members(db):
    owner = _user(db, 701, role="agency_admin")
    a = _agency(db, "Owned")
    _own(db, owner, a)
    platform_service.archive_user(db, owner.id, freeze_agencies=True)
    db.refresh(a)
    assert a.archived_at is not None
    # Сотрудник замороженного агентства блокируется.
    member = SimpleNamespace(agency_id=a.id)
    with pytest.raises(AppError) as exc:
        dependencies._ensure_agency_not_archived(db, member)
    assert exc.value.key == "agency_suspended"


def test_archive_without_freeze_keeps_agency_live(db):
    owner = _user(db, 706, role="agency_admin")
    a = _agency(db, "Live")
    _own(db, owner, a)
    platform_service.archive_user(db, owner.id, freeze_agencies=False)
    db.refresh(a)
    assert a.archived_at is None  # агентство работает дальше


def test_restore_transfers_owned_to_target(db):
    owner = _user(db, 702, role="agency_admin")
    a = _agency(db, "ToTransfer")
    _own(db, owner, a)
    target = _user(db, 703, role="user")
    platform_service.archive_user(db, owner.id, freeze_agencies=True)

    platform_service.restore_user_data(db, owner.id, target.id)

    # Архивный удалён, агентство разморожено и принадлежит target.
    assert user_repo.get_by_id(db, owner.id) is None
    db.refresh(a)
    db.refresh(target)
    assert a.archived_at is None
    m = agency_membership_repo.get(db, target.id, a.id)
    assert m is not None and m.is_owner is True
    assert target.agency_id == a.id and target.role == "agency_admin"


def test_restore_rejects_archived_target(db):
    owner = _user(db, 707, role="agency_admin")
    a = _agency(db, "X")
    _own(db, owner, a)
    victim = _user(db, 708, role="user")
    platform_service.archive_user(db, owner.id)
    platform_service.archive_user(db, victim.id)  # цель тоже в архиве — нельзя
    with pytest.raises(AppError) as exc:
        platform_service.restore_user_data(db, owner.id, victim.id)
    assert exc.value.key == "archive_target_invalid"


def test_purge_deletes_owned_keeps_membered(db):
    owner = _user(db, 704, role="agency_admin")
    owned = _agency(db, "Owned")
    _own(db, owner, owned)
    other = _agency(db, "Other")
    _own(db, owner, other, is_owner=False, role="agent")
    platform_service.archive_user(db, owner.id)

    platform_service.purge_user(db, owner.id)

    assert user_repo.get_by_id(db, owner.id) is None
    assert agency_repo.get_by_id(db, owned.id) is None       # владельческое — удалено
    assert agency_repo.get_by_id(db, other.id) is not None   # где был агентом — осталось
