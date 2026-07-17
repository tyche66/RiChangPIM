#!/usr/bin/env bash
# 幂等创建集成测试库 ai_pim_test（供 pytest 的 TEST_DATABASE_URL 使用）。
#
# 设计（与 db_backup.sh / db_restore.sh 一致）：
# - 全部参数经环境变量覆盖，无硬编码密钥；路径相对项目根（AI-PIM/）。
# - 优先用宿主机 psql（POSTGRES_HOST 可覆盖）；若设 DOCKER=1 或宿主机无
#   psql，则经 postgres 容器执行（容器自带客户端）。
# - 数据随 ./docker/volumes/postgres 留在项目目录内。
#
# 用法：
#   ./scripts/create_test_db.sh                 # 宿主机 psql（localhost:5432）
#   DOCKER=1 ./scripts/create_test_db.sh        # 经 docker compose 的 postgres 容器
#   POSTGRES_HOST=db.internal ./scripts/create_test_db.sh

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-pim}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-pim_password}"
POSTGRES_DB="${POSTGRES_DB:-ai_pim}"
TEST_DB="${TEST_DB:-ai_pim_test}"
USE_DOCKER="${DOCKER:-0}"

SQL=$(cat <<'EOSQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'ai_pim_test') THEN
    CREATE DATABASE ai_pim_test;
  END IF;
END
$$;
EOSQL
)

if [ "$USE_DOCKER" = "1" ]; then
  echo "==> 经 docker compose 的 postgres 容器创建测试库 ${TEST_DB}"
  cd "$PROJECT_ROOT"
  echo "$SQL" | docker compose -f docker-compose.dev.yml exec -T \
    -e PGPASSWORD="$POSTGRES_PASSWORD" postgres \
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1
else
  echo "==> 宿主机 psql 创建测试库 ${TEST_DB} (${POSTGRES_HOST}:${POSTGRES_PORT})"
  export PGPASSWORD="$POSTGRES_PASSWORD"
  echo "$SQL" | psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" \
    -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1
fi

echo "测试库就绪：${TEST_DB}（数据目录：./docker/volumes/postgres）"
