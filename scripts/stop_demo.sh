#!/usr/bin/env bash
set -euo pipefail

PID_FILE="/tmp/ai-pim-demo-server.pid"
SCRIPT_PATH="/home/AI-PIM/RiChangPIM/scripts/pim-demo-server.mjs"

stop_pid() {
  local pid="$1"
  if kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid"
    echo "==> stopped demo server (pid $pid)"
    return 0
  fi
  return 1
}

if [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE")"
  if ! stop_pid "$PID"; then
    echo "==> demo server pid file exists but process is gone"
  fi
  rm -f "$PID_FILE"
fi

STALE_PIDS="$(ps -eo pid=,args= | grep "$SCRIPT_PATH" | grep -v grep | awk '{print $1}')"
if [ -n "$STALE_PIDS" ]; then
  for pid in $STALE_PIDS; do
    stop_pid "$pid" || true
  done
elif [ ! -f "$PID_FILE" ]; then
  echo "==> no demo server pid file found"
fi
