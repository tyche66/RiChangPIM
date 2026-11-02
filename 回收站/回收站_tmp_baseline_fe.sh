#!/bin/bash
# 临时基线脚本（跑完即弃，移到回收站）
export PATH="$HOME/.nvm/versions/node/v24.18.0/bin:$PATH"
cd /home/AI-PIM/RiChangPIM/frontend || exit 9
LOG=/tmp/fe-baseline.log
: > "$LOG"

echo "### vue-tsc --noEmit" | tee -a "$LOG"
./node_modules/.bin/vue-tsc --noEmit >> "$LOG" 2>&1
echo "vue-tsc exit=$?" | tee -a "$LOG"

echo "### vitest run" | tee -a "$LOG"
./node_modules/.bin/vitest run >> "$LOG" 2>&1
echo "vitest exit=$?" | tee -a "$LOG"

echo "### eslint ." | tee -a "$LOG"
./node_modules/.bin/eslint . >> "$LOG" 2>&1
echo "eslint exit=$?" | tee -a "$LOG"

echo "=== SUMMARY ==="
grep -E "^(vue-tsc|vitest|eslint) exit=" "$LOG"
