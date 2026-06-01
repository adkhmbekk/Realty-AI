@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Realty AI - публичная ссылка

echo Текущая публичная ссылка туннеля (для @BotFather):
echo ============================================
docker compose logs cloudflared 2>nul | findstr /C:"trycloudflare.com"
echo ============================================
echo.
echo Если пусто - подожди 10-20 секунд после запуска и запусти снова.
echo.
pause
