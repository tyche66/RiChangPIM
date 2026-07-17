#!/usr/bin/env bash
# AI-PIM MinIO bucket backup.
#
# Requires MinIO client (`mc`) on the host, or run the equivalent `mc mirror`
# from a temporary minio/mc container. Secrets must be supplied via environment
# variables or a controlled env file; do not commit real credentials.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups/minio}"
MINIO_ALIAS="${MINIO_ALIAS:-ai-pim}"
MINIO_ENDPOINT="${MINIO_ENDPOINT:?MINIO_ENDPOINT is required}"
MINIO_ROOT_USER="${MINIO_ROOT_USER:?MINIO_ROOT_USER is required}"
MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD is required}"
MINIO_BUCKET="${MINIO_BUCKET:-ai-pim-files}"
KEEP="${KEEP:-7}"

mkdir -p "$BACKUP_DIR"
TS="$(date +%Y%m%d_%H%M%S)"
OUT="${BACKUP_DIR}/${MINIO_BUCKET}_${TS}"

mc alias set "$MINIO_ALIAS" "$MINIO_ENDPOINT" "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
mc mirror --overwrite "${MINIO_ALIAS}/${MINIO_BUCKET}" "$OUT"

tar -C "$BACKUP_DIR" -czf "${OUT}.tar.gz" "$(basename "$OUT")"
rm -rf "$OUT"
sha256sum "${OUT}.tar.gz" > "${OUT}.tar.gz.sha256"

printf 'MinIO backup completed: %s\n' "${OUT}.tar.gz"

find "$BACKUP_DIR" -maxdepth 1 -name "${MINIO_BUCKET}_*.tar.gz" -type f -printf '%T@ %p\n' \
  | sort -r \
  | awk -v keep="$KEEP" 'NR>keep {print $2}' \
  | while read -r old; do rm -f "$old" "$old.sha256"; done
