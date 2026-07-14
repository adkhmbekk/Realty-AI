# Telegram Bot-Confirmation Login Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дать нативному приложению вход через отдельного Telegram-бота (@realtyloginbot) с подтверждением по кнопке, попадающий в существующий аккаунт пользователя по `telegram_id`.

**Architecture:** Приложение просит у бэка одноразовый код → открывает `t.me/realtyloginbot?start=login_<code>` → пользователь жмёт «✅ Подтвердить» в боте → webhook привязывает `telegram_id` → приложение опрашивает `/poll` и получает обычную сессию (JWT). Всё изолировано от прод-бота: отдельный токен, новые таблицы/эндпоинты, существующий initData-вход не трогается.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (sync), PostgreSQL, Alembic, httpx (уже в зависимостях), Capacitor 8 / React (Vite).

## Global Constraints

- Никаких новых зависимостей (httpx, pyjwt уже есть).
- Отдельный бот: отправка сообщений входа идёт ТОЛЬКО через `settings.login_bot_token`, НИКОГДА через `settings.bot_token` (прод-бот).
- Существующий вход `POST /auth/telegram` (initData) и вся Mini-App логика не меняются.
- Комментарии на русском, в стиле окружающего кода.
- Миграция 0044 ревизирует `0043_native_oauth_identities`.
- Код одноразовый, 128-бит случайный (`secrets.token_hex(16)`), TTL 5 минут.
- Webhook аутентифицируется заголовком `X-Telegram-Bot-Api-Secret-Token` == `settings.telegram_webhook_secret`.
- Все команды выполняются из `C:/Users/Adhambek/Documents/GitHub/Realty-AI`, ветка `feature/native-auth`. Тесты: `cd backend && python -m pytest`.

---

## File Structure

- Create `backend/app/db/models/tg_login_code.py` — ORM-модель `TgLoginCode`.
- Modify `backend/app/db/models/__init__.py` — зарегистрировать модель.
- Create `backend/alembic/versions/0044_tg_login_codes.py` — миграция таблицы.
- Create `backend/app/repositories/tg_login_repo.py` — доступ к таблице.
- Modify `backend/app/config.py` — `login_bot_token`, `login_bot_username`, `telegram_webhook_secret`.
- Modify `backend/app/services/auth_service.py` — `login_with_telegram_id`.
- Create `backend/app/services/tg_login_service.py` — генерация кода, обработка апдейтов, poll.
- Create `backend/app/schemas/telegram_login.py` — схемы start/poll.
- Create `backend/app/api/routes/telegram_login.py` — `/auth/telegram/start`, `/auth/telegram/poll`.
- Create `backend/app/api/routes/telegram_webhook.py` — `/telegram/webhook`.
- Modify `backend/app/api/router.py` — подключить два новых роутера.
- Create tests: `backend/tests/test_tg_login_repo.py`, `test_tg_login_service.py`, `test_tg_login_routes.py`.
- Modify `frontend/src/App.tsx` — `telegramSignIn` + кнопка в `NativeLoginScreen`.
- Modify `docker-compose.yml` — passthrough трёх переменных.

---

## Task 1: Модель `TgLoginCode` + миграция

**Files:**
- Create: `backend/app/db/models/tg_login_code.py`
- Modify: `backend/app/db/models/__init__.py`
- Create: `backend/alembic/versions/0044_tg_login_codes.py`
- Test: `backend/tests/test_tg_login_repo.py` (создаётся в Task 2; здесь проверяем через существующий `db`-фикстур в шаге)

**Interfaces:**
- Produces: класс `TgLoginCode` с полями `id:int`, `code:str`, `status:str`, `telegram_id:Optional[int]`, `tg_first_name:Optional[str]`, `tg_last_name:Optional[str]`, `created_at:datetime`, `expires_at:datetime`.

- [ ] **Step 1: Написать провальный тест (таблица существует, вставка работает)**

Создать `backend/tests/test_tg_login_repo.py`:

```python
"""tg_login_codes: модель и доступ к данным (одноразовые коды входа через бота)."""
from datetime import datetime, timedelta, timezone

from app.db.models.tg_login_code import TgLoginCode


def test_model_insert_and_defaults(db):
    row = TgLoginCode(
        code="abc123",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    assert row.id is not None
    assert row.status == "pending"
    assert row.telegram_id is None
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `cd backend && python -m pytest tests/test_tg_login_repo.py::test_model_insert_and_defaults -v`
Expected: FAIL с `ModuleNotFoundError: No module named 'app.db.models.tg_login_code'`

- [ ] **Step 3: Создать модель**

Создать `backend/app/db/models/tg_login_code.py`:

```python
"""
Таблица "tg_login_codes" — одноразовые коды входа в нативное приложение через
отдельного Telegram-бота (@realtyloginbot).

Поток: приложение создаёт код (pending) → открывает t.me/бот?start=login_<code>
→ пользователь жмёт «Подтвердить» в боте → webhook помечает код confirmed и
привязывает telegram_id → приложение опрашивает /poll → код становится consumed
(одноразовый). Истёкшие/отменённые коды не выдают сессию.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TgLoginCode(Base):
    __tablename__ = "tg_login_codes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # Одноразовый секрет из ссылки (128 бит, hex). Уникален, ищем по нему.
    code: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    # pending → confirmed → consumed; терминальные cancelled / expired.
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending", server_default=text("'pending'")
    )
    # Заполняется при подтверждении (из callback_query.from) — чей это вход.
    telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    tg_first_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    tg_last_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Момент истечения (created_at + TTL). После него код не подтвердить и не выдать.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

- [ ] **Step 4: Зарегистрировать модель в реестре**

В `backend/app/db/models/__init__.py` добавить импорт (после строки `from app.db.models.task import Task`) и элемент в `__all__`:

```python
from app.db.models.tg_login_code import TgLoginCode
```

И в списке `__all__` добавить строку `"TgLoginCode",` (рядом с `"Task",`).

- [ ] **Step 5: Запустить тест — убедиться, что проходит**

Run: `cd backend && python -m pytest tests/test_tg_login_repo.py::test_model_insert_and_defaults -v`
Expected: PASS

- [ ] **Step 6: Создать миграцию**

Создать `backend/alembic/versions/0044_tg_login_codes.py`:

```python
"""tg_login_codes: одноразовые коды входа через Telegram-бота

