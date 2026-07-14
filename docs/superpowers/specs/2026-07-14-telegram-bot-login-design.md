# Вход через Telegram-бота (native app)

**Дата:** 2026-07-14
**Статус:** утверждён, готов к плану реализации
**Ветка:** `feature/native-auth`

## Проблема

Нативному приложению Realty AI нужен вход, который попадает в **существующий**
аккаунт пользователя. Google/Apple создают отдельный чистый аккаунт и не
связываются с уже имеющимся Telegram-аккаунтом суперадмина. Нужен способ войти в
нативке под тем же аккаунтом, что и в Telegram Mini App.

## Решение

Вход через отдельного Telegram-бота **@realtyloginbot** с подтверждением по кнопке.
`telegram_id` — глобальный ID Telegram-аккаунта (одинаковый в любом боте), поэтому
вход через отдельного бота всё равно находит существующий аккаунт.

### Принцип изоляции
Отдельный бот, отдельный токен, новые таблицы и эндпоинты. Существующий вход
Mini App (через initData) **не трогается**. Деплой: `feature/native-auth` → `main`.

## Поток

```
Нативка                Бэкенд                     @realtyloginbot
  │ tap "Войти через TG"  │                              │
  ├──POST /start─────────>│ создаёт код (TTL 5 мин)      │
  │<──{code, deep_link}───┤                              │
  │ открывает t.me/realtyloginbot?start=login_<code>     │
  │──────────────────────────────────────────────────-->│ /start
  │                       │<──webhook: /start login_code─┤
  │                       ├──sendMessage «Это вы?» + кнопка «✅ Подтвердить»──>│
  │ (опрашивает poll)     │                              │ юзер жмёт ✅
  │                       │<──webhook: callback confirm──┤
  │                       │  привязывает telegram_id     │
  ├──POST /poll──────────>│ находит/создаёт аккаунт      │
  │<──{status:confirmed,  │  по telegram_id → JWT        │
  │    token, user}───────┤  (тот же аккаунт, что в MiniApp)
  │ сохраняет сессию, входит
```

## Бэкенд (слои api → service → repo → db)

### Данные
Таблица `tg_login_codes` (миграция 0044):
- `id` PK
- `code` — unique, indexed, 128-бит случайный hex (32 символа)
- `status` — `pending` → `confirmed` → `consumed`; терминальные `cancelled`, `expired`
- `telegram_id` — nullable, ставится на confirm
- `tg_first_name`, `tg_last_name` — nullable, из `callback_query.from`
- `created_at`, `expires_at` (created_at + 5 мин)

### Эндпоинты
- **`POST /api/v1/auth/telegram/start`** → создаёт код, возвращает
  `{code, deep_link, expires_in}`. Rate-limit по IP.
- **`POST /api/v1/telegram/webhook`** → приёмник апдейтов бота:
  - `message` с текстом `/start login_<code>`: если код валиден/pending/не истёк →
    `sendMessage` с inline-кнопками «✅ Подтвердить вход» (`confirm_<code>`) и
    «❌ Отмена» (`cancel_<code>`).
  - `callback_query` с `confirm_<code>`: помечает код `confirmed`, привязывает
    `telegram_id` + имя из `callback_query.from`; редактирует сообщение на
    «✅ Вход подтверждён». `answerCallbackQuery`.
  - `callback_query` с `cancel_<code>`: помечает `cancelled`.
  - Всегда быстро возвращает 200. Аутентификация — заголовок
    `X-Telegram-Bot-Api-Secret-Token` (устанавливается при `setWebhook`).
- **`POST /api/v1/auth/telegram/poll`** `{code}`:
  - `pending` / не найден → `{status: "pending"}`; истёк → `{status: "expired"}`.
  - `confirmed` → находит **или создаёт** пользователя по `telegram_id`
    (переиспользует существующую логику Telegram-входа → тот же аккаунт, что в
    Mini App), выдаёт JWT через `build_auth_response`, помечает код `consumed`
    (одноразовый), возвращает `{status: "confirmed", ...authResponse}`.
  - Rate-limit по IP.

### Файлы
- `backend/app/repositories/tg_login_repo.py` — CRUD по `tg_login_codes`.
- `backend/app/services/tg_login_service.py` — create_code, handle_start,
  handle_confirm, poll_code (выдаёт auth).
- `backend/app/api/routes/telegram_login.py` — start + poll.
- `backend/app/api/routes/telegram_webhook.py` — webhook.
- `backend/app/db/models/tg_login_code.py` — модель.
- `backend/alembic/versions/0044_tg_login_codes.py` — миграция.
- `backend/app/config.py` — `login_bot_token`, `login_bot_username` (`realtyloginbot`),
  `telegram_webhook_secret`.

### Переиспользование
- Резолв пользователя по `telegram_id` — та же ветка, что в существующем
  initData-входе (получить-или-создать), чтобы нативка попадала в **тот же**
  аккаунт. Без проверки подписи initData (webhook уже аутентифицировал `telegram_id`).
- Отправка сообщений — существующий `telegram_service` (но с токеном
  `login_bot_token`, а не прод-бота).
- Выдача сессии — существующий `build_auth_response`.

## Безопасность
- Код 128-бит случайный → перебор невозможен.
- Webhook защищён secret-заголовком Telegram.
- TTL 5 мин; истёкшие коды отклоняются.
- Одноразовый: poll помечает `consumed` после выдачи JWT.
- Rate-limit на `/start` и `/poll` по IP (существующий `ratelimit.py`).
- Кнопка подтверждения: украденный код без нажатия живого юзера бесполезен.

## Нативка (frontend)
- Кнопка «Войти через Telegram» на `NativeLoginScreen`.
- Поток: `/start` → открыть `deep_link` → опрашивать `/poll` каждые ~2 сек до
  истечения → на `confirmed` тот же `applyAuth` + `saveSession`, что у Google.
- Статус на экране: «Подтвердите вход в Telegram…». Обработка `expired`
  (показать «Время вышло, попробуйте снова»).
- Переиспользует существующую персистентность сессии и `extraHeaders`.

## Тесты
В стиле `backend/tests/test_native_auth_routes.py` (минимальное FastAPI-приложение):
- генерация / истечение / одноразовость кода;
- состояния `poll` (pending / expired / confirmed);
- webhook confirm (симуляция апдейтов `message` и `callback_query`);
- отклонение webhook по неверному secret.

## Настройка при деплое
- Один раз `setWebhook` на `https://pc1.tailcdc07f.ts.net/api/v1/telegram/webhook`
  с `secret_token`.
- Добавить `LOGIN_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET` в `.env` на pc1 и в
  `docker-compose.yml` (passthrough).

## Вне области (YAGNI)
- SMS-подтверждение номера — отдельная задача.
- iOS / Apple — отдельная задача.
- Слияние Google-аккаунта с Telegram-аккаунтом по номеру — отдельная задача.
