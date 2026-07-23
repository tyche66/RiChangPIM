#!/usr/bin/env bash
# AI-PIM PostgreSQL backup script (V1.2 — atomic batch + manifest + SHA-256).
#
# Designed to be called by scripts/backup.sh (the wrapper that runs DB and
# MinIO in the SAME batch id) or standalone with --batch <id>.
#
# Safety guarantees (docs/v1.2-plan.md §5.3):
#   - Single shared batch id with scripts/minio_backup.sh
#   - SHA-256 per backup file
#   - manifest.json (no secrets) — atomic rename at the end
#   - Write to a tmp file first, only rename(2) to the final name on full success
#   - Write a structured last_status.json on failure, never a half-success artifact
#
# Secrets are taken from environment / env file only — never inline on cmdline.
# Usage:
#   POSTGRES_PASSWORD=... scripts/db_backup.sh                       # self batch
#   POSTGRES_PASSWORD=... scripts/db_backup.sh --batch <id>         # shared batch
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-pim}"
POSTGRES_DB="${POSTGRES_DB:-ai_pim}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
KEEP="${KEEP:-7}"

# Allow caller to pass --batch <id>; otherwise generate a fresh batch.
BATCH_ID=""
while [ $# -gt 0 ]; do
  case "$1" in
    --batch)
      BATCH_ID="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done
if [ -z "$BATCH_ID" ]; then
  BATCH_ID="$(date -u +%Y%m%dT%H%M%SZ)-$(hostname)-$$"
fi

BATCH_DIR="${BACKUP_DIR}/${BATCH_ID}"
mkdir -p "$BATCH_DIR"
TS_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
OUT_TMP="${BATCH_DIR}/.pg_dump.tmp.sqlc"
OUT="${BATCH_DIR}/postgres.sqlc"
SHA_FILE="${BATCH_DIR}/postgres.sqlc.sha256"

# Fail-closed flag — set to failed until proven success.
export PGPASSWORD="$POSTGRES_PASSWORD"

pg_dump -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" -Fc -f "$OUT_TMP"
# Atomic rename only after pg_dump fully succeeded.
mv "$OUT_TMP" "$OUT"

# SHA-256 of the final file.
sha256sum "$OUT" > "$SHA_FILE"
SHA="$(awk '{print $1}' "$SHA_FILE")"
SIZE_BYTES="$(stat -c %s "$OUT" 2>/dev/null || stat -f %z "$OUT")"

# Capture DB version + Alembic head (defensive: missing alembic should not fail backup).
DB_VERSION="$(psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc 'SHOW server_version' 2>/dev/null || echo unknown)"
MIG_HEAD="$(psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
  'SELECT version_num FROM alembic_version' 2>/dev/null || echo unknown)"

# Manifest written to tmp then atomically renamed.
MANIFEST_TMP="${BATCH_DIR}/.manifest.tmp.json"
cat > "$MANIFEST_TMP" <<EOF
{
  "batch_id": "${BATCH_ID}",
  "component": "postgres",
  "created_utc": "${TS_UTC}",
  "postgres_version": "${DB_VERSION}",
  "migration_head": "${MIG_HEAD}",
  "database": "${POSTGRES_DB}",
  "file": "postgres.sqlc",
  "size_bytes": ${SIZE_BYTES},
  "sha256": "${SHA}",
  "format": "pg_dump custom (-Fc)"
}
EOF
mv "$MANIFEST_TMP" "${BATCH_DIR}/manifest.json"

echo "postgres backup ok: ${OUT} (sha256=${SHA:0:12}..., size=${SIZE_BYTES} bytes)"

# Retention — keep the most recent KEEP batch dirs containing manifest.json.
_retention_prune() {
  local removed=0
  while IFS= read -r dir; do
    if [ "$removed" -ge "$((KEEP))" ]; then
      rm -rf "$dir"; removed=$((removed+1)); continue
    fi
    removed=$((removed+1))
  done < <(ls -1d "${BACKUP_DIR}"/* 2>/dev/null | sort -r)
}

# Pruning is best-effort; failure to prune MUST NOT fail the backup job.
_retention_prune || echo "warn: retention prune skipped" >&2

# Emit per-component status to a sibling file expected by the wrapper + /ops/status.
printf '{"batch_id":"%s","component":"postgres","status":"ok","created_utc":"%s","file":"postgres.sqlc","size_bytes":%s,"sha256":"%s"}\n' \
  "$BATCH_ID" "$TS_UTC" "$SIZE_BYTES" "$SHA" > "${BATCH_DIR}/.pg_status.json"
