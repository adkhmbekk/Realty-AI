# Runbook выката: юзер-центричная модель

Ветка: `feature/user-centric-pivot`. Прод: WSL2 на `pc1` (`git pull` только `main`).
**Пока НЕ деплоить** — ждём команды владельца. Этот файл — чтобы выкат и откат
прошли по шагам.

---

## 0. Что уже сделано (на ветке, запушено)

- Бэкенд Фаз 1–3, 5 (профиль, открытая регистрация, мультиагентство, superadmin-вид) + тесты.
- Миграции: `0038_user_profile_fields`, `0039_user_role_personal` (обе аддитивные).
- Фронт-экраны: `screens/Personal.tsx`, `screens/PlatformUsers.tsx` (пока НЕ импортированы в App).

## 1. ОБЯЗАТЕЛЬНО перед деплоем (на pc1, со сборкой)

Деплой БЕЗ этих шагов выкатит бэкенд + неподключённые экраны (новый UX не покажется,
а неиспользуемый .tsx с TS-ошибкой уронит `npm run build`). Поэтому сначала:

- [ ] Встроить `Personal.tsx` в машину фаз `App.tsx` (личный контекст → хаб; вход в
      агентство → Shell; «назад в личное» из Shell).
- [ ] Встроить `PlatformUsersScreen` в `Superadmin.tsx` / нижние вкладки суперадмина
      (главный экран — список юзеров).
- [ ] Перенести локальные строки (`STR`) из обоих экранов в `i18n.ts`.
- [ ] `cd backend && ruff check app tests && pytest -q` — зелено.
- [ ] `cd frontend && npm ci && npm run build` — зелено (TS без ошибок).
- [ ] Вживую прокликать на тестовой БД: онбординг → хаб → создать/вступить →
      вход/переключение; superadmin → список юзеров → карточка (объекты, без клиентов);
      существующий юзер видит своё агентство и входит.

## 2. Деплой (после зелёной проверки и команды владельца)

```bash
# локально: слить ветку в main и запушить
git checkout main && git pull --ff-only
git merge --no-ff feature/user-centric-pivot
git push origin main

# на pc1:
ssh user@100.81.172.20
wsl
cd ~/Realty-AI
git pull --ff-only
docker compose up -d --build          # миграции 0038/0039 применятся на старте (lifespan)
docker compose ps                     # все контейнеры up
curl -s localhost:8080/health || true # проверка живости
```

Проверить после выката: вход существующего юзера → личный хаб со своим агентством;
создание/вступление; superadmin-вид.

## 3. Откат (если что-то пошло не так)

```bash
# на pc1: код назад
cd ~/Realty-AI
git log --oneline -3                  # найти прошлый коммит main (ДО мерджа)
git reset --hard <prev_main_sha>      # или: git revert -m 1 <merge_sha>
docker compose up -d --build

# база: миграции аддитивные, откат чистый до 0037
docker compose exec backend alembic downgrade 0037_invite_multiuse
```

- Миграции только ДОБАВЛЯЮТ колонки/роль → `downgrade` безопасен, данные агентств/
  юзеров/объектов не теряются.
- Внимание: `downgrade` роли (0039) упадёт, если появились строки с `role='user'`
  (новые личные аккаунты). Тогда сначала: перевести их (`UPDATE users SET role='agent'
  WHERE role='user' AND agency_id IS NOT NULL; DELETE FROM users WHERE role='user' AND
  agency_id IS NULL` — по ситуации), потом `downgrade`.
- Крайний случай: восстановление из авто-бэкапа (сервис `backup`: БД + фото).

## 4. Что НЕ забыть

- CVE-апгрейд (`cryptography`/`starlette`) — отдельной веткой, НЕ в этом деплое (бэклог).
- `pip-audit` в CI красный — это ожидаемо (не блокирует), см. бэклог.
