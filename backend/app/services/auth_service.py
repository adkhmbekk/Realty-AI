"""
Бизнес-логика входа.

Принимает initData от Telegram, проверяет его, находит пользователя в нашей
базе, обновляет его данные и выдаёт пропуск (JWT).

Важно: незнакомый пользователь (не привязанный к агентству) НЕ получает доступ.
Привязка происходит только через приглашение (будет на следующем этапе) или
если это суперадмин платформы.
"""
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.core import security
from app.core.errors import AppError
from app.core.subscription import agency_is_active
from app.repositories import (
    agency_membership_repo,
    agency_repo,
    audit_repo,
    user_repo,
)


def login_with_init_data(db: Session, init_data: str, ip: Optional[str] = None) -> dict:
    # 1. Без токена бота проверить подлинность входа невозможно.
    if not settings.bot_token:
        raise AppError(
            "telegram_login_not_configured", status.HTTP_503_SERVICE_UNAVAILABLE
        )

    # 2. Проверяем подпись Telegram. Анти-повтор здесь НЕ «гасим» сразу: вход
    #    незнакомца отвечает 403, а сразу за этим фронтенд шлёт тот же initData
    #    на вступление по коду (/invites/redeem). Если бы вход «сжигал» подпись,
    #    redeem ложно посчитался бы повтором и новый сотрудник не смог бы войти.
    #    Поэтому подпись помечаем использованной только когда реально выдаём
    #    сессию существующему пользователю (ниже).
    try:
        data = security.validate_init_data(
            init_data, settings.bot_token, settings.init_data_max_age_seconds,
            anti_replay=False,
        )
    except security.InitDataError as exc:
        raise AppError(exc.key, status.HTTP_401_UNAUTHORIZED) from exc

    tg_user = data["user"]
    telegram_id = int(tg_user["id"])

    # 3. Ищем пользователя в нашей базе.
    user = user_repo.get_by_telegram_id(db, telegram_id)
    if user is not None and not user.is_active:
        raise AppError("access_deactivated", status.HTTP_403_FORBIDDEN)
    if user is None:
        # Открытая регистрация (2026-07): незнакомец получает ЛИЧНЫЙ аккаунт
        # (role='user', без агентства) и попадает в личное пространство, откуда
        # сам создаёт агентство или вступает по коду. Подпись здесь НЕ «гасим»
        # (как прежде для «незнакомца») — чтобы последующий redeem с той же
        # подписью не посчитался повтором; она погасится при redeem/след. входе.
        first = tg_user.get("first_name")
        last = tg_user.get("last_name")
        full = " ".join(p for p in [first, last] if p) or None
        user = user_repo.create(
            db,
            telegram_id=telegram_id,
            role="user",
            agency_id=None,
            username=tg_user.get("username"),
            full_name=full,
        )
        user.first_name = first
        user.last_name = last
        lang = (tg_user.get("language_code") or "ru").split("-")[0]
        user.language = lang if lang in ("ru", "uz", "en") else "ru"
        user.last_login_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)
        return build_auth_response(db, user)

    # Пользователь есть и активен — выдаём сессию, поэтому теперь «гасим» повтор.
    if security.remember_replay(data["init_data_hash"], data["replay_expires_at"]):
        raise AppError("init_data_replayed", status.HTTP_401_UNAUTHORIZED)

    # 4. Обновляем актуальные данные из Telegram и время входа.
    username = tg_user.get("username")
    if username:
        user.username = username
    full_name = " ".join(
        part for part in [tg_user.get("first_name"), tg_user.get("last_name")] if part
    )
    if full_name:
        user.full_name = full_name
    user.last_login_at = datetime.now(timezone.utc)

    # 5. Журнал аудита: фиксируем вход (для сотрудников агентства).
    if user.agency_id is not None:
        audit_repo.add(
            db,
            action="login",
            agency_id=user.agency_id,
            actor_user_id=user.id,
            actor_telegram_id=user.telegram_id,
            actor_name=user.full_name or (("@" + user.username) if user.username else None),
            ip=ip,
        )

    db.commit()
    db.refresh(user)

    # 6. Выдаём пропуск (вместе со статусом подписки агентства).
    return build_auth_response(db, user)


