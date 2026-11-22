#!/bin/sh
# Restore a backup into a NEW database on the docker compose `db` service.
#
#   sh backend/scripts/restore.sh <dump-file> <new-database-name>
#
# It never overwrites an existing database. To go live with the restored
# copy, stop the backend, point ENVO_DATABASE_URL at the new database (or
# rename it), run `alembic upgrade head` and start the backend again. Check
# it first with:
#
#   python -m app.modules.variables.verify --database <new-database-name>
set -eu

if [ $# -ne 2 ]; then
  echo "usage: $0 <dump-file> <new-database-name>" >&2
  exit 2
fi
DUMP="$1"
TARGET="$2"
DB_USER="${ENVO_DB_USER:-envo}"

case "$TARGET" in
  *[!a-z0-9_]* | "" | [0-9]*)
    echo "database name must be lowercase letters, digits and underscores" >&2
    exit 2
    ;;
esac

if [ -f "$DUMP.sha256" ]; then
  (cd "$(dirname "$DUMP")" && sha256sum -c "$(basename "$DUMP").sha256" >/dev/null)
  echo "checksum OK"
else
  echo "warning: no $DUMP.sha256 next to the dump; integrity not checked" >&2
fi

exists=$(docker compose exec -T db psql -U "$DB_USER" -d postgres -tAc \
  "SELECT 1 FROM pg_database WHERE datname = '$TARGET'")
if [ "$exists" = "1" ]; then
  echo "database $TARGET already exists; choose a new name" >&2
  exit 1
fi

docker compose exec -T db createdb -U "$DB_USER" "$TARGET"
docker compose exec -T db pg_restore -U "$DB_USER" -d "$TARGET" --no-owner --exit-on-error < "$DUMP"
echo "restored $DUMP into database $TARGET"
