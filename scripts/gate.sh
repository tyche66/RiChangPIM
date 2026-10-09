#!/usr/bin/env bash
# AI-PIM 阶段门禁（10月新需求集，设计文档 §3.3）—— 每阶段结束必跑。
# 用法: scripts/gate.sh [backend|frontend|all]
# 后端优先使用临时测试 venv（README-OPS §12 配方），可用 PY=... 覆盖。
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1

# node（nvm 安装）
for d in "$HOME"/.nvm/versions/node/*/bin; do [ -d "$d" ] && PATH="$d:$PATH"; done
export PATH

PY="${PY:-}"
if [ -z "$PY" ]; then
  for cand in /tmp/pimtestenv/bin/python "$ROOT/backend/venv/bin/python"; do
    if [ -x "$cand" ] && "$cand" -m pytest --version >/dev/null 2>&1; then PY="$cand"; break; fi
  done
fi
[ -n "$PY" ] || { echo "FATAL: 找不到带 pytest 的 python（参考 README-OPS §12 建 /tmp/pimtestenv）"; exit 1; }

fail=0
run() { local name="$1"; shift; echo "── $name"; "$@"; local rc=$?; if [ $rc -ne 0 ]; then echo "✗ FAIL($rc): $name"; fail=1; else echo "✓ $name"; fi; }

if [ "${1:-all}" != frontend ]; then
  (cd backend && run "backend ruff" "$PY" -m ruff check app)
  (cd backend && run "backend unit" "$PY" -m pytest tests/unit -q -p no:cacheprovider)
  if [ -n "${TEST_DATABASE_URL:-}" ]; then
    (cd backend && run "backend contract/integration" "$PY" -m pytest tests -q --ignore=tests/unit -p no:cacheprovider)
  else
    echo "── backend contract/integration: SKIP (未设置 TEST_DATABASE_URL)"
  fi
fi
if [ "${1:-all}" != backend ]; then
  (cd frontend && run "vue-tsc" node_modules/.bin/vue-tsc --noEmit)
  (cd frontend && run "vitest" node_modules/.bin/vitest run)
  (cd frontend && run "eslint" node_modules/.bin/eslint .)
  (cd frontend && run "vite build" node_modules/.bin/vite build)
fi
exit $fail
