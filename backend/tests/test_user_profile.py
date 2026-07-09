"""
Тесты личного профиля юзера (юзер-центричная модель, 2026-07).

Фаза 1: аддитивные поля профиля в users (first_name/last_name/phone/
phone_verified/language) и бэкфилл first_name из full_name. Поведение
авторизации/изоляции при этом НЕ меняется — членства (0035) остаются
источником правды о ролях.
"""
from app.db.models.user import User


def test_user_has_profile_fields(db):
    """Модель принимает и хранит новые поля профиля."""
    u = User(
        telegram_id=900001,
        role="agent",
        agency_id=None,
        first_name="Азиз",
        last_name="Каримов",
        phone="+998901234567",
        phone_verified=True,
        language="uz",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    assert u.first_name == "Азиз"
    assert u.last_name == "Каримов"
    assert u.phone == "+998901234567"
    assert u.phone_verified is True
    assert u.language == "uz"


def test_user_profile_defaults(db):
    """Без явных значений: имя/фамилия/номер — пусто, номер не подтверждён, язык ru."""
    u = User(telegram_id=900002, role="agent")
    db.add(u)
    db.commit()
    db.refresh(u)
    assert u.first_name is None
    assert u.last_name is None
    assert u.phone is None
    assert u.phone_verified is False
    assert u.language == "ru"


def _backfill_first_name(db):
    """Та же логика, что в миграции 0038 — проверяем её на реальной сессии БД."""
    for u in (
        db.query(User)
        .filter(User.first_name.is_(None), User.full_name.isnot(None))
        .all()
    ):
        u.first_name = u.full_name
    db.commit()


def test_backfill_first_name_from_full_name(db):
    """Существующему юзеру (full_name задан, first_name пуст) проставляем first_name."""
    u = User(telegram_id=900003, role="agent", full_name="Сардор Алиев")
    db.add(u)
    db.commit()
    _backfill_first_name(db)
    db.refresh(u)
    assert u.first_name == "Сардор Алиев"
