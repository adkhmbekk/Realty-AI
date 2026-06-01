@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Realty AI - публичная ссылка

echo ============================================
echo   ПУБЛИЧНАЯ ССЫЛКА (постоянная) для Telegram:
echo ============================================
echo     https://pagan-crawling-retiring.ngrok-free.dev
echo.
echo Эту ссылку прописывают в @BotFather как URL Mini App.
echo Она не меняется между запусками.
echo.
echo --------------------------------------------
echo   Проверяем, поднят ли туннель прямо сейчас...
echo --------------------------------------------

REM Спрашиваем у локальной панели ngrok её текущий публичный адрес.
REM Если строка ниже появилась - туннель работает.
curl -s http://localhost:4040/api/tunnels | findstr /C:"public_url"
if errorlevel 1 (
  echo [!] Не вижу активный туннель.
  echo     Запусти проект через start.bat и подожди 10 секунд.
)

echo.
echo Подробности и список запросов: http://localhost:4040
echo.
pause
