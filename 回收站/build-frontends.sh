#!/bin/bash
# portal 构建（依赖 ../logo，所以要用带 logo 的完整工作区副本或把 logo 放到 /tmp/logo）
set -uo pipefail
export PATH="/root/.nvm/versions/node/v24.18.0/bin:$PATH"
cd /tmp/po || exit 1
npm run build > /tmp/po-build.log 2>&1
echo "exit=$?"
tail -12 /tmp/po-build.log