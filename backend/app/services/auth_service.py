"""
Бизнес-логика входа.

Принимает initData от Telegram, проверяет его, находит пользователя в нашей
базе, обновляет его данные и выдаёт пропуск (JWT).

Важно: незнакомый пользователь (не привязанный к агентству) НЕ получает доступ.
Привязка происходит только через приглашение (будет на следующем этапе) или
если это суперадмин платформы.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import status
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
    if user is None:
        raise AppError("not_in_agency", status.HTTP_403_FORBIDDEN)
    if not user.is_active:
        raise AppError("access_deactivated", status.HTTP_403_FORBIDDEN)

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
            },
        }

    # У суперадмина (владельца платформы) подписки нет — оставляем None,
    # чтобы фронтенд не показывал ему строку про подписку.
    subscription_active = None
    if user.role != "superadmin":
        agency = agency_repo.get_by_id(db, user.agency_id) if user.agency_id else None
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


def touch_last_seen(db: Session, user_id: Optional[int]) -> None:
    """
    Отметить, что пользователь сейчас в приложении (heartbeat). Обновляет
    users.last_seen_at не чаще раза в ~30 секунд, чтобы не писать в БД на каждый
    пинг. По этому полю панель владельца показывает статус «в сети».
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
        db.commit()
