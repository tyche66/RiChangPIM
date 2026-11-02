#!/bin/bash
# G0-3 e2e 基线：chromium + Mobile Chrome，共 3 轮。记录失败用例与耗时。
export PATH="$HOME/.nvm/versions/node/v24.18.0/bin:$PATH"
cd "$(cd "$(dirname "$0")" && pwd)/frontend" || exit 9
export E2E_PORT=5199
LOG=/tmp/e2e-baseline.log
: > "$LOG"
for round in 1 2 3; do
  echo "===== ROUND $round =====" >> "$LOG"
  ./node_modules/.bin/playwright test --project=chromium --project="Mobile Chrome" >> "$LOG" 2>&1
  echo "ROUND_${round}_EXIT=$?" >> "$LOG"
done
grep -E '=====|ROUND_._EXIT=|[0-9]+ (passed|failed|flaky|skipped)' "$LOG" | tail -30
