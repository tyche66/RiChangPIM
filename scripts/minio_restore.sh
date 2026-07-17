#!/usr/bin/env bash
# AI-PIM MinIO bucket restore.
#
# Restore only to an explicitly supplied test bucket/instance unless production
# recovery has been approved. This script never deletes Docker volumes.
set -euo pipefail

ARCHIVE="${1:-}"
if [ -z "$ARCHIVE" ] || [ ! -f "$ARCHIVE" ]; then
  printf 'Usage: %s <backup.tar.gz>\n' "$0" >&2
  exit 1
fi

MINIO_ALIAS="${MINIO_ALIAS:-ai-pim-restore}"
MINIO_ENDPOINT="${MINIO_ENDPOINT:?MINIO_ENDPOINT is required}"
MINIO_ROOT_USER="${MINIO_ROOT_USER:?MINIO_ROOT_USER is required}"
MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD is required}"
MINIO_BUCKET="${MINIO_BUCKET:?MINIO_BUCKET restore target is required}"
RESTORE_TMP="${RESTORE_TMP:-/tmp/opencode/ai-pim-minio-restore}"

rm -rf "$RESTORE_TMP"
mkdir -p "$RESTORE_TMP"
tar -C "$RESTORE_TMP" -xzf "$ARCHIVE"
SRC_DIR="$(find "$RESTORE_TMP" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
if [ -z "$SRC_DIR" ]; then
  printf 'Archive does not contain a restore directory: %s\n' "$ARCHIVE" >&2
  exit 1
fi

mc alias set "$MINIO_ALIAS" "$MINIO_ENDPOINT" "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
mc mb --ignore-existing "${MINIO_ALIAS}/${MINIO_BUCKET}"
mc mirror --overwrite "$SRC_DIR" "${MINIO_ALIAS}/${MINIO_BUCKET}"

printf 'MinIO restore completed: %s -> %s/%s\n' "$ARCHIVE" "$MINIO_ENDPOINT" "$MINIO_BUCKET"
