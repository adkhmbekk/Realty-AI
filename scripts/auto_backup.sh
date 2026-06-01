#!/bin/sh
# Авто-бэкап по расписанию. Запускается сервисом `backup` из docker-compose
# (образ postgres:16 — там есть pg_dump нужной версии). Складывает копии в
# папку backups\ в том же формате, что и ручной backup.bat, поэтому их можно
# восстановить тем же restore.bat (метка вида auto-ГГГГ-ММ-ДД_ЧЧ-ММ-СС).
#
# Настройки (через переменные окружения, см. docker-compose.yml / .env):
#   BACKUP_INTERVAL_HOURS — как часто делать копию (по умолчанию 24 ч);
#   BACKUP_KEEP           — сколько последних авто-копий хранить (по умолчанию 7);
#   PGPASSWORD/DB_*       — доступ к базе.
set -eu

INTERVAL_HOURS="${BACKUP_INTERVAL_HOURS:-24}"
KEEP="${BACKUP_KEEP:-7}"
DB_HOST="${DB_HOST:-db}"
DB_USER="${DB_USER:-realty}"
DB_NAME="${DB_NAME:-realty}"

mkdir -p /backups
echo "[auto-backup] запущен: интервал=${INTERVAL_HOURS}ч, хранить=${KEEP} копий"

while true; do
  TS="$(date +%Y-%m-%d_%H-%M-%S)"
  LABEL="auto-${TS}"
  echo "[auto-backup] создаю копию ${LABEL}…"

  if pg_dump -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" > "/backups/db_${LABEL}.sql" 2>/tmp/pgerr; then
    # Фотографии (том примонтирован только для чтения) — копируем рядом.
    if [ -d /data/photos ]; then
      cp -a /data/photos "/backups/photos_${LABEL}" 2>/dev/null || \
        echo "[auto-backup] фото скопировать не удалось (возможно, их ещё нет)"
    fi
    echo "[auto-backup] готово: ${LABEL}"
  else
    echo "[auto-backup] ОШИБКА pg_dump: $(cat /tmp/pgerr 2>/dev/null)"
    rm -f "/backups/db_${LABEL}.sql"
  fi

  # Чистим старые авто-копии: оставляем только KEEP самых свежих.
  # shellcheck disable=SC2012
  ls -1t /backups/db_auto-*.sql 2>/dev/null | tail -n +"$((KEEP + 1))" | while read -r old; do
    label="$(basename "$old" .sql)"      # db_auto-…
    label="${label#db_}"                 # auto-…
    rm -f "$old"
    rm -rf "/backups/photos_${label}"
    echo "[auto-backup] удалил старую копию ${label}"
  done

  sleep "$((INTERVAL_HOURS * 3600))"
done
