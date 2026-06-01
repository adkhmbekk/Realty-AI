@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Realty AI - резервная копия

echo ============================================
echo        Realty AI - РЕЗЕРВНАЯ КОПИЯ
echo ============================================
echo.
echo Сохраню в папку backups\:
echo   - базу данных (объекты, команды, агентства);
echo   - все загруженные фотографии.
echo.

REM Проект должен быть запущен (нужны работающие контейнеры).
docker info >nul 2>&1
if errorlevel 1 (
  echo [!] Docker не запущен. Открой Docker Desktop и запусти проект (start.bat).
  echo.
  pause
  exit /b 1
)

REM Метка времени вида 2026-06-01_14-30-05 (через PowerShell - надёжно при любых настройках Windows).
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HH-mm-ss"') do set "TS=%%i"

if not exist "backups" mkdir "backups"

echo [1/2] Сохраняю базу данных...
docker compose exec -T db pg_dump -U realty -d realty > "backups\db_%TS%.sql"
if errorlevel 1 (
  echo [!] Не удалось сохранить базу. Запущен ли проект? Попробуй start.bat, затем повтори.
  del "backups\db_%TS%.sql" >nul 2>&1
  echo.
  pause
  exit /b 1
)

echo [2/2] Сохраняю фотографии...
docker compose cp backend:/data/photos "backups\photos_%TS%" >nul 2>&1
if errorlevel 1 (
  echo [!] Базу сохранил, но фотографии скопировать не вышло. Возможно, фото ещё нет - это не страшно.
)

echo.
echo ============================================
echo   ГОТОВО. Резервная копия создана:
echo ============================================
echo     Метка:  %TS%
echo     База:   backups\db_%TS%.sql
echo     Фото:   backups\photos_%TS%\
echo.
echo Запомни эту метку (%TS%) - она понадобится для восстановления (restore.bat).
echo Совет: иногда копируй папку backups\ на флешку или в облако.
echo.
pause
