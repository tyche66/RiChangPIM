#!/usr/bin/env bash
# 构建两个前端（frontend=后台、portal=门户），并注入真实的版本元数据。
#
# 为什么要有这个脚本，而不是各自 npm run build：
#
# 1. 版本页要显示真话。frontend/src/config/version.ts 读的是构建期注入的
#    VITE_APP_VERSION / VITE_BUILD_ID / VITE_GIT_COMMIT / VITE_BUILD_TIME，
#    直接 npm run build 会全部退化成 package.json 版本 + dev-local + unknown，
#    版本页就只能显示「—」，和后端 /api/v1/version 也对不上。
#
# 2. 后台必须按 base '/admin/' 构建。frontend/vite.config.ts 里
#    base = process.env.VITE_BASE_PATH || '/'，直接 npm run build 出来的
#    index.html 引用的是 <script src="/assets/index-xxxx.js">（绝对根路径），
#    而这个请求在生产 nginx 上会打到 docker/nginx/conf.d/default.conf 的
#        location / { root /usr/share/nginx/portal; }
#    去门户目录里找 —— 后台 dist 被 COPY 到 /usr/share/nginx/admin，那里没有
#    → 后台 JS/CSS 全 404，页面白屏（实测 2026-07-31：
#    GET :888/assets/index-CY12cIKj.js → 404，而该文件确实存在于容器的
#    /usr/share/nginx/admin/assets/）。
#    注意：这个锅不是 nginx 的 location 匹配优先级（conf 里没有正则 location，
#    2026-07-31 已核对 default.conf 全文与容器内 /etc/nginx/nginx.conf 确认）。
#
#    所以下面 export VITE_BASE_PATH=/admin/ 是硬要求，不是可选优化。
#    历史包袱已清：公开分享页 /share/:token 现在由门户承载
#    （portal/src/views/SharePage.vue），此前那段「把后台静态资源复制一份到
#    portal/dist」的 merge_admin_static 补丁已随之删除，别再加回来。
#    改这里的同时记得同步 README-OPS.md 的「已知缺口」。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v node >/dev/null 2>&1; then
  echo "ERROR: node 不在 PATH 里。先 export PATH=\"\$HOME/.nvm/versions/node/v24.18.0/bin:\$PATH\"" >&2
  exit 1
fi

# 版本锚点是 frontend/package.json（见 版本控制规范和Git.md §1.1），这里只读它，
# 不去改它——发版时手改那 7 处的清单在 CHANGELOG.md 顶部。
APP_VERSION="${APP_VERSION:-$(node -p "require('./frontend/package.json').version")}"
BUILD_ID="${BUILD_ID:-local-$(date -u +%Y%m%dT%H%M%SZ)}"
BUILD_TIME="${BUILD_TIME:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
if [ -z "${GIT_COMMIT:-}" ]; then
  GIT_COMMIT="$(git rev-parse --short HEAD)"
  # 工作区有未提交改动时必须标 -dirty：版本页显示的 commit 要能对上真实产物。
  if [ -n "$(git status --porcelain)" ]; then
    GIT_COMMIT="${GIT_COMMIT}-dirty"
  fi
fi

export VITE_APP_VERSION="$APP_VERSION"
export VITE_BUILD_ID="$BUILD_ID"
export VITE_GIT_COMMIT="$GIT_COMMIT"
export VITE_BUILD_TIME="$BUILD_TIME"
export VITE_BASE_PATH=/admin/

echo "==> APP_VERSION=$APP_VERSION BUILD_ID=$BUILD_ID GIT_COMMIT=$GIT_COMMIT BUILD_TIME=$BUILD_TIME"

echo "==> building frontend (admin)"
(cd frontend && npm run build)

echo "==> building portal"
(cd portal && npm run build)

echo "==> done"
echo "    frontend/dist: $(du -sh frontend/dist | cut -f1)"
echo "    portal/dist:   $(du -sh portal/dist | cut -f1)"

