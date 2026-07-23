#!/usr/bin/env bash
# AI-PIM MinIO bucket backup script (V1.2 — atomic batch + manifest + SHA-256).
#
# Pair with scripts/db_backup.sh — the wrapper scripts/backup.sh supplies the
# SAME --batch id to both so the manifest for one backup batch groups the
# PostgreSQL dump and MinIO tarball together.
#
# Secrets (MinIO root creds) are taken from environment / env file only.
# Usage:
#   MINIO_ROOT_USER=... MINIO_ROOT_PASSWORD=... MINIO_ENDPOINT=... \
#     scripts/minio_backup.sh
#   MINIO_ROOT_USER=... MINIO_ROOT_PASSWORD=... MINIO_ENDPOINT=... \
#     scripts/minio_backup.sh --batch <id>
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
MINIO_ALIAS="${MINIO_ALIAS:-ai-pim}"
MINIO_ENDPOINT="${MINIO_ENDPOINT:?MINIO_ENDPOINT is required}"
MINIO_ROOT_USER="${MINIO_ROOT_USER:?MINIO_ROOT_USER is required}"
MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD is required}"
MINIO_BUCKET="${MINIO_BUCKET:-ai-pim-files}"
KEEP="${KEEP:-7}"

BATCH_ID=""
while [ $# -gt 0 ]; do
  case "$1" in
    --batch) BATCH_ID="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done
if [ -z "$BATCH_ID" ]; then
  BATCH_ID="$(date -u +%Y%m%dT%H%M%SZ)-$(hostname)-$$"
fi

BATCH_DIR="${BACKUP_DIR}/${BATCH_ID}"
mkdir -p "$BATCH_DIR"
TS_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

STAGE_DIR="${BATCH_DIR}/.minio_stage"
OUT_TMP="${BATCH_DIR}/.minio.tar.gz.tmp"
OUT="${BATCH_DIR}/minio.tar.gz"
SHA_FILE="${BATCH_DIR}/minio.tar.gz.sha256"

mkdir -p "$STAGE_DIR"

mc alias set "$MINIO_ALIAS" "$MINIO_ENDPOINT" "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
mc mirror --overwrite "${MINIO_ALIAS}/${MINIO_BUCKET}" "$STAGE_DIR" >/dev/null

# Compute object count BEFORE tarball for the manifest.
OBJECT_COUNT=$(find "$STAGE_DIR" -type f | wc -l)

tar -C "$BATCH_DIR" -czf "$OUT_TMP" "$(basename "$STAGE_DIR")"
# Atomic rename once the tarball is fully written.
mv "$OUT_TMP" "$OUT"
rm -rf "$STAGE_DIR"

sha256sum "$OUT" > "$SHA_FILE"
SHA="$(awk '{print $1}' "$SHA_FILE")"
SIZE_BYTES="$(stat -c %s "$OUT" 2>/dev/null || stat -f %z "$OUT")"

MANIFEST_TMP="${BATCH_DIR}/.manifest.minio.tmp.json"
cat > "$MANIFEST_TMP" <<EOF
{
  "batch_id": "${BATCH_ID}",
  "component": "minio",
  "created_utc": "${TS_UTC}",
  "bucket": "${MINIO_BUCKET}",
  "file": "minio.tar.gz",
  "size_bytes": ${SIZE_BYTES},
  "object_count": ${OBJECT_COUNT},
  "sha256": "${SHA}",
  "format": "tar.gz"
}
EOF
mv "$MANIFEST_TMP" "${BATCH_DIR}/manifest.minio.json"

echo "minio backup ok: ${OUT} (sha256=${SHA:0:12}..., size=${SIZE_BYTES} bytes, objects=${OBJECT_COUNT})"

# Per-component status consumed by wrapper + /ops/status.
printf '{"batch_id":"%s","component":"minio","status":"ok","created_utc":"%s","file":"minio.tar.gz","size_bytes":%s,"object_count":%s,"sha256":"%s"}\n' \
  "$BATCH_ID" "$TS_UTC" "$SIZE_BYTES" "$OBJECT_COUNT" "$SHA" > "${BATCH_DIR}/.minio_status.json"
