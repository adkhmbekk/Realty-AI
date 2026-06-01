@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Realty AI - запуск

echo ============================================
echo            Realty AI - ЗАПУСК
echo ============================================
echo.

REM Проверяем, запущен ли Docker.
docker info >nul 2>&1
if errorlevel 1 (
  echo [!] Docker не запущен.
  echo     Открой Docker Desktop, дождись зелёного значка и запусти этот файл снова.
  echo.
  pause
  exit /b 1
)

REM Проверяем файл .env с секретами (в нём теперь хранится токен ngrok).
if not exist ".env" (
  echo [!] Не найден файл .env с секретами.
  echo     Без него туннель ngrok не запустится. Сделай так:
  echo       1^) Скопируй файл .env.example и назови копию .env
  echo       2^) Открой .env Блокнотом и впиши строку: NGROK_AUTHTOKEN=твой_токен
  echo          Токен бери тут: https://dashboard.ngrok.com  (Your Authtoken^)
  echo.
  pause
  exit /b 1
)

echo [1/2] Собираем и запускаем проект... (первый раз дольше, дальше быстро)
echo.
docker compose up -d --build
if errorlevel 1 (
  echo.
  echo [!] Что-то пошло не так при запуске. Прокрути сообщения выше.
  echo.
  pause
  exit /b 1
)

echo.
echo [2/2] Поднимаем туннель ngrok (5-10 сек)...
timeout /t 8 /nobreak >nul

echo.
echo ============================================
echo   ПУБЛИЧНАЯ ССЫЛКА (постоянная) для Telegram.
echo   Один раз пропиши её в @BotFather как URL
echo   Mini App - дальше она не меняется:
echo ============================================
echo     https://pagan-crawling-retiring.ngrok-free.dev
echo.
echo --------------------------------------------
echo   Локально (на этом компьютере):
echo     Приложение:     http://localhost:8080
echo     API / docs:     http://localhost:8000/docs
echo     Панель ngrok:   http://localhost:4040
echo --------------------------------------------
echo.
echo Готово. Проект работает в фоне.
echo   - Показать публичную ссылку снова:  url.bat
echo   - Посмотреть логи сервера:          logs.bat
echo   - Остановить проект:                stop.bat
echo   - Полная пересборка:                rebuild.bat
echo.
pause
