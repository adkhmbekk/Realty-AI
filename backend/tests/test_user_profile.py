"""
Тесты личного профиля юзера (юзер-центричная модель, 2026-07).

Фаза 1: аддитивные поля профиля в users (first_name/last_name/phone/
phone_verified/language) и бэкфилл first_name из full_name. Поведение
авторизации/изоляции при этом НЕ меняется — членства (0035) остаются
источником правды о ролях.
"""
import pytest

from app.core.errors import AppError
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


def test_personal_user_role_allowed(db):
    """Личный аккаунт без агентства (role='user', agency_id=NULL) — валиден.

    Основа открытой регистрации: человек вошёл, но ещё не в агентстве.
    Проверяем, что CHECK-ограничение роли пропускает 'user'.
    """
    u = User(telegram_id=900004, role="user", agency_id=None, first_name="Нур")
    db.add(u)
    db.commit()
    db.refresh(u)
    assert u.role == "user"
    assert u.agency_id is None


def test_user_profile_schema_exposes_profile_fields(db):
    """Схема ответа /auth/me отдаёт поля профиля (нужно фронту)."""
    from app.schemas.auth import UserProfile

    u = User(
        telegram_id=900005, role="user", agency_id=None,
        first_name="Азиз", last_name="Каримов",
        phone="+998901234567", phone_verified=True, language="uz",
    )
    db.add(u)
    db.commit()
    db.refresh(u)

    out = UserProfile.model_validate(u)
    assert out.first_name == "Азиз"
    assert out.last_name == "Каримов"
    assert out.phone == "+998901234567"
    assert out.phone_verified is True
    assert out.language == "uz"


def test_update_profile_syncs_full_name(db):
    """Правка профиля обновляет поля и держит full_name в синхроне."""
    from app.services import auth_service

    u = User(telegram_id=900006, role="user", first_name="Old", full_name="Old")
    db.add(u)
    db.commit()
    db.refresh(u)

    out = auth_service.update_profile(
        db, u, first_name="Азиз", last_name="Каримов", language="uz"
    )
    assert out.first_name == "Азиз"
    assert out.last_name == "Каримов"
    assert out.language == "uz"
    assert out.full_name == "Азиз Каримов"


def test_set_phone_verified_and_unique(db):
    """Номер нормализуется, помечается подтверждённым и уникален между аккаунтами."""
    from app.services import auth_service

    u1 = User(telegram_id=900007, role="user")
    u2 = User(telegram_id=900008, role="user")
    db.add(u1)
    db.add(u2)
    db.commit()
    db.refresh(u1)
    db.refresh(u2)

    out = auth_service.set_phone(db, u1, "+998 90 123 45 67")
    assert out.phone == "+998901234567"
    assert out.phone_verified is True

    # Тот же номер (в другом виде) второму аккаунту — занят.
    with pytest.raises(AppError) as exc:
        auth_service.set_phone(db, u2, "998901234567")
    assert exc.value.key == "phone_taken"

    # Свой же номер повторно себе — не ошибка.
    again = auth_service.set_phone(db, u1, "998901234567")
    assert again.phone == "+998901234567"
