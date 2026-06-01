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
  echo     Открой Docker Desktop, дождись зелёного значка слева внизу,
  echo     и запусти этот файл снова.
  echo.
  pause
  exit /b 1
)

echo [1/3] Собираем и запускаем (первый раз дольше, потом быстро)...
echo.
docker compose up -d --build
echo.

echo [2/3] Статус контейнеров (все должны быть "running"/"Up"):
echo --------------------------------------------
docker compose ps
echo --------------------------------------------
echo.

echo [3/3] Получаем публичный адрес туннеля (до ~30 сек)...
set "FOUND="
for /L %%i in (1,1,15) do (
  docker compose logs cloudflared 2>nul | findstr /C:"trycloudflare.com" >nul && set "FOUND=1"
  if defined FOUND goto :showurl
  timeout /t 2 /nobreak >nul
)
:showurl
echo.
echo ============================================
echo   ПУБЛИЧНАЯ ССЫЛКА для Telegram:
echo ============================================
docker compose logs cloudflared 2>nul | findstr /C:"trycloudflare.com"
echo ============================================
echo.
echo   !!! ВАЖНО !!!
echo   Этот адрес МЕНЯЕТСЯ при каждом перезапуске.
echo   Скопируй ссылку выше (https://....trycloudflare.com) и вставь её
echo   в @BotFather: /mybots - твой бот - Bot Settings - Menu Button / Mini App URL.
echo   Без этого Mini App будет открывать СТАРЫЙ (мёртвый) адрес.
echo.
echo   (Это лечится постоянным адресом - спроси разработчика про ngrok.)
echo.
echo   Проверка локально (в браузере на ПК): http://localhost:8080
echo.
echo Команды: logs.bat (логи)  ^|  url.bat (показать ссылку)  ^|  stop.bat (стоп)
echo.
pause
