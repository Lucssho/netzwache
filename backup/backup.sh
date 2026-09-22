#!/bin/sh
# Läuft dauerhaft im "backup"-Container: sichert die Postgres-DB sofort beim
# Start (damit ein frischer Stack nicht 24h auf die erste Sicherung wartet)
# und danach im Takt von BACKUP_INTERVAL_SECONDS.
#
# Ein Dump zählt nur, wenn er wirklich vollständig ist:
#  - pg_dump selbst muss mit Exit-Code 0 enden (bei "pg_dump | gzip" gilt in
#    POSIX-sh nur der Exit-Code von gzip - ein fehlgeschlagenes pg_dump wurde
#    so früher als "OK" mit einer 20-Byte-Datei verbucht),
#  - die gzip-Datei muss intakt sein und die Abschlusszeile von pg_dump
#    enthalten ("PostgreSQL database dump complete").
# Alte Dumps werden erst gelöscht, NACHDEM ein neuer, geprüfter Dump
# vorliegt - ein fehlgeschlagener Lauf darf nie einen guten Stand verdrängen.
# Nach einem Fehlschlag wird bald erneut versucht (BACKUP_RETRY_SECONDS),
# nicht erst nach einem ganzen Intervall.
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
KEEP="${BACKUP_KEEP:-14}"
INTERVAL="${BACKUP_INTERVAL_SECONDS:-86400}"
RETRY="${BACKUP_RETRY_SECONDS:-300}"
MIN_BYTES="${BACKUP_MIN_BYTES:-1024}"
ONCE="${BACKUP_ONCE:-0}"   # 1 = genau ein Lauf, Exit-Code = Ergebnis (für Tests)

mkdir -p "$BACKUP_DIR"

# Intakt: nicht winzig, gzip-Prüfsumme stimmt.
is_valid() {
  [ -f "$1" ] && [ "$(wc -c < "$1")" -ge "$MIN_BYTES" ] && gzip -t "$1" 2>/dev/null
}

# Vollständig: pg_dump hat seine Abschlusszeile geschrieben.
is_complete() {
  gzip -dc "$1" 2>/dev/null | tail -n 5 | grep -q "PostgreSQL database dump complete"
}

run_backup() {
  ts=$(date -u +%Y%m%d-%H%M%S)
  file="$BACKUP_DIR/netzwache-${ts}.sql.gz"
  tmp="${file}.part"
  rc_file="${tmp}.rc"

  echo "[backup] $(date -u '+%F %T') starte Dump nach $file"

  # Exit-Code von pg_dump separat festhalten - die Pipeline selbst liefert
  # nur den von gzip.
  ( rc=0
    pg_dump -h "${PGHOST:-db}" -U "${PGUSER:-netzwache}" -d "${PGDATABASE:-netzwache}" || rc=$?
    echo "$rc" > "$rc_file"
  ) | gzip > "$tmp" || true
  dump_rc=$(cat "$rc_file" 2>/dev/null || echo 1)
  rm -f "$rc_file"

  if [ "$dump_rc" = "0" ] && is_valid "$tmp" && is_complete "$tmp"; then
    mv "$tmp" "$file"
    echo "[backup] OK: $file ($(du -h "$file" | cut -f1))"
    return 0
  fi

  echo "[backup] FEHLGESCHLAGEN für $ts (pg_dump Exit-Code $dump_rc) - vorhandene Dumps bleiben unangetastet" >&2
  rm -f "$tmp"
  return 1
}

# Nur nach einem erfolgreichen Lauf aufrufen.
prune() {
  # Kaputte/leere Dumps (z.B. 20-Byte-Reste alter Fehlläufe) zählen nicht als
  # Sicherung und dürfen keinen Platz in der Aufbewahrung belegen.
  for f in "$BACKUP_DIR"/netzwache-*.sql.gz; do
    [ -e "$f" ] || continue
    if ! is_valid "$f"; then
      echo "[backup] entferne ungültigen Dump: $f"
      rm -f "$f"
    fi
  done
  # Retention: nur die KEEP jüngsten (gültigen) Dumps behalten.
  ls -1t "$BACKUP_DIR"/netzwache-*.sql.gz 2>/dev/null | tail -n "+$((KEEP + 1))" | while read -r old; do
    echo "[backup] entferne alten Dump: $old"
    rm -f "$old"
  done
}

while true; do
  if run_backup; then
    prune
    status=0
    wait_s="$INTERVAL"
  else
    status=1
    wait_s="$RETRY"
  fi
  [ "$ONCE" = "1" ] && exit "$status"
  sleep "$wait_s"
done
