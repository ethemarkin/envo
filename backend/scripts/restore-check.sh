#!/bin/sh
# Restore drill: back up, restore into a scratch database, prove that every
# stored value decrypts with the configured master key, then drop the copy.
#
#   sh backend/scripts/restore-check.sh [dump-file]
#
# Without a dump file a fresh backup is taken first. Set KEEP=1 to keep the
# scratch database. VERIFY_CMD selects how the verifier runs; by default it
# runs inside the compose `backend` service, which has the master key.
set -eu

cd "$(dirname "$0")/../.."
DB_USER="${ENVO_DB_USER:-envo}"
SCRATCH="envo_restore_check_$(date -u +%Y%m%d%H%M%S)"
VERIFY_CMD="${VERIFY_CMD:-docker compose exec -T backend python -m app.modules.variables.verify}"

DUMP="${1:-}"
if [ -z "$DUMP" ]; then
  DUMP=$(sh backend/scripts/backup.sh backups)
  echo "backup: $DUMP"
fi

cleanup() {
  if [ "${KEEP:-0}" != "1" ]; then
    docker compose exec -T db dropdb -U "$DB_USER" --if-exists "$SCRATCH" || true
  fi
}
trap cleanup EXIT

sh backend/scripts/restore.sh "$DUMP" "$SCRATCH"
# shellcheck disable=SC2086
$VERIFY_CMD --database "$SCRATCH"
echo "restore check passed ($SCRATCH)"
