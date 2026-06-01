"""
Локализация сообщений об ошибках сервера (ru / uz / en).

Как это работает:
  - У каждого сообщения есть КЛЮЧ и перевод на три языка (MESSAGES).
  - Язык запроса определяется ASGI-middleware (LanguageMiddleware) по заголовку
    X-Lang, который шлёт фронтенд; язык кладётся в ContextVar.
  - AppError(key=...) — это HTTPException, у которого detail уже переведён на
    язык текущего запроса (в момент создания исключения).
  - translate(key, lang, **params) — перевод с подстановкой параметров и
    запасным вариантом на русском (а если ключа нет — возвращаем сам ключ).

ВАЖНО: LanguageMiddleware сделан «чистым» ASGI-middleware (а не на базе
BaseHTTPMiddleware) — иначе значение ContextVar не дошло бы до обработчика
эндпоинта.
"""
import contextvars
from typing import Optional

from fastapi import HTTPException

SUPPORTED_LANGS = ("ru", "uz", "en")
DEFAULT_LANG = "ru"

_current_lang: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_lang", default=DEFAULT_LANG
)


def set_current_lang(lang: Optional[str]) -> None:
    _current_lang.set(lang if lang in SUPPORTED_LANGS else DEFAULT_LANG)


def get_current_lang() -> str:
    return _current_lang.get()


