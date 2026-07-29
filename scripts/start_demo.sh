#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="/tmp/ai-pim-demo-server.pid"
LOG_FILE="/tmp/ai-pim-demo-server.log"
PORT="${PIM_DEMO_PORT:-5173}"
HOST="${PIM_DEMO_HOST:-0.0.0.0}"
BACKEND_URL="${PIM_DEMO_BACKEND:-http://127.0.0.1:8000}"
HEALTH_URL="http://127.0.0.1:${PORT}/__demo/health"

cd "$ROOT"

if [ ! -d "$ROOT/frontend/dist" ] || [ ! -d "$ROOT/portal/dist" ]; then
  echo "ERROR: frontend/dist or portal/dist not found. Build both frontends first." >&2
  exit 1
fi

if curl -fsS "${BACKEND_URL%/}/api/v1/health" >/dev/null 2>&1; then
  echo "==> backend OK: ${BACKEND_URL%/}/api/v1/health"
else
  echo "WARN: backend health check failed: ${BACKEND_URL%/}/api/v1/health" >&2
fi

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" >/dev/null 2>&1; then
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
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
  nohup env \
    PIM_DEMO_PORTAL_ROOT="$ROOT/portal/dist" \
    PIM_DEMO_ADMIN_ROOT="$ROOT/frontend/dist" \
    PIM_DEMO_PORT="$PORT" \
    PIM_DEMO_HOST="$HOST" \
    PIM_DEMO_BACKEND="$BACKEND_URL" \
    node "$ROOT/scripts/pim-demo-server.mjs" \
    > "$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
fi

sleep 1

if curl -fsS "$HEALTH_URL" >/dev/null 2>&1 && curl -fsS "http://127.0.0.1:${PORT}/chat" >/dev/null 2>&1; then
  echo "==> demo server is ready: http://127.0.0.1:${PORT}/"
  echo "==> AI Portal entry: http://127.0.0.1:${PORT}/"
  echo "==> AI chat page:    http://127.0.0.1:${PORT}/chat"
else
  echo "ERROR: demo server failed to start. See ${LOG_FILE}" >&2
  exit 1
fi

echo "==> expected Windows mapping: 3001 -> 198.18.0.1:${PORT}"
echo "==> optional direct AI mapping: 888 -> 198.18.0.1:888"
