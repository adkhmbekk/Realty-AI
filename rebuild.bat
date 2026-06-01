@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Realty AI - полная пересборка

echo ============================================
echo   ПОЛНАЯ ПЕРЕСБОРКА (использовать после
echo   обновления, если обычный start.bat не
echo   подхватил изменения backend)
echo ============================================
echo.

docker info >nul 2>&1
if errorlevel 1 (
  echo [!] Docker не запущен. Открой Docker Desktop и попробуй снова.
  echo.
  pause
  exit /b 1
)

echo Останавливаем...
docker compose down

echo.
echo Пересобираем backend и frontend с нуля (это дольше обычного)...
docker compose build --no-cache backend web
if errorlevel 1 (
  echo.
  echo [!] Ошибка при сборке. Прокрути сообщения выше.
  echo.
  pause
  exit /b 1
)

echo.
echo Запускаем...
docker compose up -d
echo.
echo Готово. Подожди ~10 секунд, затем покажи публичную ссылку командой url.bat
echo (постоянный адрес: https://pagan-crawling-retiring.ngrok-free.dev).
echo.
pause