# ─── Каталог сообщений: ключ -> {ru, uz, en} ─────────────────────────────
MESSAGES: dict[str, dict[str, str]] = {
    # Общая внутренняя ошибка (непредвиденный сбой, 500).
    "internal_error": {
        "ru": "Внутренняя ошибка сервера. Мы уже уведомлены, попробуйте позже.",
        "uz": "Server ichki xatosi. Bizga xabar berildi, keyinroq urinib koʻring.",
        "en": "Internal server error. We have been notified, please try again later.",
    },
    # Доступ / авторизация
    "auth_required": {
        "ru": "Требуется авторизация.",
        "uz": "Avtorizatsiya talab qilinadi.",
        "en": "Authorization required.",
    },
    "auth_invalid_token": {
        "ru": "Недействительный или истёкший пропуск. Войдите заново.",
        "uz": "Yaroqsiz yoki muddati oʻtgan kirish. Qaytadan kiring.",
        "en": "Invalid or expired session. Please sign in again.",
    },
    "user_not_found_or_inactive": {
        "ru": "Пользователь не найден или деактивирован.",
        "uz": "Foydalanuvchi topilmadi yoki oʻchirilgan.",
        "en": "User not found or deactivated.",
    },
    "forbidden_superadmin_only": {
        "ru": "Доступ только для суперадмина.",
        "uz": "Faqat platforma egasi uchun ruxsat.",
        "en": "Superadmin access only.",
    },
    "subscription_suspended": {
        "ru": "Доступ к агентству приостановлен: подписка неактивна. "
              "Обратитесь к владельцу платформы.",
        "uz": "Agentlikka kirish toʻxtatilgan: obuna faol emas. "
              "Platforma egasiga murojaat qiling.",
        "en": "Agency access suspended: subscription is inactive. "
              "Contact the platform owner.",
    },
    "forbidden_member_only": {
        "ru": "Доступ только для сотрудников агентства.",
        "uz": "Faqat agentlik xodimlari uchun ruxsat.",
        "en": "Agency members only.",
    },
    "forbidden_admin_only": {
        "ru": "Доступ только для администратора агентства.",
        "uz": "Faqat agentlik administratori uchun ruxsat.",
        "en": "Agency admin only.",
    },
    "forbidden_owner_only": {
        "ru": "Доступ только для главного администратора агентства.",
        "uz": "Faqat agentlikning bosh administratori uchun ruxsat.",
        "en": "Agency main admin only.",
    },
    # Агентства
    "cannot_assign_superadmin_as_admin": {
        "ru": "Нельзя назначить суперадмина администратором агентства.",
        "uz": "Platforma egasini agentlik administratori qilib tayinlab boʻlmaydi.",
        "en": "The platform owner cannot be assigned as an agency admin.",
    },
    "agency_not_found": {
        "ru": "Агентство не найдено.",
        "uz": "Agentlik topilmadi.",
        "en": "Agency not found.",
    },
    "subscription_end_date_required": {
        "ru": "Не указана дата окончания подписки.",
        "uz": "Obuna tugash sanasi koʻrsatilmagan.",
        "en": "Subscription end date is not specified.",
    },
    "unknown_action": {
        "ru": "Неизвестное действие.",
        "uz": "Nomaʼlum amal.",
        "en": "Unknown action.",
    },
    "agency_name_empty": {
        "ru": "Название агентства не может быть пустым.",
        "uz": "Agentlik nomi boʻsh boʻlishi mumkin emas.",
        "en": "Agency name cannot be empty.",
    },
    "user_already_in_another_agency": {
        "ru": "Этот пользователь уже состоит в другом агентстве.",
        "uz": "Bu foydalanuvchi allaqachon boshqa agentlikda.",
        "en": "This user already belongs to another agency.",
    },
    # Агенты (справочник)
    "agent_code_exists": {
        "ru": "Агент с кодом «{code}» уже существует в этом агентстве.",
        "uz": "«{code}» kodli agent bu agentlikda allaqachon mavjud.",
        "en": "An agent with code “{code}” already exists in this agency.",
    },
    "agent_not_found": {
        "ru": "Агент не найден.",
        "uz": "Agent topilmadi.",
        "en": "Agent not found.",
    },
    # Объекты
    "display_id_generation_failed": {
        "ru": "Не удалось сгенерировать номер объекта.",
        "uz": "Obyekt raqamini yaratib boʻlmadi.",
        "en": "Failed to generate the property number.",
    },
    "apartment_not_found": {
        "ru": "Объект не найден.",
        "uz": "Obyekt topilmadi.",
        "en": "Property not found.",
    },
    "invalid_apartment_status": {
        "ru": "Недопустимый статус объекта.",
        "uz": "Obyektning yaroqsiz holati.",
        "en": "Invalid property status.",
    },
    # Отправка / шаринг
    "share_via_bot_not_configured": {
        "ru": "Отправка через бота недоступна: не настроен токен бота.",
        "uz": "Bot orqali yuborish imkonsiz: bot tokeni sozlanmagan.",
        "en": "Sending via the bot is unavailable: bot token is not configured.",
    },
    "share_send_failed": {
        "ru": "Не удалось отправить. Откройте чат с ботом, нажмите «Старт» и повторите.",
        "uz": "Yuborib boʻlmadi. Bot bilan chatni oching, «Start» bosing va qayta urinib koʻring.",
        "en": "Failed to send. Open the chat with the bot, press “Start”, and try again.",
    },
    "share_not_configured": {
        "ru": "Отправка недоступна: не настроен токен бота.",
        "uz": "Yuborish imkonsiz: bot tokeni sozlanmagan.",
        "en": "Sending is unavailable: bot token is not configured.",
    },
    "share_prepare_failed": {
        "ru": "Не удалось подготовить отправку. Попробуйте ещё раз.",
        "uz": "Yuborishni tayyorlab boʻlmadi. Qayta urinib koʻring.",
        "en": "Failed to prepare sending. Please try again.",
    },
    # Вход / приглашения
    "telegram_login_not_configured": {
        "ru": "Вход через Telegram не настроен (не задан токен бота).",
        "uz": "Telegram orqali kirish sozlanmagan (bot tokeni berilmagan).",
        "en": "Telegram login is not configured (bot token is not set).",
    },
    "not_in_agency": {
        "ru": "Вы не привязаны ни к одному агентству. Обратитесь к администратору.",
        "uz": "Siz hech bir agentlikka biriktirilmagansiz. Administratorga murojaat qiling.",
        "en": "You are not linked to any agency. Contact your administrator.",
    },
    "access_deactivated": {
        "ru": "Ваш доступ деактивирован. Обратитесь к администратору.",
        "uz": "Sizning kirishingiz oʻchirilgan. Administratorga murojaat qiling.",
        "en": "Your access has been deactivated. Contact your administrator.",
    },
    "invite_code_generation_failed": {
        "ru": "Не удалось сгенерировать код приглашения, попробуйте ещё раз.",
        "uz": "Taklif kodini yaratib boʻlmadi, qayta urinib koʻring.",
        "en": "Failed to generate an invite code, please try again.",
    },
    "invite_not_found": {
        "ru": "Приглашение не найдено.",
        "uz": "Taklif topilmadi.",
        "en": "Invite not found.",
    },
    "invite_already_used": {
        "ru": "Это приглашение уже использовано.",
        "uz": "Bu taklif allaqachon ishlatilgan.",
        "en": "This invite has already been used.",
    },
    "invite_expired": {
        "ru": "Срок действия приглашения истёк.",
        "uz": "Taklif muddati tugagan.",
        "en": "The invite has expired.",
    },
    "superadmin_cannot_join": {
        "ru": "Владелец платформы не может вступать в агентство.",
        "uz": "Platforma egasi agentlikka qoʻshila olmaydi.",
        "en": "The platform owner cannot join an agency.",
    },
    "already_in_agency": {
        "ru": "Вы уже состоите в агентстве.",
        "uz": "Siz allaqachon agentlikdasiz.",
        "en": "You already belong to an agency.",
    },
    # Команда / роли
    "member_not_found": {
        "ru": "Сотрудник не найден.",
        "uz": "Xodim topilmadi.",
        "en": "Member not found.",
    },
    "cannot_disable_self": {
        "ru": "Нельзя отключить доступ самому себе.",
        "uz": "Oʻzingizning kirishingizni oʻchira olmaysiz.",
        "en": "You cannot disable your own access.",
    },
    "only_owner_manage_admins": {
        "ru": "Управлять администраторами может только главный администратор агентства.",
        "uz": "Administratorlarni faqat agentlikning bosh administratori boshqara oladi.",
        "en": "Only the agency main admin can manage admins.",
    },
    "cannot_change_owner": {
        "ru": "Главного администратора агентства изменить нельзя.",
        "uz": "Agentlikning bosh administratorini oʻzgartirib boʻlmaydi.",
        "en": "The agency main admin cannot be changed.",
    },
    "invalid_role": {
        "ru": "Недопустимая роль. Доступно: администратор агентства или агент.",
        "uz": "Yaroqsiz rol. Mavjud: agentlik administratori yoki agent.",
        "en": "Invalid role. Available: agency admin or agent.",
    },
    "only_owner_change_roles": {
        "ru": "Менять роли сотрудников может только главный администратор агентства.",
        "uz": "Xodimlar rollarini faqat agentlikning bosh administratori oʻzgartira oladi.",
        "en": "Only the agency main admin can change member roles.",
    },
    "cannot_change_own_role": {
        "ru": "Нельзя менять роль самому себе. Попросите другого администратора.",
        "uz": "Oʻz rolingizni oʻzgartira olmaysiz. Boshqa administratordan soʻrang.",
        "en": "You cannot change your own role. Ask another admin.",
    },
    "only_owner_transfer": {
        "ru": "Передать роль главного может только сам главный администратор.",
        "uz": "Bosh administrator rolini faqat bosh administratorning oʻzi topshira oladi.",
        "en": "Only the current main admin can transfer the main admin role.",
    },
    "already_owner": {
        "ru": "Вы уже главный администратор.",
        "uz": "Siz allaqachon bosh administratorsiz.",
        "en": "You are already the main admin.",
    },
    # Фотографии
    "no_photos_to_upload": {
        "ru": "Нет фото для загрузки.",
        "uz": "Yuklash uchun foto yoʻq.",
        "en": "No photos to upload.",
    },
    "photo_not_found": {
        "ru": "Фото не найдено.",
        "uz": "Foto topilmadi.",
        "en": "Photo not found.",
    },
    "only_http_links": {
        "ru": "Поддерживаются только ссылки http/https.",
        "uz": "Faqat http/https havolalar qoʻllab-quvvatlanadi.",
        "en": "Only http/https links are supported.",
    },
    "invalid_link": {
        "ru": "Некорректная ссылка.",
        "uz": "Notoʻgʻri havola.",
        "en": "Invalid link.",
    },
    "link_host_unresolved": {
        "ru": "Не удалось определить адрес ссылки.",
        "uz": "Havola manzilini aniqlab boʻlmadi.",
        "en": "Could not resolve the link address.",
    },
    "link_internal_blocked": {
        "ru": "Ссылка ведёт во внутреннюю сеть и заблокирована.",
        "uz": "Havola ichki tarmoqqa olib boradi va bloklangan.",
        "en": "The link points to an internal network and is blocked.",
    },
    "photo_too_large_mb": {
        "ru": "Фото больше {mb} МБ — слишком большое.",
        "uz": "Foto {mb} MB dan katta — juda katta.",
        "en": "The photo is larger than {mb} MB — too large.",
    },
    "only_images": {
        "ru": "Можно загружать только изображения.",
        "uz": "Faqat rasmlarni yuklash mumkin.",
        "en": "Only images can be uploaded.",
    },
    "no_photos_or_limit": {
        "ru": "Нет фото для загрузки или достигнут лимит.",
        "uz": "Yuklash uchun foto yoʻq yoki chegaraga yetildi.",
        "en": "No photos to upload or the limit has been reached.",
    },
    "file_too_large": {
        "ru": "Файл слишком большой.",
        "uz": "Fayl juda katta.",
        "en": "The file is too large.",
    },
    "empty_link": {
        "ru": "Пустая ссылка.",
        "uz": "Boʻsh havola.",
        "en": "Empty link.",
    },
    "import_only_telegram": {
        "ru": "Импорт работает только со ссылками Telegram (t.me/<канал>/<номер>).",
        "uz": "Import faqat Telegram havolalari bilan ishlaydi (t.me/<kanal>/<raqam>).",
        "en": "Import works only with Telegram links (t.me/<channel>/<number>).",
    },
    "link_open_failed": {
        "ru": "Не удалось открыть ссылку. Проверьте, что канал открытый.",
        "uz": "Havolani ochib boʻlmadi. Kanal ochiq ekanini tekshiring.",
        "en": "Could not open the link. Make sure the channel is public.",
    },
    "no_photos_in_post": {
        "ru": "По ссылке не найдено фотографий. Убедитесь, что в посте есть фото и канал открытый.",
        "uz": "Havolada fotosurat topilmadi. Postda foto borligiga va kanal ochiqligiga ishonch hosil qiling.",
        "en": "No photos found at the link. Make sure the post has photos and the channel is public.",
    },
    "photo_download_failed": {
        "ru": "Не удалось загрузить фото по ссылке.",
        "uz": "Havoladan fotoni yuklab boʻlmadi.",
        "en": "Failed to download the photo from the link.",
    },
    # Проверка данных входа Telegram (InitDataError)
    "init_data_empty": {
        "ru": "Пустые данные входа.",
        "uz": "Boʻsh kirish maʼlumotlari.",
        "en": "Empty login data.",
    },
    "init_data_bad_format": {
        "ru": "Некорректный формат данных входа.",
        "uz": "Kirish maʼlumotlari formati notoʻgʻri.",
        "en": "Invalid login data format.",
    },
    "init_data_no_signature": {
        "ru": "В данных входа отсутствует подпись.",
        "uz": "Kirish maʼlumotlarida imzo yoʻq.",
        "en": "Login data is missing a signature.",
    },
    "init_data_bad_signature": {
        "ru": "Подпись данных входа недействительна.",
        "uz": "Kirish maʼlumotlari imzosi yaroqsiz.",
        "en": "Login data signature is invalid.",
    },
    "init_data_bad_date": {
        "ru": "Некорректная дата входа.",
        "uz": "Kirish sanasi notoʻgʻri.",
        "en": "Invalid login date.",
    },
    "init_data_expired": {
        "ru": "Данные входа устарели, откройте приложение заново.",
        "uz": "Kirish maʼlumotlari eskirgan, ilovani qaytadan oching.",
        "en": "Login data has expired, please reopen the app.",
    },
    "init_data_bad_user": {
        "ru": "Некорректные данные пользователя.",
        "uz": "Foydalanuvchi maʼlumotlari notoʻgʻri.",
        "en": "Invalid user data.",
    },
    "init_data_no_user_id": {
        "ru": "В данных входа нет идентификатора пользователя.",
        "uz": "Kirish maʼlumotlarida foydalanuvchi identifikatori yoʻq.",
        "en": "Login data has no user identifier.",
    },
    # Валидация форм (pydantic, 422)
    "agent_name_empty": {
        "ru": "Имя агента не может быть пустым.",
        "uz": "Agent ismi boʻsh boʻlishi mumkin emas.",
        "en": "Agent name cannot be empty.",
    },
    "agent_code_empty": {
        "ru": "Код агента не может быть пустым.",
        "uz": "Agent kodi boʻsh boʻlishi mumkin emas.",
        "en": "Agent code cannot be empty.",
    },
    "agent_code_too_long": {
        "ru": "Код агента не длиннее 5 символов.",
        "uz": "Agent kodi 5 belgidan oshmasligi kerak.",
        "en": "Agent code must be at most 5 characters.",
    },
    "agent_code_alnum": {
        "ru": "Код агента может содержать только буквы и цифры.",
        "uz": "Agent kodi faqat harf va raqamlardan iborat boʻlishi mumkin.",
        "en": "Agent code may contain only letters and digits.",
    },
    "value_negative": {
        "ru": "Значение не может быть отрицательным.",
        "uz": "Qiymat manfiy boʻlishi mumkin emas.",
        "en": "Value cannot be negative.",
    },
    "value_empty": {
        "ru": "Значение не может быть пустым.",
        "uz": "Qiymat boʻsh boʻlishi mumkin emas.",
        "en": "Value cannot be empty.",
    },
    "invite_role_invalid": {
        "ru": "Роль должна быть 'agent' (агент) или 'agency_admin' (администратор).",
        "uz": "Rol 'agent' (agent) yoki 'agency_admin' (administrator) boʻlishi kerak.",
        "en": "Role must be 'agent' or 'agency_admin'.",
    },
    "invite_days_range": {
        "ru": "Срок приглашения — от 1 до 365 дней.",
        "uz": "Taklif muddati — 1 dan 365 kungacha.",
        "en": "Invite validity must be from 1 to 365 days.",
    },
    "invite_code_empty": {
        "ru": "Код приглашения не может быть пустым.",
        "uz": "Taklif kodi boʻsh boʻlishi mumkin emas.",
        "en": "Invite code cannot be empty.",
    },
}


