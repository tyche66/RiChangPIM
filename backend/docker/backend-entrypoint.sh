#!/usr/bin/env bash
# AI-PIM 后端容器入口：等待 DB -> alembic 迁移 -> 初始管理员 -> 种子数据 -> 启动服务。
# 任何必要步骤真实失败时，以非零状态退出，绝不对外提供服务。
set -euo pipefail

DB_HOST="${DB_HOST:-postgres}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${POSTGRES_USER:-pim}"
DB_PASS="${POSTGRES_PASSWORD:-pim_password}"
DB_NAME="${POSTGRES_DB:-ai_pim}"

# DATABASE_URL 是应用与 Alembic 的权威目标；分项变量仅作为本地 Compose 回退。
DB_URL="${DATABASE_URL:-postgresql://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}}"
DB_URL="${DB_URL/postgresql+asyncpg:/postgresql:}"

# 临时 alembic 配置：成功/失败都必须清理。
TMP_INI="$(mktemp)"
cleanup() { rm -f "$TMP_INI"; }
trap cleanup EXIT

# 写覆盖后的 alembic 配置。
sed "s#^sqlalchemy.url = .*#sqlalchemy.url = ${DB_URL}#" alembic.ini > "$TMP_INI"

echo "[entrypoint] 等待配置的数据库就绪..."

# 注意：后端镜像基于 python:3.11-slim + libpq-dev，不含 pg_isready 二进制。
# 这里用镜像内已安装的 psycopg2 做连接探测，避免依赖未安装的系统客户端。
READY=0
for i in $(seq 1 30); do
  if python -c "import psycopg2, sys; psycopg2.connect(sys.argv[1], connect_timeout=5).close()" "$DB_URL" >/dev/null 2>&1; then
    READY=1
    echo "[entrypoint] 数据库就绪。"
    break
  fi
  echo "[entrypoint] 等待中... ($i/30)"
  sleep 2
done

if [ "$READY" -ne 1 ]; then
  echo "[entrypoint] 错误：重试 30 次仍无法连接数据库，容器以非零状态退出，不启动服务。" >&2
  exit 1
fi

echo "[entrypoint] 执行数据库迁移 alembic upgrade head ..."
# 迁移失败必须直接退出（set -e 已保证），绝不继续。
alembic -c "$TMP_INI" upgrade head

echo "[entrypoint] 初始化管理员用户（幂等，已存在则跳过）..."
# 真实异常会由 set -e 终止容器；仅“已存在”返回 0。
python -m app.scripts.init_admin

echo "[entrypoint] 写入 RBAC 种子数据（幂等，已存在则跳过）..."
# 真实异常会由 set -e 终止容器；仅“已存在”返回 0。
python -m app.scripts.seed_data

# 启动前清理临时文件；exec 替换进程，EXIT trap 不再触发。
cleanup

echo "[entrypoint] 启动服务 ..."
# exec 使 uvicorn 接管 PID 1，正确接收并转发 SIGTERM/SIGINT 等信号。
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
  --workers "${UVICORN_WORKERS:-2}" --no-access-log
