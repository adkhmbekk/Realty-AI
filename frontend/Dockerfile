# Многоэтапная сборка фронтенда Realty AI.
#
# Этап 1 (build): ставим зависимости и собираем React (Vite) в статику.
# Этап 2 (serve): берём только готовую статику и отдаём её через Caddy,
#                 который заодно проксирует /api на backend.

# ─── Этап 1: сборка ──────────────────────────────────────────────────────
FROM node:20-alpine AS build
WORKDIR /app

# Сначала только манифесты зависимостей — для кэширования слоёв.
COPY package.json package-lock.json ./
RUN npm ci

# Теперь исходники и сборка.
COPY . .
RUN npm run build

# ─── Этап 2: отдача статики ──────────────────────────────────────────────
FROM caddy:2-alpine
COPY --from=build /app/dist /srv
COPY Caddyfile /etc/caddy/Caddyfile
EXPOSE 80
