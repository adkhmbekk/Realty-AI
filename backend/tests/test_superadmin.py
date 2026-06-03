"""
Тесты владельца платформы (ensure_superadmin):
- настроенный суперадмин ВСЕГДА приводится к «активный суперадмин без агентства»
  (самовосстановление — лечит случай, когда аккаунт случайно деактивировали);
- у всех прочих суперадминов права снимаются (их не должно быть двое);
- если пользователя нет — создаётся.
На SQLite в памяти (фикстура db из conftest).
"""
from app.db.models.user import User
from app.main import ensure_superadmin
from app.repositories import user_repo


def test_reactivates_deactivated_superadmin(db):
    # Был суперадмином, но его деактивировали — должен восстановиться.
    u = User(telegram_id=111, role="superadmin", agency_id=None, is_active=False)
    db.add(u)
    db.commit()

    ensure_superadmin(db, 111)
    db.commit()

    got = user_repo.get_by_telegram_id(db, 111)
    assert got.role == "superadmin" and got.is_active is True and got.agency_id is None


def test_promotes_regular_user(db):
    u = User(telegram_id=222, role="agent", agency_id=5, is_active=False)
    db.add(u)
    db.commit()

    ensure_superadmin(db, 222)
    db.commit()

    got = user_repo.get_by_telegram_id(db, 222)
    assert got.role == "superadmin" and got.is_active is True and got.agency_id is None


def test_creates_when_missing(db):
    ensure_superadmin(db, 999)
    db.commit()
    got = user_repo.get_by_telegram_id(db, 999)
    assert got is not None and got.role == "superadmin" and got.is_active is True


def test_demotes_other_superadmins(db):
    db.add(User(telegram_id=111, role="superadmin", agency_id=None, is_active=True))
    db.add(User(telegram_id=222, role="superadmin", agency_id=None, is_active=True))
    db.commit()

    ensure_superadmin(db, 111)  # настроенный владелец — 111
    db.commit()

    a = user_repo.get_by_telegram_id(db, 111)
    b = user_repo.get_by_telegram_id(db, 222)
    assert a.role == "superadmin" and a.is_active is True
    # Прежний суперадмин 222 теряет права и деактивируется.
    assert b.role == "agent" and b.is_active is False
