#!/bin/bash
export PATH="/root/.nvm/versions/node/v24.18.0/bin:$PATH"
cd /home/AI-PIM/RiChangPIM/frontend || exit 9
echo "== eslint =="
./node_modules/.bin/eslint . 2>&1 | tail -3
echo "eslint_exit=$?"
echo "== vitest =="
./node_modules/.bin/vitest run 2>&1 | tail -4
echo "vitest_exit=$?"
