"""
Доступ к данным пользователей (таблица users).
Только этот слой обращается к БД напрямую — бизнес-логика ходит сюда.
"""
from typing import List, Optional, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models.user import User


def get_by_id(db: Session, user_id: int) -> Optional[User]:
    return db.get(User, user_id)


def get_by_telegram_id(db: Session, telegram_id: int) -> Optional[User]:
    """Активный пользователь по telegram_id. АРХИВНЫХ НЕ возвращаем: их аккаунт
    «удалён», а Telegram освобождён — поэтому вход по нему должен завести НОВЫЙ
    чистый аккаунт (login создаёт его, не найдя активного)."""
    return db.execute(
        select(User).where(
            User.telegram_id == telegram_id, User.archived_at.is_(None)
        )
    ).scalar_one_or_none()


def list_all(
    db: Session, *, q: Optional[str] = None, archived: bool = False,
    extra=None, limit: int = 50, offset: int = 0,
) -> Tuple[List[User], int]:
    """Пользователи прошки (КРОМЕ суперадминов) — для витрины «юзеры» у владельца
    платформы. archived=False — активные, True — архив (удалённые). Новые сверху;
    фильтр q по имени/username/телефону. extra — доп. SQL-условия (напр. фильтр по
    тиру вовлечённости, который строит сервис). Возвращает (список, всего)."""
    conds = [User.role != "superadmin"]
    conds.append(User.archived_at.isnot(None) if archived else User.archived_at.is_(None))
    if extra:
        conds.extend(extra)
    if q and q.strip():
        like = f"%{q.strip()}%"
        conds.append(
            or_(
                User.full_name.ilike(like),
                User.first_name.ilike(like),
                User.last_name.ilike(like),
                User.username.ilike(like),
                User.phone.ilike(like),
            )
        )
    total = db.execute(
        select(func.count()).select_from(User).where(*conds)
    ).scalar_one()
    items = list(
        db.execute(
            select(User)
            .where(*conds)
            .order_by(User.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return items, total


def presence_signals_active(db: Session):
    """(last_seen_at, last_login_at) всех АКТИВНЫХ юзеров прошки (кроме суперадминов).
    Лёгкая выборка для агрегатной сводки по тирам вовлечённости — считаем в Python
    тем же engagement(), что и per-row, чтобы сводка и бейджи не разъезжались."""
    return db.execute(
        select(User.last_seen_at, User.last_login_at).where(
            User.role != "superadmin", User.archived_at.is_(None)
        )
    ).all()


def get_by_phone(db: Session, phone: str) -> Optional[User]:
    """Активный пользователь по номеру телефона (номер уникален среди активных;
    архивные не учитываем — их номер освобождён)."""
    return db.execute(
        select(User).where(User.phone == phone, User.archived_at.is_(None))
    ).scalar_one_or_none()


def get_by_google_sub(db: Session, google_sub: str) -> Optional[User]:
    """Активный пользователь по Google 'sub' (native-вход). Архивные не учитываем
    (их идентичность освобождена — следующий вход заведёт новый аккаунт)."""
    return db.execute(
        select(User).where(User.google_sub == google_sub, User.archived_at.is_(None))
    ).scalar_one_or_none()


def get_by_apple_sub(db: Session, apple_sub: str) -> Optional[User]:
    """Активный пользователь по Apple 'sub' (native-вход). Архивные не учитываем."""
    return db.execute(
        select(User).where(User.apple_sub == apple_sub, User.archived_at.is_(None))
    ).scalar_one_or_none()


def get_by_agency(db: Session, agency_id: int) -> List[User]:
    """Все сотрудники агентства (для управления командой)."""
    return list(
        db.execute(
            select(User)
            .where(User.agency_id == agency_id)
            .order_by(User.role, User.created_at)
        )
        .scalars()
        .all()
    )


def get_owner(db: Session, agency_id: int) -> Optional[User]:
    """Владелец агентства (главный администратор, is_owner=True). Может быть None."""
    return db.execute(
        select(User)
        .where(
            User.agency_id == agency_id,
            User.role == "agency_admin",
            User.is_owner.is_(True),
        )
        .order_by(User.created_at)
        .limit(1)
    ).scalar_one_or_none()


def get_member(db: Session, agency_id: int, user_id: int) -> Optional[User]:
    """Сотрудник по id, но только в пределах своего агентства (изоляция)."""
    return db.execute(
        select(User).where(User.id == user_id, User.agency_id == agency_id)
    ).scalar_one_or_none()


def get_by_ids(db: Session, ids) -> List[User]:
    """Несколько пользователей по их id (для отображения имён создателей)."""
    ids = list(ids)
    if not ids:
        return []
    return list(
        db.execute(select(User).where(User.id.in_(ids))).scalars().all()
    )


def create(
    db: Session,
    telegram_id: Optional[int] = None,
    role: str = "user",
    agency_id: Optional[int] = None,
    username: Optional[str] = None,
    full_name: Optional[str] = None,
    is_owner: bool = False,
    google_sub: Optional[str] = None,
    apple_sub: Optional[str] = None,
    email: Optional[str] = None,
) -> User:
    # telegram_id=None — для native-пользователей (вход Google/Apple): их
    # идентичность в google_sub/apple_sub.
    user = User(
        telegram_id=telegram_id,
        role=role,
        agency_id=agency_id,
        username=username,
        full_name=full_name,
        is_active=True,
        is_owner=is_owner,
        google_sub=google_sub,
        apple_sub=apple_sub,
        email=email,
    )
    db.add(user)
    db.flush()  # чтобы получить сгенерированный id
    return user
