@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Realty AI - логи сервера

echo Живые логи backend. Чтобы выйти — нажми Ctrl+C, затем закрой окно.
echo (Полезно, когда что-то не работает — присылай это разработчику.)
echo.
docker compose logs -f --tail=50 backend
pause
