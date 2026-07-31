#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${PIM_DEMO_PORT:-5173}"
HOST="${PIM_DEMO_HOST:-0.0.0.0}"
# pid/log 按端口分开：允许同时跑「指向生产后端」和「指向本地开发后端」两个实例，
# 也让 stop_demo.sh 能只停指定那一个，不会顺手把别人的实例带走。
PID_FILE="/tmp/ai-pim-demo-server-${PORT}.pid"
LOG_FILE="/tmp/ai-pim-demo-server-${PORT}.log"
# 兼容旧版本留下的、不带端口的 pid 文件（默认端口才认）。
if [ "$PORT" = "5173" ] && [ ! -f "$PID_FILE" ] && [ -f /tmp/ai-pim-demo-server.pid ]; then
  PID_FILE="/tmp/ai-pim-demo-server.pid"
  LOG_FILE="/tmp/ai-pim-demo-server.log"
fi
BACKEND_URL="${PIM_DEMO_BACKEND:-http://127.0.0.1:8000}"
HEALTH_URL="http://127.0.0.1:${PORT}/__demo/health"

cd "$ROOT"

# 发行版里 export 了 http_proxy/HTTPS_PROXY=http://127.0.0.1:7890，不加 --noproxy
# 的话连 127.0.0.1 都会被送去代理，健康检查会拿到代理的 502/空回复，明明起来了也
# 报「failed to start」。所有本机 curl 都必须带 --noproxy '*'。
curl_local() { curl -fsS --noproxy '*' "$@"; }

if [ ! -d "$ROOT/frontend/dist" ] || [ ! -d "$ROOT/portal/dist" ]; then
  echo "ERROR: frontend/dist or portal/dist not found. Build both frontends first." >&2
  exit 1
fi

if curl_local "${BACKEND_URL%/}/api/v1/health" >/dev/null 2>&1; then
  echo "==> backend OK: ${BACKEND_URL%/}/api/v1/health"
else
  echo "WARN: backend health check failed: ${BACKEND_URL%/}/api/v1/health" >&2
fi

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" >/dev/null 2>&1; then
  if curl_local "$HEALTH_URL" >/dev/null 2>&1; then
    echo "==> demo server already running (pid $(cat "$PID_FILE"))"
  else
    echo "==> stale demo server detected, restarting"
    kill "$(cat "$PID_FILE")" >/dev/null 2>&1 || true
    rm -f "$PID_FILE"
  fi
fi

if [ ! -f "$PID_FILE" ]; then
  if ss -ltn "sport = :$PORT" | grep -q LISTEN; then
    echo "ERROR: port ${PORT} is already in use by a non-demo process. Free the port or set PIM_DEMO_PORT." >&2
    exit 1
  fi

  echo "==> starting demo server on http://${HOST}:${PORT}"
  # 必须用 setsid 而不是 nohup：从 Windows 侧 wsl.exe -- sh -c 调进来时，interop 的
  # sh 会话一结束就把整个进程组带走，nohup 的子进程照样死，脚本随后报「failed to
  # start」而日志里明明写着 listening。setsid 让 node 进到自己的会话里活下来。
  setsid env \
    PIM_DEMO_PORTAL_ROOT="$ROOT/portal/dist" \
    PIM_DEMO_ADMIN_ROOT="$ROOT/frontend/dist" \
    PIM_DEMO_PORT="$PORT" \
    PIM_DEMO_HOST="$HOST" \
    PIM_DEMO_BACKEND="$BACKEND_URL" \
    node "$ROOT/scripts/pim-demo-server.mjs" \
    > "$LOG_FILE" 2>&1 < /dev/null &
  sleep 1
  # setsid 会 fork，$! 未必是 node 自己，按命令行找真正的 pid（只取一个，别把
  # pgrep 自己所在的 shell 也写进去）。
  pgrep -f "pim-demo-server.mjs" | head -1 > "$PID_FILE"
fi

sleep 1

if curl_local "$HEALTH_URL" >/dev/null 2>&1 && curl_local "http://127.0.0.1:${PORT}/chat" >/dev/null 2>&1; then
  echo "==> demo server is ready: http://127.0.0.1:${PORT}/"
  echo "==> AI Portal entry: http://127.0.0.1:${PORT}/"
  echo "==> AI chat page:    http://127.0.0.1:${PORT}/chat"
  echo "==> admin entry:     http://127.0.0.1:${PORT}/admin/"
  echo "==> backend target:  ${BACKEND_URL}"
else
  echo "ERROR: demo server failed to start. See ${LOG_FILE}" >&2
  exit 1
fi

echo "==> expected Windows mapping: 3001 -> 198.18.0.1:${PORT}"
echo "==> optional direct AI mapping: 888 -> 198.18.0.1:888"
