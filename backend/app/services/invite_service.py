"""
Бизнес-логика приглашений сотрудников (Этап 2).

Сценарий:
  1) Админ агентства создаёт приглашение с ролью и сроком → получает код и
     (если задано имя бота) готовую ссылку-диплинк для Telegram.
  2) Новый сотрудник открывает Mini App по ссылке (или вводит код вручную) и
     присылает свой initData + код. Мы проверяем подпись Telegram и код, после
     чего создаём/привязываем пользователя к агентству с нужной ролью и выдаём
     ему пропуск — точно такой же, как при обычном входе.

Приглашение одноразовое: после успешного вступления оно помечается
использованным (used_at) и больше не действует.
"""
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import status
from sqlalchemy.orm import Session

from app.config import settings
from app.core import security
from app.core.errors import AppError
from app.repositories import agency_repo, audit_repo, invite_repo, user_repo
from app.schemas.agency import ActivationOut
from app.schemas.invite import InviteCreate, InviteOut
from app.services import auth_service

# Спец-роль приглашения: активация агентства (приглашённый становится главным
# админом и запускает подписку). Не путать с ролью пользователя (agency_admin).
_OWNER_ROLE = "owner"
# Срок жизни ссылки активации агентства (дней).
ACTIVATION_DAYS = 7

# Сколько байт случайности в коде (token_urlsafe даёт ~1.3 символа на байт).
_CODE_BYTES = 9


def _generate_unique_code(db: Session) -> str:
    """Сгенерировать случайный код, которого ещё нет в базе."""
    for _ in range(10):
        code = secrets.token_urlsafe(_CODE_BYTES)
        if invite_repo.get_by_code(db, code) is None:
            return code
    # Практически недостижимо, но не зацикливаемся молча.
    raise AppError(
        "invite_code_generation_failed", status.HTTP_500_INTERNAL_SERVER_ERROR
    )