def translate(key: str, lang: Optional[str] = None, **params) -> str:
    """Перевести сообщение по ключу на язык lang (по умолчанию — язык запроса)."""
    lang = lang if lang in SUPPORTED_LANGS else get_current_lang()
    by_lang = MESSAGES.get(key)
    if by_lang is None:
        text = key  # неизвестный ключ — возвращаем как есть (заметно при отладке)
    else:
        text = by_lang.get(lang) or by_lang.get(DEFAULT_LANG) or key
    if params:
        try:
            text = text.format(**params)
        except Exception:  # noqa: BLE001
            pass
    return text


class AppError(HTTPException):
    """
    HTTP-ошибка с локализованным сообщением. detail переводится на язык
    текущего запроса в момент создания исключения.
    """

    def __init__(self, key: str, status_code: int = 400, *, headers=None, **params):
        self.key = key
        self.params = params
        super().__init__(
            status_code=status_code,
            detail=translate(key, **params),
            headers=headers,
        )


class LanguageMiddleware:
    """
    «Чистый» ASGI-middleware: читает X-Lang из заголовков и кладёт язык в
    ContextVar на время обработки запроса. Сделан не на BaseHTTPMiddleware,
    чтобы значение ContextVar корректно дошло до обработчика эндпоинта.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        lang = DEFAULT_LANG
        for name, value in scope.get("headers", []):
            if name == b"x-lang":
                candidate = value.decode("latin-1").strip().lower()
                if candidate in SUPPORTED_LANGS:
                    lang = candidate
                break
        token = _current_lang.set(lang)
        try:
            await self.app(scope, receive, send)
        finally:
            _current_lang.reset(token)
