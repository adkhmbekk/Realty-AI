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
echo [2/2] Получаем публичную ссылку для Telegram (10-20 сек)...
timeout /t 14 /nobreak >nul

echo.
echo ============================================
echo   ПУБЛИЧНАЯ ССЫЛКА (вставь её в @BotFather
echo   как URL Mini App, если адрес сменился):
echo ============================================
docker compose logs cloudflared 2>nul | findstr /C:"trycloudflare.com"
echo.
echo --------------------------------------------
echo   Локально (на этом компьютере):
echo     Приложение:  http://localhost:8080
echo     API / docs:  http://localhost:8000/docs
echo --------------------------------------------
echo.
echo Готово. Проект работает в фоне.
echo   - Посмотреть логи сервера:  logs.bat
echo   - Остановить проект:        stop.bat
echo   - Полная пересборка:        rebuild.bat
echo.
pause
