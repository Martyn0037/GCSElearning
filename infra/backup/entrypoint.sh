#!/bin/sh
# infra/backup/entrypoint.sh
# "run" (default): back up at BACKUP_AT each day (London time) and test a
# restore every Sunday. "backup" or "restore-test": run once and exit.
set -eu

case "${1:-run}" in
  backup) exec backup.sh ;;
  restore-test) exec restore-test.sh ;;
  run) ;;
  *) echo "usage: entrypoint.sh [run|backup|restore-test]" >&2; exit 2 ;;
esac

at="${BACKUP_AT:-02:30}"
while true; do
  now="$(date +%s)"
  target="$(date -d "$(date +%Y-%m-%d) ${at}" +%s 2>/dev/null || date -D '%Y-%m-%d %H:%M' -d "$(date +%Y-%m-%d) ${at}" +%s)"
  if [ "$target" -le "$now" ]; then target=$((target + 86400)); fi
  sleep $((target - now))
  backup.sh || true
  if [ "$(date +%u)" = "7" ]; then restore-test.sh || true; fi
done
