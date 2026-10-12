#!/usr/bin/env bash
# Backup database before migrations
# Usage: DATABASE_URL=postgresql://... bash scripts/backup.sh
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_FILE="$BACKUP_DIR/backup_$TIMESTAMP.sql"

if [ -z "${DATABASE_URL:-}" ]; then
  echo "ERROR: DATABASE_URL is required" >&2
  exit 1
fi

pg_dump "$DATABASE_URL" > "$OUTPUT_FILE"
echo "Backup saved to $OUTPUT_FILE"