def _as_utc(dt: datetime) -> datetime:
    """Привести дату из БД к aware-UTC. Postgres (прод) отдаёт дату со смещением,
    а SQLite (тесты) — без него; без этой нормализации сравнение с
    datetime.now(timezone.utc) падает с TypeError (naive vs aware)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _status_of(invite) -> str:
    # Исчерпано, когда израсходован лимит использований (многоразовость).
    if (invite.used_count or 0) >= (invite.max_uses or 1):
        return "used"
    if _as_utc(invite.expires_at) <= datetime.now(timezone.utc):
        return "expired"
    return "active"


def _join_link(code: str) -> Optional[str]:
    # Диплинк Telegram Mini App: открывает бота и передаёт код в start_param.
    if settings.bot_username:
        return f"https://t.me/{settings.bot_username}?startapp={code}"
    return None


def _to_out(invite) -> InviteOut:
    return InviteOut(
        id=invite.id,
        code=invite.code,
        role=invite.role,
        status=_status_of(invite),
        max_uses=invite.max_uses or 1,
        used_count=invite.used_count or 0,
        join_link=_join_link(invite.code),
        expires_at=invite.expires_at,
        used_at=invite.used_at,
        used_by_telegram_id=invite.used_by_telegram_id,
        created_at=invite.created_at,
    )


def create_invite(
    db: Session, agency_id: int, created_by: int, payload: InviteCreate,
    is_owner: bool = False,
) -> InviteOut:
    # Обычный админ (не владелец) может приглашать только агентов.
    # Право выдавать роль администратора есть лишь у главного админа.
    if not is_owner and payload.role != "agent":
        raise AppError("invite_role_forbidden", status.HTTP_403_FORBIDDEN)
    code = _generate_unique_code(db)
    expires_at = datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days)
    invite = invite_repo.create(
        db,
        agency_id=agency_id,
        code=code,
        role=payload.role,
        created_by=created_by,
        expires_at=expires_at,
        max_uses=payload.max_uses,
    )
    audit_repo.add(
        db, action="invite_created", agency_id=agency_id, actor_user_id=created_by,
        target=payload.role,
        note=f"срок {payload.expires_in_days} дн., лимит {payload.max_uses}",
    )
    db.commit()
    db.refresh(invite)
    return _to_out(invite)


def list_invites(db: Session, agency_id: int) -> List[InviteOut]:
    # Ссылки активации агентства (role='owner') в список приглашений сотрудников
    # не показываем — это служебные ссылки для владельца платформы.
    return [
        _to_out(inv)
        for inv in invite_repo.get_all(db, agency_id)
        if inv.role != _OWNER_ROLE
    ]


# ── Активация агентства по ссылке (owner-приглашение) ─────────────────
def activation_out(invite) -> ActivationOut:
    return ActivationOut(
        code=invite.code,
        link=_join_link(invite.code),
        expires_at=invite.expires_at,
        status=_status_of(invite),
    )


def create_owner_invite(
    db: Session, agency_id: int, created_by_user_id: Optional[int],
    expires_in_days: int = ACTIVATION_DAYS,
) -> "object":
    """Создать ссылку активации агентства (без commit — коммитит вызывающий)."""
    code = _generate_unique_code(db)
    expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
    return invite_repo.create(
        db, agency_id=agency_id, code=code, role=_OWNER_ROLE,
        created_by=created_by_user_id, expires_at=expires_at,
    )


def get_active_owner_invite(db: Session, agency_id: int):
    for inv in invite_repo.get_all(db, agency_id):
        if inv.role == _OWNER_ROLE and _status_of(inv) == "active":
            return inv
    return None


def revoke_owner_invites(db: Session, agency_id: int) -> None:
    """Удалить все неиспользованные ссылки активации агентства."""
    for inv in invite_repo.get_all(db, agency_id):
        if inv.role == _OWNER_ROLE and inv.used_at is None:
            invite_repo.delete(db, inv)


def reissue_owner_invite(db: Session, agency_id: int, created_by_user_id: Optional[int]):
    """Отозвать старые ссылки активации и создать новую (без commit)."""
    revoke_owner_invites(db, agency_id)
    return create_owner_invite(db, agency_id, created_by_user_id)


def revoke_invite(db: Session, agency_id: int, invite_id: int) -> None:
    invite = invite_repo.get_by_id(db, agency_id, invite_id)
    if invite is None:
        raise AppError("invite_not_found", status.HTTP_404_NOT_FOUND)
    audit_repo.add(
        db, action="invite_revoked", agency_id=agency_id, target=invite.role
    )
    invite_repo.delete(db, invite)
    db.commit()


def redeem_invite(db: Session, init_data: str, code: str) -> dict:
    # 1. Без токена бота проверить подлинность входа невозможно.
    if not settings.bot_token:
        raise AppError(
            "telegram_login_not_configured", status.HTTP_503_SERVICE_UNAVAILABLE
        )

    # 2. Проверяем подпись Telegram — это подтверждает личность сотрудника.
    try:
        data = security.validate_init_data(
            init_data, settings.bot_token, settings.init_data_max_age_seconds
        )
    except security.InitDataError as exc:
        raise AppError(exc.key, status.HTTP_401_UNAUTHORIZED) from exc

    tg_user = data["user"]
    telegram_id = int(tg_user["id"])

    # 3. Находим и проверяем приглашение.
    now = datetime.now(timezone.utc)
    invite = invite_repo.get_by_code(db, code)
    if invite is None:
        raise AppError("invite_not_found", status.HTTP_404_NOT_FOUND)
    # Быстрая проверка лимита/срока (понятная ошибка). АВТОРИТЕТНЫЙ, защищённый
    # от гонки контроль лимита — ниже, в атомарном claim_use.
    if (invite.used_count or 0) >= (invite.max_uses or 1):
        raise AppError("invite_already_used", status.HTTP_409_CONFLICT)
    if _as_utc(invite.expires_at) <= now:
        raise AppError("invite_expired", status.HTTP_400_BAD_REQUEST)

    # 4. Создаём или привязываем пользователя к агентству приглашения.
    username = tg_user.get("username")
    full_name = " ".join(
        part for part in [tg_user.get("first_name"), tg_user.get("last_name")] if part
    ) or None

    # Ссылка активации агентства (role='owner') делает вступившего ГЛАВНЫМ
    # админом (agency_admin + is_owner) и запускает подписку. Обычная ссылка —
    # просто роль из приглашения (agent/agency_admin).
    is_owner_invite = invite.role == _OWNER_ROLE
    target_role = "agency_admin" if is_owner_invite else invite.role

    user = user_repo.get_by_telegram_id(db, telegram_id)
    # Проверяем право на вступление ДО «занятия» использования — чтобы отказ
    # (уже в агентстве / суперадмин) не съедал лимит приглашения.
    if user is not None:
        if user.role == "superadmin":
            raise AppError("superadmin_cannot_join", status.HTTP_400_BAD_REQUEST)
        if user.agency_id is not None:
            raise AppError("already_in_agency", status.HTTP_409_CONFLICT)

    # 4.0. Атомарно занимаем одно использование приглашения (защита от гонки:
    # два одновременных вступления не пробьют лимит). Если лимит уже исчерпан —
    # claim_use вернёт False. Всё в одной транзакции с привязкой пользователя:
    # если привязка упадёт — откатится и «занятие», лимит не потеряется.
    if not invite_repo.claim_use(db, invite.id, telegram_id, now):
        raise AppError("invite_already_used", status.HTTP_409_CONFLICT)

    if user is not None:
        # Пользователь существовал без агентства — привязываем.
        user.agency_id = invite.agency_id
        user.role = target_role
        user.is_active = True
        if is_owner_invite:
            user.is_owner = True
        if username:
            user.username = username
        if full_name:
            user.full_name = full_name
    else:
        user = user_repo.create(
            db,
            telegram_id=telegram_id,
            role=target_role,
            agency_id=invite.agency_id,
            username=username,
            full_name=full_name,
            is_owner=is_owner_invite,
        )

    # 4.1. Активация агентства-черновика: запускаем подписку с этого момента.
    if is_owner_invite:
        agency = agency_repo.get_by_id(db, invite.agency_id)
        if agency is not None and agency.status == "pending":
            days = agency.pending_days or 30
            agency.status = "active"
            agency.subscription_expires_at = datetime.now(timezone.utc) + timedelta(days=days)
            agency.activated_at = datetime.now(timezone.utc)
            agency.pending_days = None

    # 5. Использование уже засчитано атомарно (claim_use, см. п. 4.0) —
    # used_count/used_at/used_by_telegram_id обновлены там.
    user.last_login_at = datetime.now(timezone.utc)

    audit_repo.add(
        db,
        action="agency_activated" if is_owner_invite else "member_joined",
        agency_id=invite.agency_id,
        actor_user_id=user.id,
        actor_telegram_id=telegram_id,
        actor_name=user.full_name or (("@" + username) if username else None),
        note="активация агентства" if is_owner_invite else f"роль: {invite.role}",
    )

    db.commit()
    db.refresh(user)

    # 6. Выдаём пропуск (как при обычном входе).
    return auth_service.build_auth_response(db, user)
