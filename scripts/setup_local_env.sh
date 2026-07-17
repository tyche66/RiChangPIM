#!/usr/bin/env bash
# ============================================================================
# AI-PIM 本地/CI 一体化环境引导
#
# 一条命令完成「阶段构建审查」要求的专用库实跑：
#   1) 启动依赖服务（postgres + pgvector / redis / minio / gotenberg）
#   2) 等待 postgres 就绪，幂等创建测试库 ai_pim_test
#   3) Alembic upgrade head（含 0005 修复 partial unique）
#   4) seed_data 装后种子（角色/权限/映射 + admin 用户）
#   5) 全量 pytest（DeprecationWarning 视为 error）
#
# 环境隔离（全部限制在 AI-PIM 目录内）：
#   - 数据：./docker/volumes/postgres（postgres）/ redis / minio
#   - 日志：./logs   备份：./backups
#   - 密钥：仅从环境变量或 *.env.example 占位值读取，绝不写死
# 可移植性（服务器部署）：
#   - 所有参数经环境变量覆盖；compose 服务用 ${VAR:-默认}，真实秘钥
#     经 env/K8s 注入即可，无需改动本文件
#   - 服务器改命名卷：PG_DATA=pg_data / REDIS_DATA=redis_data /
#     MINIO_DATA=minio_data（已在 compose 声明）
#   - 测试库若不在本机，设 TEST_DATABASE_URL=<服务器测试库>，
#     且库名不含 "test" 时设 AI_PIM_TEST_DB_APPROVED=1
#
# 前置：已安装 Docker（含 compose 插件）与本仓库 venv（backend/venv）。
# 若本机无 Docker/Postgres，本脚本无法执行，但配置已就绪，可在有
# Docker 的主机/服务器上直接运行。
# ============================================================================

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

# ---- 依赖服务环境变量（可被真实部署覆盖；均提供默认值，避免 set -u 下 unbound variable）----
export POSTGRES_DB="${POSTGRES_DB:-ai_pim}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-pim_password}"
export POSTGRES_USER="${POSTGRES_USER:-pim}"
export MINIO_ROOT_USER="${MINIO_ROOT_USER:-pim_minio}"
export MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-pim_minio_secret}"
export JWT_SECRET="${JWT_SECRET:-change_me_in_production_ai_pim_local}"
# 测试库连接参数（仅用于本机/CI 一键实跑；库名含 test 或设置 AI_PIM_TEST_DB_APPROVED=1）
export TEST_DATABASE_URL="${TEST_DATABASE_URL:-postgresql+asyncpg://pim:pim_password@localhost:5432/ai_pim_test}"
export DATABASE_URL="${DATABASE_URL:-postgresql://pim:pim_password@localhost:5432/ai_pim}"

# 在干净 shell（env -i，未设置任何项目变量）下，所有变量均应有默认值且可被覆盖。
# 下面打印解析后的关键配置（密钥做掩码），便于核查变量展开，也避免脚本在
# 未设置变量时因 set -u 退出。绝不写死生产密钥。
echo "==> 解析后的运行配置（密钥掩码）："
echo "    POSTGRES_DB=${POSTGRES_DB}  POSTGRES_USER=${POSTGRES_USER}"
echo "    TEST_DATABASE_URL=${TEST_DATABASE_URL}"
echo "    DATABASE_URL=${DATABASE_URL}"
echo "    MINIO_ROOT_USER=${MINIO_ROOT_USER}  JWT_SECRET=${JWT_SECRET:+***set***}"

# docker 不可用则无法拉起依赖；给出明确提示并以非零退出（非 unbound variable）。
# 真实部署主机上 docker 可见，正常继续后续步骤。
if ! command -v docker >/dev/null 2>&1; then
  echo "==> [skip] 未检测到 docker，无法启动 postgres/redis/minio/gotenberg 依赖服务。" >&2
  echo "==> 请在已安装 Docker 的主机执行本脚本；变量已确认可在干净 shell 下正确展开。" >&2
  exit 1
fi

COMPOSE="docker compose -f docker-compose.dev.yml"

echo "==> [1/5] 启动依赖服务 (postgres/redis/minio/gotenberg)"
$COMPOSE up -d postgres redis minio gotenberg

echo "==> [2/5] 等待 postgres 就绪"
for _ in $(seq 1 30); do
  if $COMPOSE exec -T postgres pg_isready -U "$POSTGRES_USER" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "==> [2/5] 幂等创建测试库 ai_pim_test"
DOCKER=1 POSTGRES_DB="$POSTGRES_DB" POSTGRES_USER="$POSTGRES_USER" \
  POSTGRES_PASSWORD="$POSTGRES_PASSWORD" ./scripts/create_test_db.sh

cd "$PROJECT_ROOT/backend"

echo "==> [3/5] Alembic upgrade head（迁移建表 + 0005 修复）"
./venv/bin/alembic upgrade head

echo "==> [4/5] 装后种子（角色/权限/映射 + admin 用户）"
./venv/bin/python -m app.scripts.seed_data

echo "==> [5/5] 全量 pytest（DeprecationWarning 视为 error）"
./venv/bin/python -m pytest -W error::DeprecationWarning

echo "==> 完成。测试库 ai_pim_test 已就绪，数据位于 ./docker/volumes/postgres"
