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
  echo [!] Docker Desktop не запущен.
  echo     Открой Docker Desktop, дождись зелёного значка и запусти этот файл снова.
  echo.
  pause
  exit /b 1
)

REM Читаем постоянный домен ngrok из .env.
set "NGDOM="
if exist ".env" (
  for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
    if /i "%%a"=="NGROK_DOMAIN" set "NGDOM=%%b"
  )
)

echo [1/2] Собираем и запускаем (первый раз дольше, потом быстро)...
echo.
docker compose up -d --build
echo.

echo [2/2] Статус контейнеров (все должны быть "running"/"Up"):
echo --------------------------------------------
docker compose ps
echo --------------------------------------------
echo.

echo ============================================
if defined NGDOM (
  echo   ПОСТОЯННЫЙ адрес для Telegram (вставь в @BotFather ОДИН раз^):
  echo.
  echo        https://%NGDOM%
  echo.
  echo   Этот адрес НЕ меняется между запусками.
) else (
  echo   [!] В файле .env не задан NGROK_DOMAIN.
  echo   Добавь в .env строки:
  echo        NGROK_AUTHTOKEN=твой_токен
  echo        NGROK_DOMAIN=твой-домен.ngrok-free.app
  echo   и запусти start.bat снова.
)
echo ============================================
echo.
echo   Проверка локально (в браузере на ПК): http://localhost:8080
echo.
echo Команды: logs.bat (логи)  ^|  url.bat (адрес)  ^|  stop.bat (стоп)
echo.
pause
