#!/usr/bin/env bash
# 「我现在到底在跟哪套环境说话？」——一条命令看清生产/开发/测试三套东西的真实状态。
#
# 为什么需要它：2026-07-31 出过一次事故级的误会。当时把一个开发后端指到了本机
# 原生 PG18 的 ai_pim（那是个只有 1 个 admin、0 个商品的空库），前端看起来一切正常，
# 但所有密码都「错」——因为真正的数据在 Docker 里 pg16 容器的命名卷里。空库和生产库
# 同名、端口不同、都叫 ai_pim，肉眼完全分不出来。
#
# 用法：bash scripts/where-am-i.sh
set -uo pipefail

cd "$(cd "$(dirname "$0")/.." && pwd)"

# RiChangPIM 这个发行版没开 Docker Desktop 的 WSL integration，~/.docker 里的
# desktop-linux context 指向 Windows 的 npipe，在这里用会直接 panic。走 Docker
# Desktop 铺在 /mnt/wsl 下的 unix socket 才能连上。
DD_SOCK=/mnt/wsl/docker-desktop/shared-sockets/host-services/docker.proxy.sock
if [ -S "$DD_SOCK" ]; then
  export DOCKER_HOST="unix://$DD_SOCK"
  export DOCKER_CONTEXT=default
fi

# 发行版里 export 了 http_proxy/HTTPS_PROXY=127.0.0.1:7890，不加 --noproxy 连本机都会
# 被送去代理，拿到的 502 会让人误判服务没起来。
C() { curl -sS --noproxy '*' -m 8 "$@"; }

hr() { printf '%s\n' '--------------------------------------------------------------'; }

echo "生产（Docker Desktop 里的 compose 栈，数据在命名卷里）"
hr
if docker version >/dev/null 2>&1; then
  docker compose ps --format '  {{.Service}}\t{{.Status}}' 2>/dev/null || echo "  compose 项目没在跑"
  echo
  BACKEND_DB="$(docker exec richangpim-backend-1 python -c "
import os, re
url = os.environ.get('DATABASE_URL', '')
print(re.sub(r'//([^:]+):[^@]*@', r'//\\1:***@', url))
" 2>/dev/null)"
  echo "  后端连的库: ${BACKEND_DB:-<容器没在跑>}"
  echo "  （postgres 那个主机名只在 compose 网络里解析，宿主机上 ping 不到，这是对的）"
  ALEMBIC="$(docker exec richangpim-backend-1 alembic current 2>/dev/null | tail -1)"
  echo "  alembic:    ${ALEMBIC:-<未知>}"
  USERS="$(docker exec richangpim-postgres-1 psql -U pim -d ai_pim -tAc 'select count(*) from "user"' 2>/dev/null | tr -d ' ')"
  PRODUCTS="$(docker exec richangpim-postgres-1 psql -U pim -d ai_pim -tAc 'select count(*) from product' 2>/dev/null | tr -d ' ')"
  echo "  数据规模:   用户 ${USERS:-?} / 商品 ${PRODUCTS:-?}  <- 生产应该是 7 个用户量级，不是 1"
else
  echo "  连不上 Docker daemon（Docker Desktop 没开？）"
fi

echo
echo "生产入口"
hr
# curl 连不上时 %{http_code} 会打 000 并且退出码非 0，两个都输出会拼成「000连不上」，
# 所以先拿到码再翻译，别用 `... || echo`。
code() {
  local c
  c="$(C -o /dev/null -w '%{http_code}' "$1" 2>/dev/null)"
  case "${c:-000}" in
    000|'') echo "连不上" ;;
    *)      echo "$c" ;;
  esac
}
printf '  http://127.0.0.1:888/api/v1/health -> %s\n' "$(code http://127.0.0.1:888/api/v1/health)"
printf '  http://127.0.0.1:888/  (门户)       -> %s\n' "$(code http://127.0.0.1:888/)"
# 8000 在 Windows 上被系统服务占着（svchost），docker 的 8000:8000 实际没绑上，
# 所以后端只能通过 :888 访问。这不是故障，别再去 8000 上找后端。
printf '  http://127.0.0.1:8000/ (直连后端)   -> %s  <- 预期连不上，8000 被 Windows 占用\n' "$(code http://127.0.0.1:8000/api/v1/health)"

