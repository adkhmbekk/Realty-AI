@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Realty AI - остановка

echo Останавливаем проект...
docker compose down
echo.
echo Проект остановлен. Данные (база и фото) сохранены.
echo.
pause
