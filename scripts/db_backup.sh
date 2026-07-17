#!/usr/bin/env bash
# AI-PIM PostgreSQL 全量备份（pg_dump，自定义格式 .sqlc）。
#
# 依赖宿主机已安装 PostgreSQL 客户端（pg_dump），不在后端 Python 镜像内。
# 两种运行方式：
#   1) 宿主机直接运行（端口已映射到宿主机）：
#        POSTGRES_HOST=localhost ./scripts/db_backup.sh
#   2) 经 postgres 容器运行（容器自带客户端，无需宿主机安装）：
#        docker compose exec -T postgres pg_dump -U pim -d ai_pim -Fc \
#          > "backups/$(date +%Y%m%d_%H%M%S)_ai_pim.sqlc"
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-pim}"
POSTGRES_DB="${POSTGRES_DB:-ai_pim}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
KEEP="${KEEP:-7}"

mkdir -p "$BACKUP_DIR"
TS="$(date +%Y%m%d_%H%M%S)"
OUT="${BACKUP_DIR}/ai_pim_${TS}.sqlc"

export PGPASSWORD="$POSTGRES_PASSWORD"
pg_dump -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" -Fc -f "$OUT"

echo "备份完成: $OUT ($(du -h "$OUT" | cut -f1))"

# 仅保留最近 KEEP 份
find "$BACKUP_DIR" -maxdepth 1 -name 'ai_pim_*.sqlc' -type f -printf '%T@ %p\n' \
  | sort -r \
  | awk -v keep="$KEEP" 'NR>keep {print $2}' \
  | xargs -r rm -f
echo "已清理旧备份，保留最近 ${KEEP} 份。"
