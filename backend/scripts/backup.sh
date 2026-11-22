#!/bin/sh
# Back up the Envo database from the docker compose `db` service.
#
#   sh backend/scripts/backup.sh [output-dir]      (default: backups/)
#
# Writes envo-<UTC time>.dump (pg_dump custom format) and a .sha256 next to it.
#
# The master key (ENVO_MASTER_KEY) is NOT part of the dump. Back it up
# separately, under different access control: the dump cannot be decrypted
# without the key, and the key alone reveals nothing. The dump still holds
# password hashes and encrypted values: store it encrypted and restricted.
set -eu

OUT_DIR="${1:-backups}"
DB_USER="${ENVO_DB_USER:-envo}"
DB_NAME="${ENVO_DB_NAME:-envo}"

umask 077
mkdir -p "$OUT_DIR"
NAME="envo-$(date -u +%Y%m%dT%H%M%SZ).dump"

docker compose exec -T db pg_dump -U "$DB_USER" -d "$DB_NAME" --format=custom --no-owner \
  > "$OUT_DIR/$NAME.partial"
mv "$OUT_DIR/$NAME.partial" "$OUT_DIR/$NAME"
(cd "$OUT_DIR" && sha256sum "$NAME" > "$NAME.sha256")

echo "$OUT_DIR/$NAME"