def login_with_google(
    db: Session,
    google_sub: str,
    email: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
) -> dict:
    """
    Вход через Google (нативное приложение, вне Telegram). Получает УЖЕ
    проверенные claims (подпись ID-token проверяет роут через oauth_verify).

    Первый вход по этому google_sub → создаётся ЛИЧНЫЙ аккаунт (role='user', без
    агентства, telegram_id=None) — так же, как открытая регистрация из Telegram.
    Повторный вход возвращает того же пользователя. Связывание с Telegram-
    аккаунтом того же человека по email здесь НЕ делаем (риск угона) — это
    отдельный этап (телефон-якорь).
    """
    user = user_repo.get_by_google_sub(db, google_sub)
    if user is not None and not user.is_active:
        raise AppError("access_deactivated", status.HTTP_403_FORBIDDEN)

    if user is None:
        full = " ".join(p for p in [first_name, last_name] if p) or None
        user = user_repo.create(
            db,
            telegram_id=None,
            role="user",
            agency_id=None,
            google_sub=google_sub,
            email=email,
            full_name=full,
        )
        user.first_name = first_name
        user.last_name = last_name
        user.last_login_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)
        return build_auth_response(db, user)

    # Существующий native-аккаунт — обновляем время входа и (если ещё не знали)
    # email, выдаём сессию.
    if email and not user.email:
        user.email = email
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return build_auth_response(db, user)


def login_with_apple(
    db: Session,
    apple_sub: str,
    email: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
) -> dict:
    """
    Вход через Apple (нативное приложение). Аналог login_with_google по apple_sub.
    Apple отдаёт имя пользователя ТОЛЬКО при самом первом входе (в теле запроса
    авторизации, не в токене) — поэтому first/last сюда приходят опционально.
    """
    user = user_repo.get_by_apple_sub(db, apple_sub)
    if user is not None and not user.is_active:
        raise AppError("access_deactivated", status.HTTP_403_FORBIDDEN)

    if user is None:
        full = " ".join(p for p in [first_name, last_name] if p) or None
        user = user_repo.create(
            db,
            telegram_id=None,
            role="user",
            agency_id=None,
            apple_sub=apple_sub,
            email=email,
            full_name=full,
        )
        user.first_name = first_name
        user.last_name = last_name
        user.last_login_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)
        return build_auth_response(db, user)

    if email and not user.email:
        user.email = email
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return build_auth_response(db, user)


def login_with_telegram_id(
    db: Session,
    telegram_id: int,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    username: Optional[str] = None,
) -> dict:
    """
    Вход нативного приложения через Telegram-бота (@realtyloginbot). telegram_id
    УЖЕ аутентифицирован ботом (webhook подтвердил, что кнопку нажал именно этот
    пользователь) — поэтому здесь без проверки initData.

    По telegram_id находим СУЩЕСТВУЮЩИЙ аккаунт (тот же, что в Telegram Mini App)
    и выдаём его сессию — так суперадмин входит в нативку под собой. Незнакомый
    telegram_id → создаётся ЛИЧНЫЙ аккаунт (role='user'), как открытая регистрация
    из Telegram. Профиль существующего аккаунта НЕ перезаписываем (имя могло быть
    отредактировано пользователем).
    """
    user = user_repo.get_by_telegram_id(db, telegram_id)
    if user is not None and not user.is_active:
        raise AppError("access_deactivated", status.HTTP_403_FORBIDDEN)

    if user is None:
        full = " ".join(p for p in [first_name, last_name] if p) or None
        user = user_repo.create(
            db,
            telegram_id=telegram_id,
            role="user",
            agency_id=None,
            username=username,
            full_name=full,
        )
        user.first_name = first_name
        user.last_name = last_name
        user.last_login_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)
        return build_auth_response(db, user)

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return build_auth_response(db, user)


def refresh_session(
    db: Session, refresh_token: str, act_as_agency_id: Optional[int] = None
) -> dict:
    """
    Обновить сессию по refresh-пропуску: выдать новый access (+ refresh) без
    повторной проверки initData. Так длинная сессия не упирается в «тихий
    тупик» после истечения короткого пропуска.

    act_as_agency_id (необязательно): если суперадмин сейчас работает ВНУТРИ
    своего личного агентства, фронтенд передаёт его id — чтобы тихое продление
    токена не выкидывало владельца из агентства обратно на платформу.
    """
    payload = security.decode_refresh_token(refresh_token)
    if payload is None:
        raise AppError("auth_invalid_token", status.HTTP_401_UNAUTHORIZED)
    user = user_repo.get_by_id(db, payload.get("user_id"))
    if user is None or not user.is_active:
        raise AppError("user_not_found_or_inactive", status.HTTP_401_UNAUTHORIZED)
    # Мгновенный отзыв: refresh-токен с устаревшей версией сессии недействителен.
    if (payload.get("epoch") or 0) != (getattr(user, "session_epoch", 0) or 0):
        raise AppError("session_revoked", status.HTTP_401_UNAUTHORIZED)
    return build_auth_response(db, user, act_as_agency_id=act_as_agency_id)


