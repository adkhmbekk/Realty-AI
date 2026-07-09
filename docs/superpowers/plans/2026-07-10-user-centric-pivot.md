# План реализации: переход на юзер-центричную модель

> **Для агентов-исполнителей:** ОБЯЗАТЕЛЬНАЯ СУБ-СКИЛЛ: используйте superpowers:subagent-driven-development (рекомендуется) или superpowers:executing-plans для пошагового выполнения. Шаги отмечены чекбоксами (`- [ ]`).

**Цель:** Перевести приложение с модели «вокруг агентства» на «вокруг юзера»: личный аккаунт, мультиагентство, онбординг и переключение между агентствами — не ломая изоляцию арендаторов.

**Архитектура:** Слои `api → service → repository → db` (не перепрыгивать). Членство (`agency_memberships`) — источник правды о ролях; активное агентство хранится в JWT-метке `act_as_agency_id` (обобщение существующего acting-контекста суперадмина на всех юзеров). CRM-данные остаются агентство-скоупными.

**Стек:** FastAPI + SQLAlchemy 2.0 (синхронный) + PostgreSQL 16; Alembic; pytest (SQLite in-memory в conftest); фронт React 18 + Vite + TS + Tailwind.

## Глобальные ограничения

- Код, комментарии, коммиты — **на русском** (см. `CLAUDE.md`).
- Любая агентская выборка фильтруется по `agency_id` из **активного контекста**, не из тела запроса. Изоляция арендаторов — критична.
- Доступ к данным — только через `repositories/`. Настройки — через `app.config.settings`. Ошибки юзеру — через каталог `app/core/errors.py` (обе языковые версии).
- Схему БД менять только миграцией Alembic. Секреты в БД — Fernet. Не понижать CVE-пины.
- Каждая новая фича/багфикс — с тестом. Перед коммитом: `ruff check backend`, `mypy backend`, `pytest`. Фронт: `npm run build` без ошибок TS.
- **НЕ деплоить**: вся работа на ветке `feature/user-centric-pivot`, без `git push`, пока владелец не подтвердит.

## Что УЖЕ есть (не переделывать)

- `agency_memberships` (миграция 0035) создана и **забэкфилена** существующими сотрудниками (одно членство = текущее агентство/роль). Суперадмины не переносились (работают через acting).
- `repositories/agency_membership_repo.py`: `get`, `list_for_user`, `create`, `get_or_create`.
- `services/member_service.py` — управление командой.
- acting-контекст суперадмина (`act_as_agency_id` в JWT, ре-верификация владения в гвардах) — обобщаем, а не пишем заново.
- Многоразовые приглашения (`invite`) — готовы.

## Фазы (каждая — самостоятельный деплой)

- **Фаза 1 — Профиль-поля юзера в БД** (аддитивно, без смены поведения). ← детально ниже.
- **Фаза 2 — Личный контекст в auth** (вход без агентства → личное пространство; `/me/agencies`; вход/переключение в любое членство; роль из членства). Отдельный план.
- **Фаза 3 — Эндпоинты профиля/номера** (правка профиля; номер из Telegram-контакта; номер обязателен при создании агентства). Отдельный план.
- **Фаза 4 — Фронтенд** (онбординг: язык→профиль; личный хаб; переключатель; интеграция с Shell). Отдельный план.

Детальный TDD ниже — для **Фазы 1**. Планы Фаз 2–4 пишем перед их реализацией (по мере готовности предыдущей).

---

## ФАЗА 1 — Профиль-поля юзера

**Цель фазы:** добавить в `users` личные поля (`first_name`, `last_name`, `phone`, `phone_verified`, `language`), забэкфилить `first_name` из `full_name`, отдавать их в `/auth/me`. Полностью аддитивно, поведение не меняется → безопасно к деплою.

### Task 1: Поля профиля в модели User

**Files:**
- Modify: `backend/app/db/models/user.py`
- Test: `backend/tests/test_user_profile.py` (create)

