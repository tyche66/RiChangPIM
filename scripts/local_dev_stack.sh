#!/usr/bin/env bash
# 本地开发端（:888 Docker Compose 栈）的启停入口。
#
# 本机 :888 跑的是本地开发端，数据是开发样例，不是生产数据：
# 这里的 start / stop / restart / down 只会影响本机开发栈，随时可放心执行。
#
# 用法: scripts/local_dev_stack.sh {start|stop|stop-all|restart|status|logs}
#   start    构建前端产物并重建 backend / nginx（其余服务保持现状）
#   stop     只停 backend / nginx（postgres 等共享依赖不动，可直接 start）
#   stop-all 停整个本地开发栈（docker compose stop）
#   restart  stop 后 start
#   status   列出本地开发栈各服务状态
#   logs     跟随 nginx 与 backend 日志
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="${NVM_NODE_BIN:-/root/.nvm/versions/node/v24.18.0/bin}:$PATH"
export DOCKER_HOST="${DOCKER_HOST:-unix:///mnt/wsl/docker-desktop/shared-sockets/host-services/docker.proxy.sock}"
export DOCKER_CONTEXT="${DOCKER_CONTEXT:-default}"
cd "$BASE_DIR"

cmd_build() {
    bash scripts/build_frontends.sh 2>&1 | tee /tmp/local_dev_version.txt | tail -n 3
    META=$(grep -E '^==> APP_VERSION=' /tmp/local_dev_version.txt | tail -n 1)
    APP_VERSION=$(printf '%s' "$META" | sed -E 's/.*APP_VERSION=([^ ]+).*/\1/')
    BUILD_ID=$(printf '%s' "$META" | sed -E 's/.*BUILD_ID=([^ ]+).*/\1/')
    GIT_COMMIT=$(printf '%s' "$META" | sed -E 's/.*GIT_COMMIT=([^ ]+).*/\1/')
    BUILD_TIME=$(printf '%s' "$META" | sed -E 's/.*BUILD_TIME=([^ ]+).*/\1/')
    export APP_VERSION BUILD_ID GIT_COMMIT BUILD_TIME APP_ENV="${APP_ENV:-production}"
    docker compose build backend nginx
    docker compose up -d --no-deps backend nginx
}

cmd_stop() { docker compose stop backend nginx; }
cmd_stop_all() { docker compose stop; }
cmd_status() { docker compose ps; }
cmd_logs() { docker compose logs -f --tail=80 backend nginx; }

case "${1:-}" in
    start) cmd_build ;;
    stop) cmd_stop ;;
    stop-all) cmd_stop_all ;;
    restart) cmd_stop; cmd_build ;;
    status) cmd_status ;;
    logs) cmd_logs ;;
    *) echo "用法: $0 {start|stop|stop-all|restart|status|logs}" >&2; exit 1 ;;
esac
