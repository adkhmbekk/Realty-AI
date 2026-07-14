"""login_with_telegram_id: вход нативки через бота попадает в аккаунт по telegram_id."""
import pytest

from app.core.errors import AppError
from app.repositories import user_repo
from app.services import auth_service


def test_creates_personal_account_for_new_telegram_id(db):
    resp = auth_service.login_with_telegram_id(
        db, telegram_id=555001, first_name="Иван", last_name="Петров"
    )
    assert resp["access_token"]
    user = user_repo.get_by_telegram_id(db, 555001)
    assert user is not None
    assert user.role == "user"
    assert user.agency_id is None
    assert user.full_name == "Иван Петров"


def test_returns_existing_account(db):
    existing = user_repo.create(db, telegram_id=555002, role="superadmin", agency_id=None)
    db.commit()
    resp = auth_service.login_with_telegram_id(db, telegram_id=555002)
    assert resp["user"].id == existing.id
    assert resp["user"].role == "superadmin"


def test_deactivated_account_rejected(db):
    u = user_repo.create(db, telegram_id=555003, role="user", agency_id=None)
    u.is_active = False
    db.commit()
    with pytest.raises(AppError):
        auth_service.login_with_telegram_id(db, telegram_id=555003)