**Interfaces:**
- Produces: `User.first_name: str|None`, `User.last_name: str|None`, `User.phone: str|None` (unique), `User.phone_verified: bool`, `User.language: str` (default `'ru'`).

- [ ] **Step 1: Написать падающий тест** — модель принимает и хранит новые поля.

```python
# backend/tests/test_user_profile.py
from app.db.models.user import User


def test_user_has_profile_fields(db):
    u = User(
        telegram_id=900001, role="agent", agency_id=None,
        first_name="Азиз", last_name="Каримов",
        phone="+998901234567", phone_verified=True, language="uz",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    assert u.first_name == "Азиз"
    assert u.last_name == "Каримов"
    assert u.phone == "+998901234567"
    assert u.phone_verified is True
    assert u.language == "uz"


def test_user_profile_defaults(db):
    u = User(telegram_id=900002, role="agent")
    db.add(u)
    db.commit()
    db.refresh(u)
    assert u.first_name is None
    assert u.last_name is None
    assert u.phone is None
    assert u.phone_verified is False
    assert u.language == "ru"
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `cd backend && pytest tests/test_user_profile.py -v`
Expected: FAIL — `TypeError: 'first_name' is an invalid keyword argument for User` (поля ещё нет).

- [ ] **Step 3: Добавить поля в модель**

В `backend/app/db/models/user.py`, после поля `full_name` (строка ~35) добавить:

```python
    # Личный профиль (2026-07, юзер-центричная модель). Имя/фамилия — отдельно
    # от full_name (его оставляем для существующего кода отображения; при правке
    # профиля держим full_name = first_name + ' ' + last_name).
    first_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Номер телефона — «якорь» аккаунта для будущего входа с сайта/приложения.
    # Уникальный, пока необязательный. Из Telegram-контакта приходит подтверждённым.
    phone: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    phone_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # Язык интерфейса (раньше язык не хранился — шёл через заголовок X-Lang).
    language: Mapped[str] = mapped_column(
        String, nullable=False, default="ru", server_default=text("'ru'")
    )
```

(Импорты `Boolean`, `String`, `text` в этом файле уже есть.)

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `cd backend && pytest tests/test_user_profile.py -v`
Expected: PASS (оба теста).

- [ ] **Step 5: Линт/типы**

Run: `cd backend && ruff check backend/app/db/models/user.py && mypy backend/app/db/models/user.py`
Expected: без ошибок.

- [ ] **Step 6: Коммит**

```bash
git add backend/app/db/models/user.py backend/tests/test_user_profile.py
git commit -m "Профиль юзера: поля first_name/last_name/phone/phone_verified/language"
```

### Task 2: Миграция Alembic 0038 (поля + бэкфилл)

**Files:**
- Create: `backend/alembic/versions/0038_user_profile_fields.py`
- Test: `backend/tests/test_user_profile.py` (расширить)

**Interfaces:**
- Consumes: поля из Task 1.
- Produces: миграция `0038_user_profile_fields`, `down_revision = "0037_invite_multiuse"`.

- [ ] **Step 1: Написать падающий тест на бэкфилл `first_name` из `full_name`**

Тест на уровне логики бэкфилла (переносимо на SQLite): существующему юзеру с `full_name` и без `first_name` проставляется `first_name`.

```python
# добавить в backend/tests/test_user_profile.py
from app.db.models.user import User


def _backfill_first_name(db):
    # та же логика, что в миграции 0038 (для проверки на реальной сессии)
    for u in db.query(User).filter(User.first_name.is_(None), User.full_name.isnot(None)).all():
        u.first_name = u.full_name
    db.commit()


def test_backfill_first_name_from_full_name(db):
    u = User(telegram_id=900003, role="agent", full_name="Сардор Алиев")
    db.add(u)
    db.commit()
    _backfill_first_name(db)
    db.refresh(u)
    assert u.first_name == "Сардор Алиев"
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `cd backend && pytest tests/test_user_profile.py::test_backfill_first_name_from_full_name -v`
Expected: FAIL (функция `_backfill_first_name` ссылается на `User.first_name`, но до Task 1 — уже есть; тест падает только если Task 1 не сделан). Если Task 1 сделан — тест сразу зелёный; тогда это регресс-страховка, отметить шаг выполненным.

