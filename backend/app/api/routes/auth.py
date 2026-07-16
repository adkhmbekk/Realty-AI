"""
Эндпоинты входа и профиля.
Роуты не содержат бизнес-логику — они вызывают сервисы.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.core.dependencies import get_current_user
from app.core.errors import AppError
from app.core.oauth_verify import (
    OAuthError,
    verify_apple_identity_token,
    verify_google_id_token,
)
from app.core.ratelimit import rate_limit, _client_ip
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.auth import (
    AppleAuthRequest,
    AuthResponse,
    GoogleAuthRequest,
    HeartbeatRequest,
    MembershipOut,
    PhoneRequestIn,
    PhoneRequestOut,
    PhoneUpdate,
    PhoneVerifyIn,
    ProfileUpdate,
    RefreshRequest,
    TelegramAuthRequest,
    UserProfile,
)
from app.services import auth_service, phone_login_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/telegram",
    response_model=AuthResponse,
    dependencies=[Depends(rate_limit(15, 60, "auth_telegram"))],
)
def telegram_login(body: TelegramAuthRequest, request: Request, db: Session = Depends(get_db)):
    """Принять данные входа от Telegram, проверить и выдать пропуск."""
    return auth_service.login_with_init_data(db, body.init_data, ip=_client_ip(request))


@router.post(
    "/google",
    response_model=AuthResponse,
    dependencies=[Depends(rate_limit(15, 60, "auth_google"))],
)
def google_login(body: GoogleAuthRequest, db: Session = Depends(get_db)):
    """Вход из нативного приложения через Google. Проверяем подпись ID-token и
    что он выписан для НАШЕГО приложения (aud), затем выдаём наш пропуск."""
    audiences = settings.google_audiences()
    if not audiences:
        raise AppError("oauth_not_configured", status.HTTP_503_SERVICE_UNAVAILABLE)
    try:
        claims = verify_google_id_token(body.id_token, audiences)
    except OAuthError as exc:
        raise AppError(exc.key, status.HTTP_401_UNAUTHORIZED) from exc
    return auth_service.login_with_google(
        db,
        google_sub=claims["sub"],
        email=claims.get("email"),
        first_name=claims.get("given_name"),
        last_name=claims.get("family_name"),
    )


@router.post(
    "/apple",
    response_model=AuthResponse,
    dependencies=[Depends(rate_limit(15, 60, "auth_apple"))],
)
def apple_login(body: AppleAuthRequest, db: Session = Depends(get_db)):
    """Вход из нативного приложения через Apple. Имя приходит только при первом
    входе (в теле запроса, не в токене) — передаём его в сервис."""
    audiences = settings.apple_audiences()
    if not audiences:
        raise AppError("oauth_not_configured", status.HTTP_503_SERVICE_UNAVAILABLE)
    try:
        claims = verify_apple_identity_token(body.identity_token, audiences)
    except OAuthError as exc:
        raise AppError(exc.key, status.HTTP_401_UNAUTHORIZED) from exc
    return auth_service.login_with_apple(
        db,
        apple_sub=claims["sub"],
        email=claims.get("email"),
        first_name=body.first_name,
        last_name=body.last_name,
    )


@router.post(
    "/phone/request",
    response_model=PhoneRequestOut,
    # Жёстче обычного: каждая попытка = реальное SMS (деньги + бомбинг-риск).
    dependencies=[Depends(rate_limit(5, 60, "phone_request"))],
)
def phone_request(body: PhoneRequestIn, db: Session = Depends(get_db)):
    """Выслать SMS-код входа на номер (нативное приложение). Пока Eskiz не
    сконфигурирован — 503 sms_not_configured («SMS-вход пока недоступен»)."""
    return phone_login_service.request_code(db, body.phone)


@router.post(
    "/phone/verify",
    response_model=AuthResponse,
    dependencies=[Depends(rate_limit(10, 60, "phone_verify"))],
)
def phone_verify(body: PhoneVerifyIn, db: Session = Depends(get_db)):
    """Обменять SMS-код на сессию: вход в существующий аккаунт по номеру
    (номер — «якорь») или создание нового личного аккаунта."""
    return phone_login_service.verify_code(db, body.phone, body.code)


@router.post(
    "/refresh",
    response_model=AuthResponse,
    dependencies=[Depends(rate_limit(30, 60, "auth_refresh"))],
)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    """Обновить сессию по refresh-пропуску (без повторной проверки initData)."""
    return auth_service.refresh_session(
        db, body.refresh_token, act_as_agency_id=body.act_as_agency_id
    )


@router.get("/me", response_model=UserProfile)
def me(current_user: User = Depends(get_current_user)):
    """Вернуть профиль текущего пользователя (по присланному пропуску)."""
    return current_user


@router.patch("/me", response_model=UserProfile)
def update_me(
    body: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Обновить личный профиль (имя/фамилия/язык)."""
    return auth_service.update_profile(
        db,
        current_user,
        first_name=body.first_name,
        last_name=body.last_name,
        language=body.language,
    )


@router.post("/me/phone", response_model=UserProfile)
def set_my_phone(
    body: PhoneUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Задать/сменить номер телефона (из Telegram-контакта — подтверждён)."""
    return auth_service.set_phone(db, current_user, body.phone)


@router.get("/memberships", response_model=List[MembershipOut])
def my_memberships(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Агентства, в которых состоит пользователь (для переключателя «мои агентства»)."""
    return auth_service.list_my_memberships(db, current_user)


@router.post(
    "/heartbeat",
    status_code=204,
    dependencies=[Depends(rate_limit(60, 60, "auth_heartbeat"))],
)
def heartbeat(
    payload: Optional[HeartbeatRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Отметить присутствие пользователя «в сети» (периодический пинг из приложения).
    Тело необязательно; если передан agency_id — юзер внутри этого агентства."""
    agency_id = payload.agency_id if payload else None
    auth_service.touch_last_seen(db, current_user.id, agency_id)
