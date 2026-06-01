@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Realty AI - публичная ссылка

set "NGDOM=pagan-crawling-retiring.ngrok-free.dev"
if exist ".env" (
  for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
    if /i "%%a"=="NGROK_DOMAIN" if not "%%b"=="" set "NGDOM=%%b"
  )
)

echo Постоянный адрес для @BotFather:
echo ============================================
echo    https://%NGDOM%
echo ============================================
echo.
echo Последние строки туннеля ngrok (должно быть "started tunnel"):
docker compose logs --tail=15 ngrok 2>nul
echo.
pause
