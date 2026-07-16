"""
Схемы для входа и профиля пользователя.
Схемы описывают, что приходит в запросе и что уходит в ответе.
"""
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TelegramAuthRequest(BaseModel):
    # Строка initData, которую Telegram передаёт в Mini App.
    init_data: str


class GoogleAuthRequest(BaseModel):
    # ID-token, полученный нативным приложением от Google Sign-In. Подпись и aud
    # проверяет сервер (oauth_verify) — содержимому до проверки не доверяем.
    id_token: str


class AppleAuthRequest(BaseModel):
    # identity-token от Sign in with Apple.
    identity_token: str
    # Apple отдаёт имя пользователя ТОЛЬКО при первом входе — приложение может
    # переслать его здесь (в токене имени нет). Необязательно.
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class RefreshRequest(BaseModel):
    # Долгоживущий refresh-пропуск, выданный при входе.
    refresh_token: str
    # Если суперадмин сейчас работает внутри своего личного агентства —
    # его id (чтобы тихое продление сессии не выкидывало из агентства).
    act_as_agency_id: Optional[int] = None


class PhoneRequestIn(BaseModel):
    # Номер, на который выслать SMS-код (нормализуется на сервере).
    phone: str = Field(min_length=7, max_length=24)


class PhoneRequestOut(BaseModel):
    # Сколько секунд живёт код (для таймера в приложении).
    expires_in: int


class PhoneVerifyIn(BaseModel):
    phone: str = Field(min_length=7, max_length=24)
    # 6-значный код из SMS.
    code: str = Field(min_length=4, max_length=10)


class HeartbeatRequest(BaseModel):
    # Агентство, ВНУТРИ которого юзер сейчас находится (phase 'ready'); в личном
    # кабинете — None. По нему отмечаем присутствие в конкретном членстве.
    agency_id: Optional[int] = None


class ProfileUpdate(BaseModel):
    # Правка личного профиля (имя/фамилия/язык). Все поля необязательны —
    # обновляем только присланные.
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    language: Optional[str] = None


class PhoneUpdate(BaseModel):
    # Номер приходит из Telegram-контакта (кнопка «Поделиться контактом») —
    # считаем его подтверждённым. Нормализуется на сервере.
    phone: str = Field(min_length=3, max_length=32)


class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    # У native-пользователей (вход Google/Apple) telegram_id нет → Optional.
    telegram_id: Optional[int] = None
    # Email от OAuth-провайдера (native-вход). У Telegram-юзеров обычно пусто.
    email: Optional[str] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    # Личный профиль (юзер-центричная модель, 2026-07). У acting-объекта этих
    # полей нет — берутся дефолты (как match_notify ниже).
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    phone_verified: bool = False
    language: Optional[str] = None
    role: str
    is_owner: bool = False
    agency_id: Optional[int] = None
    # Acting-контекст (суперадмин внутри своего личного агентства). У обычных
    # пользователей эти поля пустые. real_role показывает истинную роль, чтобы
    # UI знал, что под капотом владелец платформы, и показал кнопку «Выйти».
    acting_as_agency_id: Optional[int] = None
    acting_as_agency_name: Optional[str] = None
    real_role: Optional[str] = None
    # Частота бот-пуша о новых совпадениях: off / instant / daily (Волна 8).
    match_notify: Optional[str] = None


class MembershipOut(BaseModel):
    # Одно членство пользователя: в каком агентстве и с какой ролью (для
    # переключателя «мои агентства», многоролевость 2026-07).
    agency_id: int
    agency_name: str
    project_name: Optional[str] = None
    role: str
    is_owner: bool = False
    is_active: bool = True
    # Агентство, в котором пользователь работает прямо сейчас (активное).
    is_current: bool = False


class AuthResponse(BaseModel):
    access_token: str
    # Долгоживущий пропуск для тихого обновления сессии (см. /auth/refresh).
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    # Активна ли подписка агентства.
    # Для суперадмина — None (у владельца платформы подписки нет, доступ всегда полный).
    subscription_active: Optional[bool] = None
    user: UserProfile
