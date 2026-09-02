#!/bin/sh
# Läuft dauerhaft im "backup"-Container: sichert die Postgres-DB sofort beim
# Start (damit ein frischer Stack nicht 24h auf die erste Sicherung wartet)
# und danach im Takt von BACKUP_INTERVAL_SECONDS. Alte Dumps über
# BACKUP_KEEP hinaus werden nach jedem Lauf gelöscht - so bleibt auch dann
# noch ein sauberer älterer Stand übrig, wenn der jüngste Dump aus einer
# bereits beschädigten Datenbank gezogen wurde.
set -eu

BACKUP_DIR="/backups"
KEEP="${BACKUP_KEEP:-14}"
INTERVAL="${BACKUP_INTERVAL_SECONDS:-86400}"

mkdir -p "$BACKUP_DIR"

while true; do
  ts=$(date -u +%Y%m%d-%H%M%S)
  file="$BACKUP_DIR/netzwache-${ts}.sql.gz"
  tmp="${file}.part"

  echo "[backup] $(date -u '+%F %T') starte Dump nach $file"
  if pg_dump -h "${PGHOST:-db}" -U "${PGUSER:-netzwache}" -d "${PGDATABASE:-netzwache}" | gzip > "$tmp"; then
    mv "$tmp" "$file"
    echo "[backup] OK: $file ($(du -h "$file" | cut -f1))"
  else
    echo "[backup] FEHLGESCHLAGEN für $ts" >&2
    rm -f "$tmp"
  fi

  # Retention: nur die KEEP jüngsten Dumps behalten
  ls -1t "$BACKUP_DIR"/netzwache-*.sql.gz 2>/dev/null | tail -n "+$((KEEP + 1))" | while read -r old; do
    echo "[backup] entferne alten Dump: $old"
    rm -f "$old"
  done

  sleep "$INTERVAL"
done
