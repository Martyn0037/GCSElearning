#!/bin/sh
# infra/backup/backup.sh
# Dump the database (custom format, compressed), keep BACKUP_KEEP_DAYS days
# locally, and upload to s3://$BACKUP_S3_BUCKET/$BACKUP_S3_PREFIX if a bucket
# is set (the bucket's lifecycle rule expires objects after 30 days).
# Logs one JSON line per run. Exits non-zero on failure.
set -eu

: "${PGHOST:=postgres}" "${PGUSER:?}" "${PGDATABASE:?}" "${BACKUP_KEEP_DAYS:=7}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
file="/backups/gcse-${stamp}.dump"

log() { printf '{"service":"backup","event":"%s","file":"%s"%s}\n' "$1" "$(basename "$file")" "${2:-}"; }

if ! pg_dump --format=custom --compress=9 --no-owner --file="$file.partial"; then
  rm -f "$file.partial"
  log backup_failed ',"step":"dump"'
  exit 1
fi
mv "$file.partial" "$file"
size="$(wc -c < "$file")"

if [ -n "${BACKUP_S3_BUCKET:-}" ]; then
  if ! aws s3 cp --only-show-errors --sse AES256 "$file" \
      "s3://${BACKUP_S3_BUCKET}/${BACKUP_S3_PREFIX:-gcse-coach}/$(basename "$file")"; then
    log backup_failed ',"step":"upload"'
    exit 1
  fi
fi

find /backups -name 'gcse-*.dump' -mtime +"$BACKUP_KEEP_DAYS" -delete
date -u +%s > /backups/.last-success
log backup_done ",\"bytes\":${size},\"uploaded\":$([ -n "${BACKUP_S3_BUCKET:-}" ] && echo true || echo false)"
