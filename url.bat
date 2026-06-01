@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Realty AI - публичная ссылка

set "NGDOM="
if exist ".env" (
  for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
    if /i "%%a"=="NGROK_DOMAIN" set "NGDOM=%%b"
  )
)

echo Постоянный адрес для @BotFather:
echo ============================================
if defined NGDOM (
  echo    https://%NGDOM%
) else (
  echo    [!] NGROK_DOMAIN не задан в .env
)
echo ============================================
echo.
echo Проверить, что туннель поднялся (последние строки ngrok):
docker compose logs --tail=15 ngrok 2>nul
echo.
pause
