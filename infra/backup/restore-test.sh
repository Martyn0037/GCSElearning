#!/bin/sh
# infra/backup/restore-test.sh
# Prove the newest backup restores: load it into a scratch database, check
# the schema version and that the core tables have rows, then drop it.
# Logs one JSON line. Exits non-zero on failure.
set -eu

: "${PGHOST:=postgres}" "${PGUSER:?}" "${PGDATABASE:?}"
latest="$(ls -1t /backups/gcse-*.dump 2>/dev/null | head -n 1 || true)"
scratch="restore_check"

log() { printf '{"service":"backup","event":"%s","file":"%s"%s}\n' "$1" "$(basename "${latest:-none}")" "${2:-}"; }

if [ -z "$latest" ]; then
  log restore_test_failed ',"reason":"no backup found"'
  exit 1
fi
dropdb --if-exists "$scratch"
createdb "$scratch"
cleanup() { dropdb --if-exists "$scratch" || true; }
trap cleanup EXIT

if ! pg_restore --no-owner --dbname="$scratch" "$latest"; then
  log restore_test_failed ',"reason":"pg_restore failed"'
  exit 1
fi
version="$(psql -d "$scratch" -tAc 'SELECT version_num FROM alembic_version')"
live_version="$(psql -tAc 'SELECT version_num FROM alembic_version')"
users="$(psql -d "$scratch" -tAc 'SELECT count(*) FROM users')"
objectives="$(psql -d "$scratch" -tAc 'SELECT count(*) FROM learning_objectives')"
if [ "$version" != "$live_version" ] || [ "$users" -lt 1 ] || [ "$objectives" -lt 1 ]; then
  log restore_test_failed ",\"schema\":\"${version}\",\"users\":${users},\"objectives\":${objectives}"
  exit 1
fi
log restore_test_passed ",\"schema\":\"${version}\",\"users\":${users},\"objectives\":${objectives}"