- [ ] **Step 3: Написать миграцию**

```python
# backend/alembic/versions/0038_user_profile_fields.py
"""users: поля личного профиля (first_name/last_name/phone/phone_verified/language)

Additive + бэкфилл: добавляем поля личного аккаунта (юзер-центричная модель) и
переносим first_name из существующего full_name. Поведение авторизации не
меняется — членства (0035) остаются источником правды о ролях.

Revision ID: 0038_user_profile_fields
Revises: 0037_invite_multiuse
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0038_user_profile_fields"
down_revision: Union[str, Sequence[str], None] = "0037_invite_multiuse"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("first_name", sa.String(), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.String(), nullable=True))
    op.add_column("users", sa.Column("phone", sa.String(), nullable=True))
    op.add_column(
        "users",
        sa.Column("phone_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("language", sa.String(), server_default=sa.text("'ru'"), nullable=False),
    )
    # Уникальность номера — частичный индекс (NULL не конфликтуют между собой).
    op.create_index(
        "uq_users_phone", "users", ["phone"], unique=True,
        postgresql_where=sa.text("phone IS NOT NULL"),
    )
    # Бэкфилл: first_name из full_name (фамилию не делим — оставляем пусто).
    op.execute("UPDATE users SET first_name = full_name WHERE first_name IS NULL AND full_name IS NOT NULL")


def downgrade() -> None:
    op.drop_index("uq_users_phone", table_name="users")
    op.drop_column("users", "language")
    op.drop_column("users", "phone_verified")
    op.drop_column("users", "phone")
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")
```

- [ ] **Step 4: Запустить весь профильный тест-файл**

Run: `cd backend && pytest tests/test_user_profile.py -v`
Expected: PASS.

- [ ] **Step 5: Проверить целостность цепочки миграций**

Run: `cd backend && python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; s=ScriptDirectory.from_config(Config('alembic.ini')); print(s.get_current_head())"`
Expected: печатает `0038_user_profile_fields` (единственная голова).

- [ ] **Step 6: Линт**

Run: `cd backend && ruff check backend/alembic/versions/0038_user_profile_fields.py`
Expected: без ошибок.

- [ ] **Step 7: Коммит**

```bash
git add backend/alembic/versions/0038_user_profile_fields.py backend/tests/test_user_profile.py
git commit -m "Миграция 0038: поля профиля + бэкфилл first_name из full_name"
```

### Task 3: Отдавать профиль в схемах и `/auth/me`

**Files:**
- Modify: схема ответа пользователя (найти: `backend/app/schemas/` — где формируется тело `/auth/me`; вероятно `schemas/auth.py` или `schemas/user.py`)
- Modify: сервис/роутер, собирающий это тело (`backend/app/services/auth_service.py` или `api/routes/auth.py`)
- Test: `backend/tests/test_sessions.py` (расширить) или `test_user_profile.py`

**Interfaces:**
- Consumes: поля User из Task 1.
- Produces: в ответе `/auth/me` присутствуют `first_name`, `last_name`, `phone`, `phone_verified`, `language`.

- [ ] **Step 1: Найти точную схему и место сборки ответа**

Run: `cd backend && grep -rn "full_name" app/schemas app/services/auth_service.py app/api/routes/auth.py`
Прочитать найденную схему ответа пользователя — определить точное имя класса (напр. `MeOut`/`UserOut`) и где он заполняется.

- [ ] **Step 2: Написать падающий тест** — ответ содержит новые поля.

```python
# в backend/tests/test_user_profile.py — использовать существующие фикстуры
# авторизованного клиента из conftest (по образцу test_sessions.py).
def test_me_returns_profile_fields(client, make_user):
    # make_user / авторизация — по образцу уже существующих тестов сессий
    ...
    resp = client.get("/api/v1/auth/me", headers=auth_headers)
    body = resp.json()
    assert "first_name" in body
    assert "phone" in body
    assert "language" in body
```

