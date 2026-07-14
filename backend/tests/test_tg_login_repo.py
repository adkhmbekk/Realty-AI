"""tg_login_codes: модель и доступ к данным (одноразовые коды входа через бота)."""
from datetime import datetime, timedelta, timezone

from app.db.models.tg_login_code import TgLoginCode
from app.repositories import tg_login_repo


def test_model_insert_and_defaults(db):
    row = TgLoginCode(
        code="abc123",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    assert row.id is not None
    assert row.status == "pending"
    assert row.telegram_id is None


def test_create_and_get_by_code(db):
    exp = datetime.now(timezone.utc) + timedelta(minutes=5)
    row = tg_login_repo.create(db, code="xyz789", expires_at=exp)
    db.commit()
    assert row.id is not None
    got = tg_login_repo.get_by_code(db, "xyz789")
    assert got is not None and got.id == row.id
    assert tg_login_repo.get_by_code(db, "nope") is None
