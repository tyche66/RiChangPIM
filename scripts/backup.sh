#!/usr/bin/env bash
# AI-PIM V1.2 unified backup wrapper.
#
# Runs scripts/db_backup.sh and scripts/minio_backup.sh with the SAME
# batch id, then writes a non-secret last_status.json consumed by
# /api/v1/ops/status and scripts/restore_drill.sh.
#
# Fail-closed: if either component fails, the overall batch is marked
# incomplete; partial DB-only success will NOT be promoted to a complete
# batch. Space pre-check prevents silent truncated writes.
#
# Secrets MUST come from an env file referenced via $ENV_FILE (loaded by the
# systemd unit / cron wrapper — never inline on the command line).
#
# Usage:
#   scripts/backup.sh                   # both components, fresh batch
#   BATCH_ID=2026-07-20T00Z-hostname-1 scripts/backup.sh
#   COMPONENTS=pg scripts/backup.sh      # subset; rare; for ops recovery
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
KEEP="${KEEP:-7}"
COMPONENTS="${COMPONENTS:-pg,minio}"

if [ -n "${ENV_FILE:-}" ] && [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

BATCH_ID="${BATCH_ID:-$(date -u +%Y%m%dT%H%M%SZ)-$(hostname)-$$}"
BATCH_DIR="${BACKUP_DIR}/${BATCH_ID}"

# Pre-check available disk space in the backup target directory.
NEED_BYTES="${BACKUP_MIN_FREE_BYTES:-$((5 * 1024 * 1024 * 1024))}"  # 5 GiB default
_avail_bytes() {
  df -P --block-size=1 "${BACKUP_DIR}" 2>/dev/null | awk 'NR==2 {print $4}'
}
FREE_BYTES="$(df -P --block-size=1 "${BACKUP_DIR}" 2>/dev/null | awk 'NR==2 {print $4}')"
if [ -n "$FREE_BYTES" ] && [ "$FREE_BYTES" -lt "$NEED_BYTES" ]; then
  echo "backup aborted: ${BACKUP_DIR} has ${FREE_BYTES} bytes free, needs >= ${NEED_BYTES}" >&2
  _write_failure_state "capacity" "available=${FREE_BYTES} threshold=${NEED_BYTES}"
  exit 3
fi

mkdir -p "$BATCH_DIR"

PG_OK=0
MINIO_OK=0
PG_ERR=""
MINIO_ERR=""

case ",$COMPONENTS," in
  *,pg,*)
    if ! bash "$(dirname "$0")/db_backup.sh" --batch "$BATCH_ID" 2> "${BATCH_DIR}/.pg.err.log"; then
      PG_ERR="$(cat "${BATCH_DIR}/.pg.err.log")"
    else
      PG_OK=1
    fi
    ;;
esac

case ",$COMPONENTS," in
  *,minio,*)
    if ! bash "$(dirname "$0")/minio_backup.sh" --batch "$BATCH_ID" 2> "${BATCH_DIR}/.minio.err.log"; then
      MINIO_ERR="$(cat "${BATCH_DIR}/.minio.err.log")"
    else
      MINIO_OK=1
    fi
    ;;
esac

# Fail-closed overall status: full success only when every requested component
# succeeded. Anything else is incomplete (or failed).
_write_success_state() {
  local state pg_label minio_label
  if [ "$PG_OK" = 1 ] && [ "$MINIO_OK" = 1 ]; then state="ok"
  elif [ "$PG_OK" = 1 ] || [ "$MINIO_OK" = 1 ]; then state="incomplete"
  else state="failed"; fi
  if [ "$PG_OK" = 1 ]; then pg_label="ok"; else pg_label="failed"; fi
  if [ "$MINIO_OK" = 1 ]; then minio_label="ok"; else minio_label="failed"; fi

  # Atomic write to last_status.json.
  TMP="${BACKUP_DIR}/.last_status.json.tmp"
  cat > "$TMP" <<EOF
{
  "batch_id": "${BATCH_ID}",
  "created_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "status": "${state}",
  "components": {
    "postgres": "${pg_label}",
    "minio": "${minio_label}"
  },
  "keep_count": ${KEEP}
}
EOF
  mv "$TMP" "${BACKUP_DIR}/last_status.json"
  echo "backup batch ${BATCH_ID}: ${state} (pg=${pg_label}, minio=${minio_label})"
}

_write_failure_state() {
  local reason="${1:-unknown}"
  local detail="${2:-}"
  local TMP="${BACKUP_DIR}/.last_status.json.tmp"
  mkdir -p "$BACKUP_DIR"
  cat > "$TMP" <<EOF
{
  "batch_id": "${BATCH_ID}",
  "created_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "status": "failed",
  "reason": "${reason}",
  "detail": "${detail}",
  "components": { "postgres": "$( [ $PG_OK = 1 ] && echo ok || echo failed )", "minio": "$( [ $MINIO_OK = 1 ] && echo ok || echo failed )" }
}
EOF
  mv "$TMP" "${BACKUP_DIR}/last_status.json"
}

if [ "$PG_OK" = 1 ] && [ "$MINIO_OK" = 1 ]; then
  _write_success_state
  exit 0
else
  _write_success_state
  exit 1
fi
