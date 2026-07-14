"""
Конфигурация backend. Все настройки читаются из переменных окружения
(или из файла .env). Никаких секретов в коде.

Часть 1B: добавились настройки для входа через Telegram.
Все они НЕОБЯЗАТЕЛЬНЫ, чтобы проект запускался даже без токена бота
(тогда вход через Telegram просто вернёт понятную ошибку, а структуру
API всё равно можно посмотреть в /docs).
"""
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ─── База данных ────────────────────────────────────────────────────
    # ВНИМАНИЕ: это значение по умолчанию — ТОЛЬКО для локального запуска без
    # Docker. В реальном развёртывании DATABASE_URL обязательно задаётся через
    # переменную окружения с НЕугадываемым паролем (см. docker-compose.yml, где
    # пароль приходит из POSTGRES_PASSWORD в .env). Пароль ниже — заведомо
    # «одноразовый» плейсхолдер: его нельзя использовать в проде.
    database_url: str = "postgresql+psycopg://realty:dev_only_change_me@localhost:5432/realty"

    # ─── Telegram / Безопасность ────────────────────────────────────────
    # Токен бота от @BotFather. Нужен для проверки подлинности входа.
    bot_token: Optional[str] = None
    # Секрет для подписи пропусков (JWT). Если не задан — сгенерируется
    # случайный при старте (для локальной разработки этого достаточно).
    jwt_secret: Optional[str] = None
    # Сколько минут действует выданный пропуск (по умолчанию 2 часа).
    # Короткий срок жизни ограничивает окно для повторного использования
    # перехваченного пропуска (см. также init_data_max_age_seconds).
    jwt_expire_minutes: int = 120
    # Сколько минут действует refresh-пропуск (по умолчанию 30 дней). Им клиент
    # обновляет короткий access-токен без повторной проверки initData — это
    # убирает «тихий тупик» длинных сессий (>1 часа).
    refresh_expire_minutes: int = 43200
    # Сколько доверенных прокси стоит ПЕРЕД приложением (Caddy = 1; если ещё и
    # туннель добавляет свой заголовок — увеличьте до 2). Реальный IP клиента
    # берётся из X-Forwarded-For с этой позиции СПРАВА — так клиент не может
    # подделать свой адрес, дописав фейковые значения слева (обход rate limit).
    trusted_proxy_count: int = 1
    # Telegram ID владельца платформы. Этот человек станет суперадмином
    # автоматически при запуске. (Совместимость: одиночный владелец.)
    superadmin_telegram_id: Optional[int] = None
    # Несколько владельцев платформы: Telegram ID через запятую
    # (SUPERADMIN_TELEGRAM_IDS="111,222"). Объединяется с superadmin_telegram_id.
    # Все перечисленные становятся равноправными суперадминами; суперадмины НЕ из
    # списка при старте теряют права (см. ensure_superadmins в main.py).
    # Храним строкой и парсим сами — так надёжнее, чем list через pydantic-env.
    superadmin_telegram_ids: Optional[str] = None
    # Имя бота без @ (например "my_realty_bot"). Нужно только для красивой
    # ссылки-приглашения вида https://t.me/<bot>?startapp=<код>. Если не задано —
    # приглашение всё равно работает, просто сотрудник вводит код вручную.
    bot_username: Optional[str] = None
    # Контакт поддержки: ссылка, которую открывает кнопка «Поддержка» в приложении
    # (например "https://t.me/username" — твой Telegram). Пусто = кнопка скрыта.
    support_url: str = ""
    # Максимальный "возраст" данных входа от Telegram (защита от повторного
    # использования). По умолчанию 1 час: вместе с одноразовой защитой
    # (anti-replay по hash) это резко сужает окно для переигрывания
    # перехваченного initData.
    init_data_max_age_seconds: int = 3600

    # Папка для секретов приложения (например, автогенерируемый JWT_SECRET).
    # ВАЖНО: это ОТДЕЛЬНЫЙ том, НЕ совпадающий с photos_dir и НЕ попадающий в
    # резервные копии — секрет не должен лежать рядом с пользовательским
    # контентом и не должен утекать вместе с бэкапами.
    secret_dir: str = "/secrets"

    # Выставлять ли интерактивную документацию (/docs, /redoc, /openapi.json).
    # По умолчанию ВЫКЛЮЧЕНА (безопасно для прода). Включай только для локальной
    # разработки через ENABLE_DOCS=true.
    enable_docs: bool = False

    # Папка для хранения загруженных фотографий объектов (внутри контейнера).
    # Монтируется на Docker-том, чтобы фото не пропадали между перезапусками.
    photos_dir: str = "/data/photos"
    # Бэкенд хранилища фото: "local" (диск, сейчас) или "s3" (в будущем).
    # Ссылки на фото всегда стабильны (/api/v1/photos/<ключ>) и не зависят от
    # бэкенда — переключение не ломает ранее выданные ссылки (в т.ч. в Google Sheets).
    photo_storage_backend: str = "local"
    # Версия приложения для /health (можно переопределить через APP_VERSION в .env).
    app_version: str = "dev"

    # Публичный HTTPS-адрес приложения (тот же, что у туннеля ngrok). Нужен,
    # чтобы при «поделиться» Telegram мог забрать фото по абсолютной ссылке.
    public_base_url: str = "https://pagan-crawling-retiring.ngrok-free.dev"

    # За сколько дней до окончания подписки начинать предупреждать владельца
    # агентства (бот пишет ему заранее). 0 — отключить предупреждения.
    subscription_warn_days: int = 3

    # Блокировать ли доступ агентствам с неактивной подпиской (заморожено/
    # просрочено). По умолчанию ВЫКЛЮЧЕНО (тарифы отключены с 2026-07): доступ
    # никогда не блокируется. Когда вернутся платные тарифы — включить
    # SUBSCRIPTION_GATING_ENABLED=true (гейт восстановится в require_* гвардах).
    # Флаг сделан честным (а не «пустой функцией»), чтобы поведение было явным и
    # тестируемым, а повторное включение — одной переменной окружения.
    subscription_gating_enabled: bool = False

    # Слать ли суперадмину уведомление в бот о непредвиденных сбоях сервера
    # (ошибки 500). По умолчанию включено; работает, только если задан BOT_TOKEN
    # и SUPERADMIN_TELEGRAM_ID.
    error_alerts_enabled: bool = True

    # ─── Импорт объявления по ссылке (AI-разбор) ────────────────────────
    # Ключ Google AI Studio (Gemini). Если не задан — импорт вернёт понятную ошибку.
    gemini_api_key: Optional[str] = None
    # Модель Gemini для извлечения полей объекта из текста объявления.
    # gemini-1.5-* на новых ключах недоступна — используем актуальную 2.5-flash.
    # Дешёвая модель ВЕЗДЕ (по просьбе пользователя 2026-06-23): и импорт по
    # ссылке, и массовый/фоновый — на flash-lite. Если для импорта по ссылке
    # когда-нибудь захочется точность повыше — поставить сюда "gemini-2.5-flash".
    import_ai_model: str = "gemini-2.5-flash-lite"
    # Массовый/фоновый импорт. Отдельная настройка оставлена на случай, если
    # захотим разнести модели; сейчас совпадает с основной — дёшево везде.
    import_ai_model_bulk: str = "gemini-2.5-flash-lite"
    # Запасной/основной ИИ-провайдер OpenRouter (OpenAI-совместимый). Бесплатные
    # модели (`...:free`) — подстраховка, когда у Gemini нет денег/лимита.
    openrouter_api_key: Optional[str] = None
    openrouter_model: str = "openai/gpt-oss-120b:free"
    # Порядок ИИ-провайдеров для импорта (через запятую): пробуем по очереди,
    # берём первого, кто ответит. Допустимо: "gemini", "openrouter". Пример:
    # "openrouter" (пока Gemini без денег) или "gemini,openrouter" (Gemini + запас).
    import_ai_providers: str = "gemini"
    # Рендер JS-страниц безголовым Chromium (Playwright) — нужен для сайтов-
    # одностраничников (joymee, OLX и пр.), где данные подгружаются скриптами.
    # Если браузер не установлен — импорт тихо откатывается на обычный HTTP.
    import_browser_render: bool = True
    import_browser_timeout_ms: int = 40000

    # ─── Синхронизация с Google Sheets (OAuth) ──────────────────────────
    # Учётные данные OAuth-приложения платформы (одни на всех клиентов).
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None

    # ─── Вход из нативного приложения (Google/Apple, 2026-07) ────────────
    # OAuth client_id нативного приложения — это ожидаемый `aud` в ID-token'е.
    # Токен принимаем, только если его aud совпал с одним из НАШИХ id (иначе это
    # токен для чужого приложения). У платформ Android/iOS/Web — разные client_id.
    google_ios_client_id: Optional[str] = None
    google_android_client_id: Optional[str] = None
    google_web_client_id: Optional[str] = None
    # Apple: aud нативного токена — bundle id приложения; веб-входа — service id.
    apple_bundle_id: Optional[str] = None
    apple_service_id: Optional[str] = None
    # Разрешённые Origin'ы для CORS (нативный webview + возможный веб-клиент),
    # через запятую. Telegram Mini App живёт на одном origin с бэком и CORS не
    # требует, поэтому по умолчанию пусто (ничего лишнего не открываем).
    cors_origins: str = ""

    # ─── Вход через Telegram-бота (нативное приложение, 2026-07) ─────────
    # ОТДЕЛЬНЫЙ бот только для входа в нативку (@realtyloginbot). Прод-бот
    # (bot_token) при этом не трогается — полная изоляция. Пусто → вход через
    # Telegram-бота не сконфигурирован (роут /auth/telegram/start ответит 503).
    login_bot_token: Optional[str] = None
    login_bot_username: Optional[str] = None
    # Секрет для проверки, что запрос на webhook пришёл именно от Telegram
    # (заголовок X-Telegram-Bot-Api-Secret-Token, задаётся при setWebhook).
    telegram_webhook_secret: Optional[str] = None

    # ─── Шифрование секретов в БД ────────────────────────────────────────
    # Ключ Fernet для шифрования секретов в базе (Google refresh-токены),
    # см. app/core/crypto.py. Хранится в .env на сервере — вне базы и бэкапов.
    # Сгенерировать: python -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
    # Если не задан — секреты хранятся как есть (только для разработки/тестов).
    app_encryption_key: Optional[str] = None

    # Окружение: "dev" (по умолчанию) или "prod". В prod включаются жёсткие
    # проверки (fail-closed): JWT_SECRET обязателен (иначе при нескольких
    # воркерах/хостах автосекрет разойдётся → массовый разлогин), и запрещено
    # хранить секреты в БД без ключа шифрования. Задаётся переменной ENV.
    env: str = "dev"

    @field_validator(
        "bot_token", "jwt_secret", "bot_username", "gemini_api_key",
        "openrouter_api_key", "google_client_id", "google_client_secret",
        "google_ios_client_id", "google_android_client_id", "google_web_client_id",
        "apple_bundle_id", "apple_service_id",
        "login_bot_token", "login_bot_username", "telegram_webhook_secret",
        "app_encryption_key", mode="before",
    )
    @classmethod
    def _empty_string_to_none(cls, value):
        # Пустая строка в .env (например BOT_TOKEN=) трактуется как "не задано".
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @field_validator("superadmin_telegram_id", mode="before")
    @classmethod
    def _empty_int_to_none(cls, value):
        # Пустую строку для числового поля тоже считаем "не задано",
        # иначе запуск упал бы с ошибкой парсинга.
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return None
        return value

    @property
    def is_prod(self) -> bool:
        """Прод-режим (жёсткие проверки безопасности). Включается ENV=prod."""
        return (self.env or "").strip().lower() in ("prod", "production")

    def google_audiences(self) -> list[str]:
        """Наши Google client_id (ожидаемые `aud`). Пусто → вход через Google не
        сконфигурирован (роут ответит 503)."""
        return [
            c for c in (
                self.google_ios_client_id,
                self.google_android_client_id,
                self.google_web_client_id,
            ) if c
        ]

    def apple_audiences(self) -> list[str]:
        """Наши Apple client_id (bundle id / service id) — ожидаемые `aud`."""
        return [c for c in (self.apple_bundle_id, self.apple_service_id) if c]

    def cors_origin_list(self) -> list[str]:
        """Разрешённые Origin'ы из CORS_ORIGINS (через запятую)."""
        return [o.strip() for o in (self.cors_origins or "").split(",") if o.strip()]

    def superadmin_ids(self) -> set[int]:
        """Все Telegram ID владельцев платформы (из обоих источников настроек)."""
        ids: set[int] = set()
        if self.superadmin_telegram_id:
            ids.add(int(self.superadmin_telegram_id))
        if self.superadmin_telegram_ids:
            for part in str(self.superadmin_telegram_ids).split(","):
                part = part.strip()
                if not part:
                    continue
                try:
                    ids.add(int(part))
                except ValueError:
                    pass
        return ids


settings = Settings()