def build_auth_response(db: Session, user, act_as_agency_id: Optional[int] = None) -> dict:
    """
    Собрать ответ авторизации: пропуск (JWT), refresh-пропуск, статус подписки и
    профиль. Используется при входе, вступлении по приглашению, обновлении сессии
    и при «входе» суперадмина в своё личное агентство (acting-контекст).

    Если задан act_as_agency_id и текущий user — суперадмин, владеющий этим
    личным агентством, выдаём сессию, оформленную как главный админ этого
    агентства (role=agency_admin, is_owner). Владение перепроверяем из БД; если
    не подтвердилось — молча отдаём обычную сессию (acting «отвалился»).
    """
    # «Версия сессии» пользователя — кладём в оба пропуска (access+refresh).
    # Её бамп (отключение/исключение/«выйти со всех устройств») мгновенно
    # обесценивает все ранее выданные пропуска этого человека.
    epoch = getattr(user, "session_epoch", 0) or 0
    acting_agency = None
    acting_role = "agency_admin"
    acting_is_owner = True
    acting_real_role = "superadmin"
    if act_as_agency_id is not None:
        user_role = getattr(user, "role", None)
        if user_role == "superadmin":
            # Путь А: суперадмин в своё личное ИЛИ ОБЩЕЕ агентство платформы
            # (is_shared — «Realty AI») → acting-сессия главного админа.
            agency = agency_repo.get_by_id(db, act_as_agency_id)
            if agency is not None and (
                agency.owner_telegram_id == user.telegram_id
                or getattr(agency, "is_shared", False)
            ):
                acting_agency = agency
                acting_role = "agency_admin"
                acting_is_owner = True
                acting_real_role = "superadmin"
        elif act_as_agency_id != getattr(user, "agency_id", None):
            # Путь Б: обычный участник в другое своё агентство (по членству).
            # Роль/владелец берутся из членства именно в ТОМ агентстве.
            m = agency_membership_repo.get(db, user.id, act_as_agency_id)
            if m is not None and m.is_active:
                agency = agency_repo.get_by_id(db, act_as_agency_id)
                if agency is not None:
                    acting_agency = agency
                    acting_role = m.role
                    acting_is_owner = m.is_owner
                    acting_real_role = user_role

    if acting_agency is not None:
        token = security.create_access_token(
            {
                "user_id": user.id,
                "telegram_id": user.telegram_id,
                "agency_id": acting_agency.id,
                "role": acting_role,
                "act_as_agency_id": acting_agency.id,
                "epoch": epoch,
            }
        )
        refresh_token = security.create_refresh_token({"user_id": user.id, "epoch": epoch})
        return {
            "access_token": token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            # Агентство «поверх» доступу по подписке не подчиняется (её и нет).
            "subscription_active": True,
            "user": {
                "id": user.id,
                "telegram_id": user.telegram_id,
                "username": user.username,
                "full_name": user.full_name,
                "role": acting_role,
                "is_owner": acting_is_owner,
                "agency_id": acting_agency.id,
                "acting_as_agency_id": acting_agency.id,
                "acting_as_agency_name": acting_agency.name,
                "real_role": acting_real_role,
                # Личный профиль НЕ теряем при входе в агентство (acting): иначе
                # после «открыть/войти» в личном кабинете обнулялись имя/фамилия/
                # номер (они не входили в acting-ответ). Берём из реальной строки.
                "first_name": getattr(user, "first_name", None),
                "last_name": getattr(user, "last_name", None),
                "phone": getattr(user, "phone", None),
                "phone_verified": getattr(user, "phone_verified", False),
                "language": getattr(user, "language", None),
                "match_notify": getattr(user, "match_notify", None),
            },
        }

    # У суперадмина (владельца платформы) подписки нет — оставляем None,
    # чтобы фронтенд не показывал ему строку про подписку.
    subscription_active = None
    # Личный аккаунт без агентства (role='user') — подписка неприменима (None),
    # как и у суперадмина; фронтенд покажет личное пространство, не экран подписки.
    if user.role != "superadmin" and getattr(user, "agency_id", None) is not None:
        agency = agency_repo.get_by_id(db, user.agency_id)
        subscription_active = agency_is_active(agency)

    token = security.create_access_token(
        {
            "user_id": user.id,
            "telegram_id": user.telegram_id,
            "agency_id": user.agency_id,
            "role": user.role,
            "epoch": epoch,
        }
    )
    refresh_token = security.create_refresh_token({"user_id": user.id, "epoch": epoch})

    return {
        "access_token": token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "subscription_active": subscription_active,
        "user": user,
    }