Additive. Нативное приложение входит через отдельного бота (@realtyloginbot) с
подтверждением по кнопке. Таблица хранит короткоживущие (5 мин) одноразовые коды:
приложение создаёт код, бот его подтверждает (webhook), приложение опрашивает и
получает сессию. Ничего в существующих таблицах не меняется.

Revision ID: 0044_tg_login_codes
Revises: 0043_native_oauth_identities
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0044_tg_login_codes"
down_revision: Union[str, Sequence[str], None] = "0043_native_oauth_identities"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tg_login_codes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("tg_first_name", sa.String(), nullable=True),
        sa.Column("tg_last_name", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("uq_tg_login_codes_code", "tg_login_codes", ["code"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_tg_login_codes_code", table_name="tg_login_codes")
    op.drop_table("tg_login_codes")
```

- [ ] **Step 7: Проверить, что миграция консистентна (голова одна)**

Run: `cd backend && python -m alembic heads`
Expected: одна голова — `0044_tg_login_codes (head)`. Если alembic требует БД/окружения и падает на подключении — пропустить (миграция применится при старте контейнера); достаточно, что файл-ревизия ссылается на `0043_native_oauth_identities`.

- [ ] **Step 8: Commit**

```bash
git add backend/app/db/models/tg_login_code.py backend/app/db/models/__init__.py backend/alembic/versions/0044_tg_login_codes.py backend/tests/test_tg_login_repo.py
git commit -m "feat(auth): tg_login_codes model + migration for bot login"
```

---

## Task 2: Репозиторий `tg_login_repo`

**Files:**
- Create: `backend/app/repositories/tg_login_repo.py`
- Test: `backend/tests/test_tg_login_repo.py` (дополняем)

**Interfaces:**
- Consumes: `TgLoginCode` (Task 1).
- Produces:
  - `create(db, code: str, expires_at: datetime) -> TgLoginCode`
  - `get_by_code(db, code: str) -> Optional[TgLoginCode]`

- [ ] **Step 1: Написать провальный тест**

Добавить в `backend/tests/test_tg_login_repo.py`:

```python
from app.repositories import tg_login_repo


def test_create_and_get_by_code(db):
    exp = datetime.now(timezone.utc) + timedelta(minutes=5)
    row = tg_login_repo.create(db, code="xyz789", expires_at=exp)
    db.commit()
    assert row.id is not None
    got = tg_login_repo.get_by_code(db, "xyz789")
    assert got is not None and got.id == row.id
    assert tg_login_repo.get_by_code(db, "nope") is None
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `cd backend && python -m pytest tests/test_tg_login_repo.py::test_create_and_get_by_code -v`
Expected: FAIL с `ModuleNotFoundError: No module named 'app.repositories.tg_login_repo'`

- [ ] **Step 3: Создать репозиторий**

Создать `backend/app/repositories/tg_login_repo.py`:

```python
"""
Доступ к данным одноразовых кодов входа через Telegram-бота (tg_login_codes).
Только этот слой ходит в БД напрямую — бизнес-логика в tg_login_service.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.tg_login_code import TgLoginCode


def create(db: Session, code: str, expires_at: datetime) -> TgLoginCode:
    row = TgLoginCode(code=code, status="pending", expires_at=expires_at)
    db.add(row)
    db.flush()  # получить сгенерированный id
    return row


def get_by_code(db: Session, code: str) -> Optional[TgLoginCode]:
    return db.execute(
        select(TgLoginCode).where(TgLoginCode.code == code)
    ).scalar_one_or_none()
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `cd backend && python -m pytest tests/test_tg_login_repo.py -v`
Expected: PASS (оба теста)

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories/tg_login_repo.py backend/tests/test_tg_login_repo.py
git commit -m "feat(auth): tg_login_repo (create/get_by_code)"
```

---

## Task 3: Настройки бота входа

**Files:**
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_tg_login_config.py`

**Interfaces:**
- Produces: `settings.login_bot_token: Optional[str]`, `settings.login_bot_username: Optional[str]`, `settings.telegram_webhook_secret: Optional[str]`.

- [ ] **Step 1: Написать провальный тест**

Создать `backend/tests/test_tg_login_config.py`:

```python
"""Настройки входа через Telegram-бота присутствуют и по умолчанию не заданы."""
from app.config import Settings


def test_login_bot_settings_default_none():
    s = Settings(_env_file=None)
    assert s.login_bot_token is None
    assert s.login_bot_username is None
    assert s.telegram_webhook_secret is None


def test_login_bot_empty_string_is_none():
    s = Settings(_env_file=None, LOGIN_BOT_TOKEN="", TELEGRAM_WEBHOOK_SECRET="")
    assert s.login_bot_token is None
    assert s.telegram_webhook_secret is None
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `cd backend && python -m pytest tests/test_tg_login_config.py -v`
Expected: FAIL (`AttributeError: 'Settings' object has no attribute 'login_bot_token'`)

- [ ] **Step 3: Добавить настройки**

В `backend/app/config.py`, сразу после блока «Вход из нативного приложения (Google/Apple…)» — после строки `cors_origins: str = ""` (строка ~154) — добавить:

```python

    # ─── Вход через Telegram-бота (нативное приложение, 2026-07) ─────────
    # ОТДЕЛЬНЫЙ бот только для входа в нативку (@realtyloginbot). Прод-бот
    # (bot_token) при этом не трогается — полная изоляция. Пусто → вход через
    # Telegram-бота не сконфигурирован (роут /auth/telegram/start ответит 503).
    login_bot_token: Optional[str] = None
    login_bot_username: Optional[str] = None
    # Секрет для проверки, что запрос на webhook пришёл именно от Telegram
    # (заголовок X-Telegram-Bot-Api-Secret-Token, задаётся при setWebhook).
    telegram_webhook_secret: Optional[str] = None
```

И в декоратор `@field_validator(...)` (список строковых полей, строки ~169-174) добавить три имени — вписать `"login_bot_token", "login_bot_username", "telegram_webhook_secret",` перед `"app_encryption_key", mode="before",`:

```python
    @field_validator(
        "bot_token", "jwt_secret", "bot_username", "gemini_api_key",
        "openrouter_api_key", "google_client_id", "google_client_secret",
        "google_ios_client_id", "google_android_client_id", "google_web_client_id",
        "apple_bundle_id", "apple_service_id",
        "login_bot_token", "login_bot_username", "telegram_webhook_secret",
        "app_encryption_key", mode="before",
    )
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `cd backend && python -m pytest tests/test_tg_login_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/tests/test_tg_login_config.py
git commit -m "feat(auth): login bot settings (token/username/webhook secret)"
```

---

## Task 4: `auth_service.login_with_telegram_id`

**Files:**
- Modify: `backend/app/services/auth_service.py`
- Test: `backend/tests/test_login_with_telegram_id.py`

**Interfaces:**
- Consumes: `user_repo.get_by_telegram_id`, `user_repo.create`, `build_auth_response` (уже в файле).
- Produces: `auth_service.login_with_telegram_id(db, telegram_id: int, first_name: Optional[str]=None, last_name: Optional[str]=None, username: Optional[str]=None) -> dict` — тот же формат ответа, что `login_with_google` (ключи `access_token`, `refresh_token`, `token_type`, `subscription_active`, `user`).

- [ ] **Step 1: Написать провальный тест**

Создать `backend/tests/test_login_with_telegram_id.py`:

```python
"""login_with_telegram_id: вход нативки через бота попадает в аккаунт по telegram_id."""
import pytest

from app.core.errors import AppError
from app.repositories import user_repo
from app.services import auth_service


def test_creates_personal_account_for_new_telegram_id(db):
    resp = auth_service.login_with_telegram_id(
        db, telegram_id=555001, first_name="Иван", last_name="Петров"
    )
    assert resp["access_token"]
    user = user_repo.get_by_telegram_id(db, 555001)
    assert user is not None
    assert user.role == "user"
    assert user.agency_id is None
    assert user.full_name == "Иван Петров"


def test_returns_existing_account(db):
    existing = user_repo.create(db, telegram_id=555002, role="superadmin", agency_id=None)
    db.commit()
    resp = auth_service.login_with_telegram_id(db, telegram_id=555002)
    assert resp["user"].id == existing.id
    assert resp["user"].role == "superadmin"


def test_deactivated_account_rejected(db):
    u = user_repo.create(db, telegram_id=555003, role="user", agency_id=None)
    u.is_active = False
    db.commit()
    with pytest.raises(AppError):
        auth_service.login_with_telegram_id(db, telegram_id=555003)
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `cd backend && python -m pytest tests/test_login_with_telegram_id.py -v`
Expected: FAIL (`AttributeError: module 'app.services.auth_service' has no attribute 'login_with_telegram_id'`)

- [ ] **Step 3: Реализовать функцию**

В `backend/app/services/auth_service.py`, сразу после функции `login_with_apple` (перед `def refresh_session`), добавить:

```python
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
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `cd backend && python -m pytest tests/test_login_with_telegram_id.py -v`
Expected: PASS (3 теста)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/auth_service.py backend/tests/test_login_with_telegram_id.py
git commit -m "feat(auth): login_with_telegram_id (bot login resolves existing account)"
```

---

## Task 5: Сервис `tg_login_service` (код, апдейты, poll)

**Files:**
- Create: `backend/app/services/tg_login_service.py`
- Test: `backend/tests/test_tg_login_service.py`

**Interfaces:**
- Consumes: `tg_login_repo` (Task 2), `auth_service.login_with_telegram_id` (Task 4), `settings.login_bot_token/login_bot_username` (Task 3).
- Produces:
  - `start_login(db) -> dict` → `{"code": str, "deep_link": str, "expires_in": int}`
  - `handle_update(db, update: dict) -> None`
  - `poll(db, code: str) -> dict` → `{"status": "pending"|"expired"|"confirmed", "auth": Optional[dict]}`
  - Константа `CODE_TTL_SECONDS = 300`.

- [ ] **Step 1: Написать провальный тест**

Создать `backend/tests/test_tg_login_service.py`:

```python
"""tg_login_service: генерация кода, обработка апдейтов бота, poll → сессия.

Сеть к Telegram не трогаем: подменяем отправителей сообщений заглушками.
"""
import pytest

from app.config import settings
from app.repositories import tg_login_repo, user_repo
from app.services import tg_login_service


@pytest.fixture(autouse=True)
def _config(monkeypatch):
    monkeypatch.setattr(settings, "login_bot_token", "TESTTOKEN", raising=False)
    monkeypatch.setattr(settings, "login_bot_username", "realtyloginbot", raising=False)
    # Глушим реальные вызовы Telegram API.
    monkeypatch.setattr(tg_login_service, "_tg_api", lambda method, payload: {"ok": True, "result": {}})


def test_start_login_returns_code_and_link(db):
    out = tg_login_service.start_login(db)
    db.commit()
    assert out["code"] and len(out["code"]) >= 16
    assert out["deep_link"] == f"https://t.me/realtyloginbot?start=login_{out['code']}"
    assert out["expires_in"] == tg_login_service.CODE_TTL_SECONDS
    assert tg_login_repo.get_by_code(db, out["code"]) is not None


def test_start_login_503_when_not_configured(db, monkeypatch):
    from app.core.errors import AppError
    monkeypatch.setattr(settings, "login_bot_token", None, raising=False)
    with pytest.raises(AppError):
        tg_login_service.start_login(db)


def test_poll_pending_then_confirmed(db):
    code = tg_login_service.start_login(db)["code"]
    db.commit()
    assert tg_login_service.poll(db, code)["status"] == "pending"

    # Симулируем /start в боте (шлёт сообщение с кнопкой) и нажатие «Подтвердить».
    tg_login_service.handle_update(db, {
        "message": {"chat": {"id": 999}, "text": f"/start login_{code}"}
    })
    db.commit()
    tg_login_service.handle_update(db, {
        "callback_query": {
            "id": "cb1",
            "data": f"confirm_{code}",
            "from": {"id": 777001, "first_name": "Оля", "last_name": "Ким"},
            "message": {"chat": {"id": 999}, "message_id": 5},
        }
    })
    db.commit()

    res = tg_login_service.poll(db, code)
    assert res["status"] == "confirmed"
    assert res["auth"]["access_token"]
    assert user_repo.get_by_telegram_id(db, 777001) is not None

    # Одноразовость: повторный poll уже не отдаёт сессию.
    assert tg_login_service.poll(db, code)["status"] != "confirmed"


def test_unknown_code_is_pending(db):
    assert tg_login_service.poll(db, "doesnotexist")["status"] == "pending"
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `cd backend && python -m pytest tests/test_tg_login_service.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.services.tg_login_service'`)

- [ ] **Step 3: Реализовать сервис**

Создать `backend/app/services/tg_login_service.py`:

```python
"""
Бизнес-логика входа в нативное приложение через Telegram-бота (@realtyloginbot).

Отдельный бот, изолированный от прод-бота: все вызовы Telegram Bot API идут через
settings.login_bot_token. Поток:
  1) start_login — создаём одноразовый код (pending, TTL 5 мин) и ссылку t.me;
  2) handle_update — обрабатываем апдейты бота: на «/start login_<code>» шлём
     сообщение с кнопкой «Подтвердить»; на нажатие кнопки — привязываем telegram_id
     и помечаем код confirmed;
  3) poll — приложение опрашивает код: pending / expired / confirmed(+сессия).
     Первый confirmed выдаёт JWT и делает код consumed (одноразовый).
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import status
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import AppError
from app.repositories import tg_login_repo
from app.services import auth_service

logger = logging.getLogger("uvicorn.error")

CODE_TTL_SECONDS = 300
_API = "https://api.telegram.org/bot{token}/{method}"


def _tg_api(method: str, payload: dict) -> Optional[dict]:
    """Вызов Telegram Bot API от лица БОТА ВХОДА (login_bot_token). Ошибки сети не
    роняют обработку — логируем и продолжаем (в тестах функция подменяется)."""
    if not settings.login_bot_token:
        return None
    url = _API.format(token=settings.login_bot_token, method=method)
    try:
        resp = httpx.post(url, json=payload, timeout=15.0)
        return resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Login-bot %s не выполнен: %s", method, exc)
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(dt: datetime) -> datetime:
    """Привести значение из БД к timezone-aware (SQLite отдаёт naive)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def start_login(db: Session) -> dict:
    """Создать одноразовый код и ссылку t.me для входа. 503, если бот не настроен."""
    if not settings.login_bot_token or not settings.login_bot_username:
        raise AppError("telegram_login_not_configured", status.HTTP_503_SERVICE_UNAVAILABLE)
    code = secrets.token_hex(16)  # 128 бит → перебор невозможен
    expires_at = _now() + timedelta(seconds=CODE_TTL_SECONDS)
    tg_login_repo.create(db, code=code, expires_at=expires_at)
    deep_link = f"https://t.me/{settings.login_bot_username}?start=login_{code}"
    return {"code": code, "deep_link": deep_link, "expires_in": CODE_TTL_SECONDS}


def _send_confirm_prompt(chat_id: int, code: str) -> None:
    """Сообщение с кнопками «Подтвердить/Отмена» — только по валидному коду."""
    _tg_api("sendMessage", {
        "chat_id": chat_id,
        "text": "Кто-то входит в приложение Realty AI. Это вы?",
        "reply_markup": {"inline_keyboard": [[
            {"text": "✅ Подтвердить вход", "callback_data": f"confirm_{code}"},
            {"text": "❌ Отмена", "callback_data": f"cancel_{code}"},
        ]]},
    })


def _handle_start(db: Session, message: dict) -> None:
    text = (message.get("text") or "").strip()
    chat_id = (message.get("chat") or {}).get("id")
    if chat_id is None:
        return
    parts = text.split()
    # Deep-link «/start login_<code>»: у /start ровно один аргумент.
    if len(parts) != 2 or not parts[0].startswith("/start"):
        return
    param = parts[1]
    if not param.startswith("login_"):
        return
    code = param[len("login_"):]
    row = tg_login_repo.get_by_code(db, code)
    if row is None or row.status != "pending" or _as_aware(row.expires_at) < _now():
        return
    _send_confirm_prompt(chat_id, code)


def _handle_callback(db: Session, cq: dict) -> None:
    data = cq.get("data") or ""
    cq_id = cq.get("id")
    frm = cq.get("from") or {}
    msg = cq.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    message_id = msg.get("message_id")

    def _answer(text: str) -> None:
        if cq_id:
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id, "text": text})

    def _edit(text: str) -> None:
        if chat_id is not None and message_id is not None:
            _tg_api("editMessageText", {"chat_id": chat_id, "message_id": message_id, "text": text})

    if data.startswith("confirm_"):
        code = data[len("confirm_"):]
        row = tg_login_repo.get_by_code(db, code)
        if row is None or row.status != "pending" or _as_aware(row.expires_at) < _now():
            _answer("Код недействителен или истёк.")
            _edit("⌛ Ссылка входа недействительна. Запросите вход заново в приложении.")
            return
        row.status = "confirmed"
        row.telegram_id = int(frm.get("id"))
        row.tg_first_name = frm.get("first_name")
        row.tg_last_name = frm.get("last_name")
        db.commit()
        _answer("Готово")
        _edit("✅ Вход подтверждён. Вернитесь в приложение.")
    elif data.startswith("cancel_"):
        code = data[len("cancel_"):]
        row = tg_login_repo.get_by_code(db, code)
        if row is not None and row.status == "pending":
            row.status = "cancelled"
            db.commit()
        _answer("Отменено")
        _edit("❌ Вход отменён.")


def handle_update(db: Session, update: dict) -> None:
    """Единая точка входа webhook: маршрутизирует message / callback_query."""
    if "message" in update:
        _handle_start(db, update["message"])
    elif "callback_query" in update:
        _handle_callback(db, update["callback_query"])


def poll(db: Session, code: str) -> dict:
    """Опрос статуса кода приложением. Confirmed → выдаём сессию и гасим код."""
    row = tg_login_repo.get_by_code(db, code)
    # Неизвестный код → отвечаем pending (не раскрываем, существует ли он).
    if row is None:
        return {"status": "pending", "auth": None}
    if row.status == "confirmed":
        auth = auth_service.login_with_telegram_id(
            db, telegram_id=row.telegram_id,
            first_name=row.tg_first_name, last_name=row.tg_last_name,
        )
        row.status = "consumed"
        db.commit()
        return {"status": "confirmed", "auth": auth}
    if row.status in ("consumed", "cancelled"):
        return {"status": "expired", "auth": None}
    if _as_aware(row.expires_at) < _now():
        if row.status == "pending":
            row.status = "expired"
            db.commit()
        return {"status": "expired", "auth": None}
    return {"status": "pending", "auth": None}
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `cd backend && python -m pytest tests/test_tg_login_service.py -v`
Expected: PASS (4 теста)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/tg_login_service.py backend/tests/test_tg_login_service.py
git commit -m "feat(auth): tg_login_service (code gen, bot updates, poll)"
```

---

## Task 6: Схемы + роуты (start/poll) + webhook + регистрация

**Files:**
- Create: `backend/app/schemas/telegram_login.py`
- Create: `backend/app/api/routes/telegram_login.py`
- Create: `backend/app/api/routes/telegram_webhook.py`
- Modify: `backend/app/api/router.py`
- Test: `backend/tests/test_tg_login_routes.py`

**Interfaces:**
- Consumes: `tg_login_service` (Task 5).
- Produces HTTP: `POST /api/v1/auth/telegram/start`, `POST /api/v1/auth/telegram/poll`, `POST /api/v1/telegram/webhook`.

- [ ] **Step 1: Написать провальный тест**

Создать `backend/tests/test_tg_login_routes.py`:

```python
"""Роуты входа через Telegram-бота: start/poll и webhook (с проверкой secret).

Лёгкое приложение с нужными роутерами; get_db → in-memory сессия из фикстуры.
Сеть к Telegram глушим (подменяем _tg_api в сервисе).
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import telegram_login as tl_routes
from app.api.routes import telegram_webhook as wh_routes
from app.config import settings
from app.db.session import get_db
from app.services import tg_login_service


@pytest.fixture(autouse=True)
def _config(monkeypatch):
    monkeypatch.setattr(settings, "login_bot_token", "TESTTOKEN", raising=False)
    monkeypatch.setattr(settings, "login_bot_username", "realtyloginbot", raising=False)
    monkeypatch.setattr(settings, "telegram_webhook_secret", "s3cret", raising=False)
    monkeypatch.setattr(tg_login_service, "_tg_api", lambda m, p: {"ok": True, "result": {}})


def _client(db):
    app = FastAPI()
    app.include_router(tl_routes.router, prefix="/api/v1")
    app.include_router(wh_routes.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app, raise_server_exceptions=False)


def test_full_flow_start_webhook_poll(db):
    client = _client(db)
    r = client.post("/api/v1/auth/telegram/start", json={})
    assert r.status_code == 200, r.text
    code = r.json()["code"]
    assert r.json()["deep_link"].endswith(f"start=login_{code}")

    # pending
    assert client.post("/api/v1/auth/telegram/poll", json={"code": code}).json()["status"] == "pending"

    # webhook: /start (нужен secret-заголовок)
    hdr = {"X-Telegram-Bot-Api-Secret-Token": "s3cret"}
    client.post("/api/v1/telegram/webhook", headers=hdr, json={
        "message": {"chat": {"id": 42}, "text": f"/start login_{code}"}})
    # webhook: подтверждение
    client.post("/api/v1/telegram/webhook", headers=hdr, json={
        "callback_query": {"id": "c1", "data": f"confirm_{code}",
                           "from": {"id": 424242, "first_name": "Тест"},
                           "message": {"chat": {"id": 42}, "message_id": 1}}})

    res = client.post("/api/v1/auth/telegram/poll", json={"code": code})
    assert res.json()["status"] == "confirmed"
    assert res.json()["auth"]["access_token"]


def test_webhook_rejects_bad_secret(db):
    client = _client(db)
    r = client.post("/api/v1/telegram/webhook",
                    headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
                    json={"message": {"chat": {"id": 1}, "text": "/start login_x"}})
    assert r.status_code == 403


def test_start_503_when_not_configured(db, monkeypatch):
    monkeypatch.setattr(settings, "login_bot_token", None, raising=False)
    client = _client(db)
    assert client.post("/api/v1/auth/telegram/start", json={}).status_code == 503
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `cd backend && python -m pytest tests/test_tg_login_routes.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.api.routes.telegram_login'`)

- [ ] **Step 3: Создать схемы**

Создать `backend/app/schemas/telegram_login.py`:

```python
"""Схемы входа через Telegram-бота (start / poll)."""
from typing import Optional

from pydantic import BaseModel

from app.schemas.auth import AuthResponse


class TelegramStartResponse(BaseModel):
    # Одноразовый код и готовая ссылка t.me для открытия бота.
    code: str
    deep_link: str
    expires_in: int


class TelegramPollRequest(BaseModel):
    code: str


class TelegramPollResponse(BaseModel):
    # pending — ждём подтверждения; expired — код истёк/использован/отменён;
    # confirmed — вход подтверждён, auth содержит сессию.
    status: str
    auth: Optional[AuthResponse] = None
```

- [ ] **Step 4: Создать роут start/poll**

Создать `backend/app/api/routes/telegram_login.py`:

```python
"""
Роуты входа через Telegram-бота (нативное приложение):
  POST /auth/telegram/start — получить одноразовый код и ссылку t.me;
  POST /auth/telegram/poll  — опросить статус (pending/expired/confirmed+сессия).

Логика — в tg_login_service. Оба роута публичные (до входа), поэтому под rate-limit.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.ratelimit import rate_limit
from app.db.session import get_db
from app.schemas.telegram_login import (
    TelegramPollRequest,
    TelegramPollResponse,
    TelegramStartResponse,
)
from app.services import tg_login_service

router = APIRouter(prefix="/auth/telegram", tags=["auth"])


@router.post(
    "/start",
    response_model=TelegramStartResponse,
    dependencies=[Depends(rate_limit(20, 60, "tg_login_start"))],
)
def start(db: Session = Depends(get_db)):
    """Создать одноразовый код и ссылку на бота входа."""
    return tg_login_service.start_login(db)


@router.post(
    "/poll",
    response_model=TelegramPollResponse,
    dependencies=[Depends(rate_limit(120, 60, "tg_login_poll"))],
)
def poll(body: TelegramPollRequest, db: Session = Depends(get_db)):
    """Опросить статус кода. Confirmed → выдаём сессию (одноразово)."""
    return tg_login_service.poll(db, body.code)
```

- [ ] **Step 5: Создать роут webhook**

Создать `backend/app/api/routes/telegram_webhook.py`:

```python
"""
Приёмник апдейтов бота входа (@realtyloginbot).
  POST /telegram/webhook — Telegram шлёт сюда message / callback_query.

Аутентификация — заголовок X-Telegram-Bot-Api-Secret-Token (задаётся при
setWebhook). Без совпадения секрета — 403 (чужой запрос). Тело — произвольный
Telegram Update (принимаем как dict). Всегда быстро отвечаем 200, чтобы Telegram
не копил повторы.
"""
from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.services import tg_login_service

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    """Обработать апдейт бота входа (с проверкой секрета Telegram)."""
    secret = settings.telegram_webhook_secret
    got = request.headers.get("x-telegram-bot-api-secret-token")
    if not secret or got != secret:
        return Response(status_code=status.HTTP_403_FORBIDDEN)
    try:
        update = await request.json()
    except Exception:  # noqa: BLE001
        return Response(status_code=status.HTTP_200_OK)
    if isinstance(update, dict):
        tg_login_service.handle_update(db, update)
    return {"ok": True}
```

- [ ] **Step 6: Зарегистрировать роутеры**

В `backend/app/api/router.py`:
- В импорт из `app.api.routes` добавить `telegram_login,` и `telegram_webhook,` (в алфавитный список).
- После `api_router.include_router(auth.router)` добавить:

```python
api_router.include_router(telegram_login.router)
api_router.include_router(telegram_webhook.router)
```

- [ ] **Step 7: Запустить тест — убедиться, что проходит**

Run: `cd backend && python -m pytest tests/test_tg_login_routes.py -v`
Expected: PASS (3 теста)

- [ ] **Step 8: Прогнать весь бэкенд-набор (ничего не сломали)**

Run: `cd backend && python -m pytest -q`
Expected: все тесты зелёные.

- [ ] **Step 9: Commit**

```bash
git add backend/app/schemas/telegram_login.py backend/app/api/routes/telegram_login.py backend/app/api/routes/telegram_webhook.py backend/app/api/router.py backend/tests/test_tg_login_routes.py
git commit -m "feat(auth): telegram bot login routes (start/poll) + webhook"
```

---

## Task 7: Фронтенд — кнопка «Войти через Telegram» + поток

**Files:**
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes HTTP: `/api/v1/auth/telegram/start`, `/api/v1/auth/telegram/poll`.
- Использует существующие: `api`, `getLastFetchError`, `errText` (импортированы в App.tsx), `applyAuth`, компонент `NativeLoginScreen`.

- [ ] **Step 1: Добавить `telegramSignIn`**

В `frontend/src/App.tsx`, сразу после функции `nativeSignIn` (после строки ~848, перед `const bootstrapping = useRef(false);`), добавить:

```tsx
  // Вход через Telegram-бота (@realtyloginbot): берём одноразовый код, открываем
  // бота, опрашиваем подтверждение. На confirmed — та же applyAuth, что у Google
  // (внутри неё сессия сохраняется на нативной платформе).
  async function telegramSignIn(): Promise<string | null> {
    try {
      const start = await api<{ code: string; deep_link: string; expires_in: number }>(
        "/api/v1/auth/telegram/start",
        { method: "POST", body: {} }
      );
      if (!start.ok || !start.data) {
        if (start.status === 0) return "сеть: " + getLastFetchError();
        return "сервер: HTTP " + start.status + " " + (errText(start.data, start.status) || "");
      }
      const { code, deep_link } = start.data;
      // "_system" → Capacitor откроет ссылку во внешнем приложении Telegram.
      window.open(deep_link, "_system");

      const deadline = Date.now() + 150000; // ~2.5 мин (TTL кода 5 мин)
      while (Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 2000));
        const p = await api<{ status: string; auth?: AuthResponse }>(
          "/api/v1/auth/telegram/poll",
          { method: "POST", body: { code } }
        );
        if (p.ok && p.data) {
          if (p.data.status === "confirmed" && p.data.auth) {
            await applyAuth(p.data.auth);
            return null;
          }
          if (p.data.status === "expired") return "Время вышло, попробуйте войти заново.";
        }
      }
      return "Время вышло, попробуйте войти заново.";
    } catch (e: any) {
      return "исключение: " + (e?.message || String(e));
    }
  }
```

- [ ] **Step 2: Прокинуть обработчик в экран входа**

В `frontend/src/App.tsx` заменить строку (~1058):

```tsx
  if (phase === "login") return <NativeLoginScreen onSignIn={nativeSignIn} />;
```

на:

```tsx
  if (phase === "login") return <NativeLoginScreen onSignIn={nativeSignIn} onTelegram={telegramSignIn} />;
```

- [ ] **Step 3: Обновить `NativeLoginScreen` (сигнатура + кнопка)**

В `frontend/src/App.tsx` заменить заголовок компонента и `busy`-стейт (строки ~543-544):

```tsx
function NativeLoginScreen({ onSignIn }: { onSignIn: (p: "google" | "apple") => Promise<string | null> }) {
  const [busy, setBusy] = useState<null | "google" | "apple">(null);
```

на:

```tsx
function NativeLoginScreen({
  onSignIn,
  onTelegram,
}: {
  onSignIn: (p: "google" | "apple") => Promise<string | null>;
  onTelegram: () => Promise<string | null>;
}) {
  const [busy, setBusy] = useState<null | "google" | "apple" | "telegram">(null);
  const goTelegram = async () => {
    setBusy("telegram");
    setErr("Открываю Telegram… подтвердите вход в боте.");
    try {
      setErr(await onTelegram());
    } catch (e: any) {
      setErr("сбой обработчика: " + (e?.message || String(e)));
    } finally {
      setBusy(null);
    }
  };
```

- [ ] **Step 4: Добавить кнопку Telegram (первой в стеке)**

В `frontend/src/App.tsx`, внутри `NativeLoginScreen`, в блоке `<div className="space-y-3">` (перед кнопкой Google, строка ~575) добавить первой кнопку:

```tsx
        <button
          onClick={goTelegram}
          disabled={!!busy}
          className="w-full py-3 rounded-xl font-bold text-[15px] text-white cursor-pointer active:scale-[.98] transition disabled:opacity-50"
          style={{ background: "#229ED9" }}
        >
          {busy === "telegram" ? "…" : "Войти через Telegram"}
        </button>
```

- [ ] **Step 5: Собрать фронтенд (проверка типов/сборки)**

Run: `cd frontend && npm run build`
Expected: сборка без ошибок TypeScript (dist создан).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(native): 'Login via Telegram' button + bot-confirmation flow"
```

---

## Task 8: Деплой и настройка webhook (ops)

Не TDD — деплой и одноразовая настройка. Токен бота НЕ коммитим (только в `.env` на pc1).

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Passthrough переменных в docker-compose**

В `docker-compose.yml`, в сервисе `backend`, секция `environment:` — добавить (рядом с существующими `GOOGLE_*`/`CORS_ORIGINS`):

```yaml
      LOGIN_BOT_TOKEN: ${LOGIN_BOT_TOKEN:-}
      LOGIN_BOT_USERNAME: ${LOGIN_BOT_USERNAME:-}
      TELEGRAM_WEBHOOK_SECRET: ${TELEGRAM_WEBHOOK_SECRET:-}
```

- [ ] **Step 2: Commit compose**

```bash
git add docker-compose.yml
git commit -m "chore(deploy): passthrough login bot env vars"
```

- [ ] **Step 3: Смёржить ветку в main и запушить**

```bash
git checkout main
git merge --ff-only feature/native-auth
git push origin main
git checkout feature/native-auth
```

(Если `--ff-only` не проходит — сообщить владельцу, не делать merge-коммит без согласования.)

- [ ] **Step 4: На pc1 добавить переменные в `.env`**

Через plink→wsl, в `~/Realty-AI/.env` дописать (сгенерировав секрет, напр. `openssl rand -hex 16`):

```
LOGIN_BOT_TOKEN=8618424637:AAG...   # реальный токен @realtyloginbot
LOGIN_BOT_USERNAME=realtyloginbot
TELEGRAM_WEBHOOK_SECRET=<случайный hex>
```

- [ ] **Step 5: Развернуть**

На pc1 (в FOREGROUND plink, чтобы SSH не отвалился):

```
cd ~/Realty-AI && git pull --ff-only && docker compose up -d --build
```

Дождаться, пока backend перезапустится (миграция 0044 применится на старте).

- [ ] **Step 6: Установить webhook бота входа**

Один раз (подставив реальные токен и секрет):

```bash
curl -s "https://api.telegram.org/bot<LOGIN_BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://pc1.tailcdc07f.ts.net/api/v1/telegram/webhook","secret_token":"<TELEGRAM_WEBHOOK_SECRET>","allowed_updates":["message","callback_query"]}'
```

Проверить: `curl -s "https://api.telegram.org/bot<LOGIN_BOT_TOKEN>/getWebhookInfo"` → `url` совпадает, `pending_update_count` не растёт.

- [ ] **Step 7: Smoke-тест end-to-end**

`curl -s -X POST https://pc1.tailcdc07f.ts.net/api/v1/auth/telegram/start -H "Content-Type: application/json" -d '{}'`
Expected: JSON с `code` и `deep_link`. Открыть ссылку в Telegram, нажать «✅ Подтвердить», убедиться, что `poll` по этому коду вернул `status: confirmed` с `auth.access_token`.

- [ ] **Step 8: Пересобрать APK**

```
cd frontend && npm run build && npx cap sync android && cd android && ./gradlew assembleDebug
```

APK: `frontend/android/app/build/outputs/apk/debug/app-debug.apk`. Отдать пользователю, проверить кнопку «Войти через Telegram» на устройстве.

---

## Self-Review

**1. Spec coverage:**
- Таблица `tg_login_codes` + миграция 0044 → Task 1 ✅
- start/poll эндпоинты → Task 6 ✅
- webhook приёмник (message + callback + secret) → Task 5 (logic) + Task 6 (route) ✅
- Переиспользование telegram_id-резолва + build_auth_response → Task 4 ✅
- Настройки login_bot_token/username/webhook secret → Task 3 ✅
- Безопасность (128-бит код, TTL, одноразовость, rate-limit, secret) → Task 1/5/6 ✅
- Нативка: кнопка + deep link + polling → Task 7 ✅
- Тесты → Task 1/2/3/4/5/6 ✅
- setWebhook + env + compose → Task 8 ✅

**2. Placeholder scan:** реальный код во всех шагах; `<LOGIN_BOT_TOKEN>` / `<TELEGRAM_WEBHOOK_SECRET>` в Task 8 — намеренные ops-подстановки (секреты не в репозитории).

**3. Type consistency:** `login_with_telegram_id(db, telegram_id, first_name, last_name, username)` — определена в Task 4, вызывается в Task 5 с `telegram_id/first_name/last_name`. `poll` → `{"status", "auth"}` совпадает с `TelegramPollResponse` (Task 6) и с фронтом (Task 7). `start_login` → `{"code","deep_link","expires_in"}` совпадает с `TelegramStartResponse` и фронтом. `_tg_api(method, payload)` — единое имя, подменяется в тестах Task 5/6.
