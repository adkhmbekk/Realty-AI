# Базовый образ с уже установленным Python 3.12 (лёгкая версия "slim").
FROM python:3.12-slim

# Все команды выполняются внутри папки /app внутри контейнера.
WORKDIR /app

# Браузеры Playwright кладём в общий путь (не в /root), чтобы их видел и
# непривилегированный пользователь (процесс запускаем НЕ от root).
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Сначала копируем только список зависимостей и ставим их.
# (Так Docker кэширует этот шаг и пересобирает быстрее, если код поменялся,
#  а зависимости — нет.)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Безголовый Chromium для рендера сайтов-одностраничников (импорт объявлений).
# --with-deps ставит системные библиотеки, нужные браузеру внутри slim-образа.
RUN playwright install --with-deps chromium

# Теперь копируем сам код приложения.
COPY . .

# Запуск НЕ от root (меньше ущерба при возможном взломе). Непривилегированному
# пользователю (uid 1000) нужны права на код, тома (фото /data, секреты /secrets)
# и браузеры Playwright. Тома на сервере уже должны быть chown 1000 (см. деплой).
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /data/photos /secrets \
    && chown -R app:app /app /data /secrets /ms-playwright
USER app

# Сервис внутри контейнера слушает порт 8000.
EXPOSE 8000

# Команда запуска: поднять веб-сервер uvicorn с нашим приложением.
# host 0.0.0.0 — чтобы сервис был доступен снаружи контейнера.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