def update_profile(
    db: Session,
    user,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    language: Optional[str] = None,
) -> "object":
    """
    Обновить личный профиль (имя/фамилия/язык). Берём НАСТОЯЩУЮ строку из БД
    (user мог быть acting-объектом суперадмина). full_name держим в синхроне
    (first + last) — его использует существующий код отображения.
    """
    real = user_repo.get_by_id(db, user.id)
    if real is None:
        raise AppError("user_not_found_or_inactive", status.HTTP_401_UNAUTHORIZED)
    if first_name is not None:
        real.first_name = first_name.strip() or None
    if last_name is not None:
        real.last_name = last_name.strip() or None
    if language is not None and language in ("ru", "uz", "en"):
        real.language = language
    fn = " ".join(p for p in [real.first_name, real.last_name] if p) or None
    if fn:
        real.full_name = fn
    db.commit()
    db.refresh(real)
    return real


def _normalize_phone(raw: str) -> str:
    """Единый вид номера: '+' + только цифры. Так '+998 90 …' и '998 90 …'
    приводятся к одному виду и уникальность работает надёжно."""
    digits = "".join(c for c in (raw or "") if c.isdigit())
    return ("+" + digits) if digits else ""


# Телефон — «якорь» аккаунта (будущий вход с сайта/приложения), поэтому он должен
# быть корректным. E.164: '+' и 9–15 цифр (короче — заведомо не номер, длиннее —
# невалидно). Пустой/мусорный номер отклоняем, чтобы не засорять уникальный якорь.
_PHONE_RE = re.compile(r"^\+\d{9,15}$")


def set_phone(db: Session, user, phone: str) -> "object":
    """
    Задать/сменить номер телефона личного аккаунта. Номер приходит из
    Telegram-контакта → считаем подтверждённым (phone_verified=True). Номер
    уникален: если уже привязан к ДРУГОМУ аккаунту — phone_taken. Формат
    проверяем (E.164): иначе — phone_invalid.
    """
    real = user_repo.get_by_id(db, user.id)
    if real is None:
        raise AppError("user_not_found_or_inactive", status.HTTP_401_UNAUTHORIZED)
    normalized = _normalize_phone(phone)
    if not _PHONE_RE.match(normalized):
        raise AppError("phone_invalid", status.HTTP_400_BAD_REQUEST)
    existing = user_repo.get_by_phone(db, normalized)
    if existing is not None and existing.id != real.id:
        raise AppError("phone_taken", status.HTTP_409_CONFLICT)
    real.phone = normalized
    real.phone_verified = True
    try:
        db.commit()
    except IntegrityError:
        # Гонка: номер занят между проверкой и commit (уникальный индекс).
        db.rollback()
        raise AppError("phone_taken", status.HTTP_409_CONFLICT)
    db.refresh(real)
    return real


def list_my_memberships(db: Session, user) -> list:
    """
    Все агентства, в которых состоит пользователь (для переключателя «мои
    агентства», многоролевость 2026-07). is_current — агентство, в котором он
    работает прямо сейчас (совместимо с acting-контекстом). У суперадмина
    членств нет (он работает через личные/общее агентства) — вернётся пусто.
    """
    rows = agency_membership_repo.list_for_user(db, user.id)
    current = getattr(user, "agency_id", None)
    return [
        {
            "agency_id": a.id,
            "agency_name": a.name,
            "project_name": a.project_name,
            "role": m.role,
            "is_owner": m.is_owner,
            "is_active": m.is_active,
            "is_current": a.id == current,
        }
        for m, a in rows
    ]


def touch_last_seen(
    db: Session, user_id: Optional[int], agency_id: Optional[int] = None
) -> None:
    """
    Отметить, что пользователь сейчас в приложении (heartbeat). Обновляет
    users.last_seen_at не чаще раза в ~30 секунд, чтобы не писать в БД на каждый
    пинг. По этому полю панель владельца показывает статус «в сети».

    Если передан agency_id (юзер сейчас ВНУТРИ этого агентства), заодно обновляет
    присутствие в этом членстве (agency_memberships.last_seen_at) — для per-agency
    статуса в карточке юзера. В личном кабинете agency_id=None → членства не трогаем.
    """
    if user_id is None:
        return
    user = user_repo.get_by_id(db, user_id)
    if user is None:
        return
    now = datetime.now(timezone.utc)
    prev = user.last_seen_at
    if prev is not None and prev.tzinfo is None:
        prev = prev.replace(tzinfo=timezone.utc)
    if prev is None or (now - prev).total_seconds() >= 30:
        user.last_seen_at = now
        if agency_id is not None:
            m = agency_membership_repo.get(db, user_id, agency_id)
            if m is not None:
                m.last_seen_at = now
        db.commit()
