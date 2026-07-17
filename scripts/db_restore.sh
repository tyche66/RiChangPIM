#!/usr/bin/env bash
# AI-PIM PostgreSQL 恢复（pg_restore，配合 db_backup.sh 的 .sqlc 归档）。
# 用法：
#   POSTGRES_HOST=localhost ./scripts/db_restore.sh backups/ai_pim_20260101_120000.sqlc
# 注意：会先 --clean 清掉目标库内对象，请确认备份文件正确！
#
# 依赖宿主机已安装 PostgreSQL 客户端（pg_restore），不在后端 Python 镜像内。
# 也可经 postgres 容器运行（容器自带客户端）：
#   docker compose exec -T postgres pg_restore -U pim -d ai_pim --clean --if-exists \
#     --no-owner -f - < backups/ai_pim_20260101_120000.sqlc
set -euo pipefail

FILE="${1:-}"
if [ -z "$FILE" ] || [ ! -f "$FILE" ]; then
  echo "用法: $0 <backup.sqlc>" >&2
  exit 1
fi

POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-pim}"
POSTGRES_DB="${POSTGRES_DB:-ai_pim}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"

export PGPASSWORD="$POSTGRES_PASSWORD"
echo "恢复中: $FILE -> ${POSTGRES_USER}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
pg_restore -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" --clean --if-exists --no-owner "$FILE"
echo "恢复完成。"