echo
echo "本机原生 PostgreSQL 18（不是生产！平时应该是 down）"
hr
if command -v pg_lsclusters >/dev/null 2>&1; then
  pg_lsclusters | sed 's/^/  /'
  if pg_lsclusters | grep -q online; then
    echo "  !! 集群在跑。它只该在跑集成测试时起来（ai_pim_test）。"
    DBS="$(su postgres -c 'psql -lqt' 2>/dev/null | cut -d'|' -f1 | tr -d ' ' | grep -v '^$' | tr '\n' ' ')"
    echo "  现有库: $DBS"
    case " $DBS " in
      *" ai_pim "*)
        echo "  !!!! 严重：本机又出现了 ai_pim。它和生产库同名但是空的，任何后端指到"
        echo "       localhost:5432/ai_pim 都会看到一套假数据。删掉它：su postgres -c 'dropdb ai_pim'"
        ;;
    esac
  fi
else
  echo "  没装（那就不会踩这个坑）"
fi

echo
echo "本机进程（开发用的，别把它们当生产）"
hr
FOUND=0
for pid in $(pgrep -f 'uvicorn app.main:app' 2>/dev/null); do
  FOUND=1
  DBURL="$(tr '\0' '\n' < "/proc/$pid/environ" 2>/dev/null | sed -n 's/^DATABASE_URL=//p' | head -1)"
  CMD="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)"
  echo "  uvicorn pid=$pid: $CMD"
  case "$DBURL" in
    *@localhost:5432/*|*@127.0.0.1:5432/*)
      echo "    !!!! 这个后端连的是本机 5432（原生 PG18），不是生产库。就是这个坑。"
      ;;
    '') echo "    DATABASE_URL 没在环境里（大概读的是 backend/.env）" ;;
    *)  echo "    DATABASE_URL=$(printf %s "$DBURL" | sed -E 's#//([^:]+):[^@]*@#//\1:***@#')" ;;
  esac
done
for pid in $(pgrep -f 'pim-demo-server.mjs' 2>/dev/null); do
  FOUND=1
  ENV_PORT="$(tr '\0' '\n' < "/proc/$pid/environ" 2>/dev/null | sed -n 's/^PIM_DEMO_PORT=//p' | head -1)"
  ENV_BE="$(tr '\0' '\n' < "/proc/$pid/environ" 2>/dev/null | sed -n 's/^PIM_DEMO_BACKEND=//p' | head -1)"
  echo "  demo server pid=$pid: 端口 ${ENV_PORT:-5173} -> 后端 ${ENV_BE:-http://127.0.0.1:8000}"
  case "${ENV_BE:-}" in
    *:888*) echo "    OK：转给生产 nginx。" ;;
    *)      echo "    注意：没有转给 :888，确认这是你要的开发后端。" ;;
  esac
done
for pid in $(pgrep -f 'vite' 2>/dev/null); do
  FOUND=1
  echo "  vite dev server pid=$pid（开发热更新，不是生产产物）"
done
[ "$FOUND" -eq 0 ] && echo "  没有本机开发进程。"

echo
echo "前端产物"
hr
for d in frontend/dist portal/dist; do
  if [ -d "$d" ]; then
    echo "  $d: $(date -r "$d/index.html" '+%Y-%m-%d %H:%M' 2>/dev/null) ($(du -sh "$d" 2>/dev/null | cut -f1))"
  else
    echo "  $d: 不存在（先 bash scripts/build_frontends.sh）"
  fi
done
echo "  提醒：nginx 镜像是把 dist COPY 进去的，只在宿主机 build 不会改变 :888 上的东西，"
echo "        必须 docker compose build nginx && docker compose up -d --no-deps nginx。"