(Точные фикстуры — свериться с `backend/tests/conftest.py` и `test_sessions.py`; повторить их приём авторизации.)

- [ ] **Step 3: Запустить — убедиться, что падает**

Run: `cd backend && pytest tests/test_user_profile.py::test_me_returns_profile_fields -v`
Expected: FAIL (полей нет в ответе).

- [ ] **Step 4: Добавить поля в схему ответа**

В найденной Pydantic-схеме ответа пользователя добавить:

```python
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    phone_verified: bool = False
    language: str = "ru"
```

Если схема строится с `model_config = ConfigDict(from_attributes=True)` — поля подтянутся из ORM автоматически. Иначе — прописать их при ручной сборке ответа.

- [ ] **Step 5: Запустить — убедиться, что проходит**

Run: `cd backend && pytest tests/test_user_profile.py -v`
Expected: PASS.

- [ ] **Step 6: Полный прогон + линт/типы**

Run: `cd backend && pytest && ruff check backend && mypy backend`
Expected: всё зелёное (ничего не сломано).

- [ ] **Step 7: Коммит**

```bash
git add backend/app/schemas backend/app/services backend/app/api backend/tests/test_user_profile.py
git commit -m "Профиль в ответе /auth/me (first_name/last_name/phone/язык)"
```

### Фаза 1 — критерий готовности

- `pytest`, `ruff`, `mypy` зелёные.
- Миграция 0038 — единственная голова, аддитивная, с корректным `downgrade`.
- Поведение авторизации/изоляции НЕ изменилось (регресс-тесты `test_isolation.py`, `test_sessions.py` проходят).
- Готово к деплою независимо (можно выкатить, ничего не сломав).

---

## Дальнейшие фазы (планы пишутся перед реализацией)

**Фаза 2 — Личный контекст в auth.** `/auth/telegram` больше не отдаёт 403 при отсутствии агентства — возвращает личный контекст. Новый `GET /me/agencies` (использует `agency_membership_repo.list_for_user`). Обобщить вход/переключение `POST /agencies/{id}/enter` на любое членство (проверка членства, роль из членства). Гварды `require_agency_*` берут роль из членства активного агентства. Тесты: изоляция между членствами (HTTP-level), не-член не входит, роль из членства.

**Фаза 3 — Профиль/номер.** `PATCH /users/me` (имя/фамилия/язык, синхронно обновлять `full_name`). Номер из Telegram-контакта (`phone_verified=true`), санитизация номера (переиспользовать существующий приём из `test_phone_sanitize`). Номер обязателен и подтверждён при `POST /agencies` (иначе ошибка из каталога). Тесты.

**Фаза 4 — Фронтенд.** Фазы `loading → onboarding → personal → agency`. Экраны: выбор языка, профиль (имя/фамилия + «поделиться номером» через `requestContact`), личный хаб (список агентств с ролью + «＋»), переключатель. Shell — рабочее пространство агентства (+ «‹ выход» и переключатель в шапке). Дизайн — существующая система (`components/ui.tsx`, `lucide`, токены). `npm run build` зелёный. Ориентир — прототип `docs/superpowers/specs/2026-07-10-user-centric-pivot-prototype.html`.
**Важно (существующие юзеры):** после деплоя текущий юзер входит → личный хаб → видит своё
агентство (членство уже есть из 0035) со своей ролью → входит и работает как раньше. Профиль
предзаполнен из `full_name`. Проверить это отдельным сценарным тестом/ручной проверкой.

**Фаза 5 — Superadmin: вид по юзерам (только объекты).** Главный экран суперадмина — список юзеров
прошки; тап по юзеру → его агентства/роли/контакт/активность + **его объекты** (листинги).
Клиентскую базу суперадмин НЕ видит (приватность — решение владельца). Реализуется явным
ограничением выборки (read-only витрина объектов), без ослабления изоляции. Тесты: суперадмин видит
объекты юзера, но НЕ его клиентов/заявки/сделки. Отдельный план.
