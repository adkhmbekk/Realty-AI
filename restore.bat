@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Realty AI - восстановление из копии
setlocal enabledelayedexpansion

echo ============================================
echo     Realty AI - ВОССТАНОВЛЕНИЕ ИЗ КОПИИ
echo ============================================
echo.
echo ВНИМАНИЕ: эта операция ЗАМЕНИТ текущую базу данных
echo данными из выбранной резервной копии. Используй её
echo только если нужно вернуть данные (например, после сбоя).
echo.

docker info >nul 2>&1
if errorlevel 1 (
  echo [!] Docker не запущен. Открой Docker Desktop и запусти проект (start.bat).
  echo.
  pause
  exit /b 1
)

if not exist "backups" (
  echo [!] Папка backups\ не найдена. Сначала создай копию через backup.bat.
  echo.
  pause
  exit /b 1
)

echo Доступные копии базы (метки):
echo --------------------------------------------
for %%f in (backups\db_*.sql) do (
  set "name=%%~nf"
  echo     !name:db_=!
)
echo --------------------------------------------
echo.

set "TS="
set /p "TS=Введи метку копии для восстановления (например 2026-06-01_14-30-05): "
if not defined TS (
  echo [!] Метка не введена. Отмена.
  echo.
  pause
  exit /b 1
)

if not exist "backups\db_%TS%.sql" (
  echo [!] Файл backups\db_%TS%.sql не найден. Проверь метку и повтори.
  echo.
  pause
  exit /b 1
)

echo.
echo Будет восстановлено из метки: %TS%
set "CONFIRM="
set /p "CONFIRM=Текущие данные будут ЗАМЕНЕНЫ. Напиши YES (большими буквами) для продолжения: "
if not "%CONFIRM%"=="YES" (
  echo Отмена. Ничего не изменено.
  echo.
  pause
  exit /b 0
)

echo.
echo [1/3] Пересоздаю чистую базу...
docker compose exec -T db psql -U realty -d postgres -c "DROP DATABASE IF EXISTS realty WITH (FORCE);" >nul 2>&1
docker compose exec -T db psql -U realty -d postgres -c "CREATE DATABASE realty OWNER realty;" >nul 2>&1
if errorlevel 1 (
  echo [!] Не удалось пересоздать базу. Операция прервана.
  echo.
  pause
  exit /b 1
)

echo [2/3] Загружаю данные из копии...
docker compose exec -T db psql -U realty -d realty < "backups\db_%TS%.sql" >nul 2>&1
if errorlevel 1 (
  echo [!] Ошибка при загрузке данных из копии.
  echo.
  pause
  exit /b 1
)

echo [3/3] Восстанавливаю фотографии...
if exist "backups\photos_%TS%" (
  docker compose cp "backups\photos_%TS%\." backend:/data/photos >nul 2>&1
) else (
  echo     (папки с фото для этой метки нет - пропускаю)
)

echo.
echo Перезапускаю backend, чтобы он увидел восстановленные данные...
docker compose restart backend >nul 2>&1

echo.
echo ============================================
echo   ГОТОВО. Данные восстановлены из метки %TS%.
echo ============================================
echo Открой приложение и проверь, что всё на месте.
echo.
pause
