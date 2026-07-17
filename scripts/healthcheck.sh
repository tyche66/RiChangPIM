#!/usr/bin/env bash
set -euo pipefail
# AI-PIM 后端健康检查：探测 /api/v1/health。
# 供 Docker HEALTHCHECK 或外部探针调用；非 200 即失败（退出码 1）。
PORT="${PORT:-8000}"
URL="${HEALTH_URL:-http://localhost:${PORT}/api/v1/health}"

if curl -fsS "$URL" >/dev/null 2>&1; then
  echo "OK: $URL"
  exit 0
else
  echo "FAIL: $URL" >&2
  exit 1
fi
