# Архитектура Realty AI

## Обзор
Мультитенантный SaaS для риелторских агентств в виде Telegram Mini App.
Стек: FastAPI (Python 3.12) + PostgreSQL 16 + Alembic + React/TS/Vite + Caddy + Docker Compose. Вход — через Telegram `initData`.

## Слои (backend)
- **routes** (`app/api/routes/*`) — HTTP, валидация схем, коды ответов. Не содержит бизнес-правил.
- **services** (`app/services/*`) — бизнес-логика (генерация `display_id`, статус-переходы, проверка подписки). Не знает про HTTP/SQL напрямую.
- **repositories** (`app/repositories/*`) — доступ к данным, всегда со scoping по `agency_id`.
- **models** (`app/db/models/*`) — ORM-модели, ограничения целостности (CHECK/FK/CASCADE).

## Мультитенантность
Изоляция по `agency_id`, который берётся из сессии/токена, а не из тела запроса. Покрыто тестами (`tests/test_isolation.py`). Роли: `superadmin` / `agency_admin` (+ флаг `is_owner`) / `agent`.

## Поток аутентификации
Telegram `initData` → проверка HMAC-SHA256 + `auth_date` + anti-replay → выдача JWT (HS256). Авторизация на каждом запросе перечитывает роль/активность из БД (смена роли/деактивация действуют мгновенно). Подписка агентства проверяется тем же gate (`agency_is_active`).

## Модель асинхронности
См. ADR-0001: гибрид — async-маршруты + `httpx` для внешнего I/O, БД синхронно через threadpool.

## Топология развёртывания
Docker Compose: `db` (Postgres, не публикуется), `backend` (FastAPI, не публикуется), `web` (Caddy, единственный ingress: `/api/*` и `/health`), `backup` (периодический pg_dump + копия фото), туннель (ngrok, постоянный домен). Цель по ТЗ (фаза 1) — VPS; текущая среда разработки — локальная машина (см. риск C1 в аудите).

## Хранилище
БД — том `db_data`; фото — том `photos_data` (локальный диск; объектное хранилище — roadmap); секреты (JWT) — отдельный том `secrets_data`, вне бэкапов.
