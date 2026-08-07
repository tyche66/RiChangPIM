# RiChangPIM 交接文档

> 交接时间：2026-07-31
> 版本基线：`v1.9.1`（产品媒体导入、AI / Knowledge 增强、媒体分页与文档同步；发布详情见 `CHANGELOG.md`）
> 下一棒方向：**管理后台（`frontend/`）界面美化 + 小部分功能调整**
> 本文只服务「快速上手」——项目怎么跑、代码在哪、规矩是什么、当前基线是什么。具体任务由用户直接指派，见 §8。

## 1. 三十秒速览

仓库里有 **三个可独立启动的部分**，别搞混：

| 目录 | 是什么 | 技术栈 | 开发端口 |
| --- | --- | --- | --- |
| `backend/` | 后端 API | FastAPI + SQLAlchemy + Alembic | 8000 |
| `frontend/` | **管理后台（下一棒主战场）** | Vue 3 + Vite + Element Plus + Pinia | 5173 |
| `portal/` | AI 门户（上一棒刚改完，不用再动） | Vue 3 + Vite，无 UI 库，手写 CSS | 5174 |

生产编排里 Nginx（宿主 `888` → 容器 `80`）把 `/` 与 `/share/{token}` 指向 portal 构建产物、`/admin/` 指向 frontend 构建产物、`/api/` 反代后端。所以「后台」在浏览器里的路径是 `/admin/`，不是根路径。

> `:888/admin/` 自 2026-07-31 起可用（后台按 `VITE_BASE_PATH=/admin/` 构建 + `default.conf` 的
> `location = /admin` 301 与 `absolute_redirect off`，硬刷新也没问题）。
> 演示服务器 `http://127.0.0.1:5173/admin/` 仍然并存，公网隧道走的是它（不经过 nginx）。
> 对客户的分享页现在由门户承载（`portal/src/views/SharePage.vue`）；后台包里那条 `/share/:token`
> 路由和 `frontend/tests/e2e/sharing.spec.ts` 是待清理的残留，线上到不了。

## 2. 环境与启动

代码在 WSL 发行版 `RiChangPIM` 里：`/home/AI-PIM/RiChangPIM`。Node 由 nvm 安装，不在默认 PATH：

```bash
export PATH="$HOME/.nvm/versions/node/v24.18.0/bin:$PATH"
```

从 Windows 侧调 WSL 的命令模板（`tr -d '\0'` 用来去掉 interop 输出里的空字节，否则日志会带乱码）：

```bash
MSYS2_ARG_CONV_EXCL='*' MSYS_NO_PATHCONV=1 wsl.exe -d RiChangPIM -- sh -c 'cd /home/AI-PIM/RiChangPIM/frontend && npm run dev' | tr -d '\0'
```

本地开发四步（详见 `README.md` 的「快速开始」）：

```bash
docker compose -f docker-compose.dev.yml up -d
```

依赖服务：PostgreSQL 16 + pgvector、Redis 7、MinIO、Gotenberg 8、OCR。后端 `uvicorn app.main:app --reload --port 8000`，后台 `cd frontend && npm run dev`（`5173`，`/api` 由 Vite 代理到 `8000`，可用 `VITE_API_PROXY_TARGET` 覆盖）。

后台入口页是 `src/views/Login.vue`，登录后默认落到 `/products`。种子账号见 `backend/app/scripts/seed_data.py` 与 `backend/alembic/versions/0004_seed_data.py`，**不要把口令写进文档或代码**。

## 3. 管理后台代码地图（下一棒主战场）

`frontend/src` 共 23 个页面、约 17.6k 行模板/脚本。改视觉按这个顺序看：

| 文件 | 行数 | 作用 |
| --- | --- | --- |
| `src/styles/design-system.css` | 273 | **全局设计令牌 + Element Plus 变量覆盖**，改整体观感先动这里 |
| `src/layouts/MainLayout.vue` | 521 | 后台外壳：深蓝圆角侧栏 + 玻璃质感顶栏 + 路由过渡 |
| `src/router.ts` | 220 | 全部路由 + 登录/权限守卫 |
| `src/api/index.ts` | 412 | 后端接口封装（另有 `src/api/media.ts`） |
| `src/stores/auth.ts` | — | 登录态、`currentUser`、`userRoleCode`、`permissions` |
| `src/views/*.vue` | 17579 | 页面，最大三个：`Products.vue` 2139、`SceneImages.vue` 1836、`MediaLibrary.vue` 1528 |
| `src/components/*.vue` | 2798 | 7 个业务组件，集中在媒体与方案（`MediaPicker`/`MediaUploader`/`ProductImageManager`/`ProductSceneCarousel`/`ProposalItemEditor`/`SceneImageSelector`/`ShareResultDialog`） |

设计令牌（`design-system.css` `:root`）：品牌色 `--pim-brand: 30, 50, 90`（深蓝，全部颜色都由它派生 rgba）、画布 `#f0f0f0`、玻璃面 `rgba(255,255,255,.68)`、圆角 `28 / 18 / 14px`、阴影 `0 20px 60px rgba(brand,.09)`；同时把 `--el-color-primary`、`--el-border-radius-base`、`--el-table-*` 等 Element Plus 变量一并覆盖成同一套值。

视觉风格是**玻璃拟态**：`.el-card`、`.el-dialog` 都是半透明 + `backdrop-filter: blur()`，`body` 铺了两层 `radial-gradient` 光斑。按钮体系被统一改成「描边 → hover 填充」，且 `success/warning/danger/info` 全部被压成同一个主色；`.capsule-btn` 系列还用了 `!important`。**动按钮样式时这三块要一起看**，否则会出现改了一处、另一处 `!important` 盖回去。

几个容易踩的点：

- `src/store/` 是**空目录**，真正的 store 在 `src/stores/`。
- `MainLayout.vue` 里导航相关的映射有 **三处**要同步：`el-menu` 的 `index`、`subMenuMap`（决定默认展开哪个子菜单）、`routeLabels`（决定顶栏 `WORKSPACE / 区块` 和标题）。加/改页面漏一处就会出现菜单不高亮或标题错。
- 侧栏是 `el-menu`，改样式要用 `:deep()`（`MainLayout.vue` 的 `<style scoped>` 已经这么写）。
- 后台响应式断点是 `1023px`（侧栏变抽屉）和 `600px`（顶栏收缩）；门户用的是 `1024/640`，**两套不通用**。
- 权限守卫在 `router.ts`：`meta.permissions` + `meta.permissionsMode`（`any` 默认 / `all`），`role_code === 'admin'` 直通；无权限时先尝试 `authStore.refresh()` 再判定，仍不通过就回落到 `Products`。加页面记得配 `meta.permissions`，否则任何人都能进。

## 4. 设计规范与两套视觉语言

- `AI-Docs/Furnispace-PLP-Design-Skill.md`（492 行）是前端设计规范：§5 视觉 token、§6 组件规范、§7 交互与动效、§8 响应式、§11 Do/Don't、§12 验收清单。门户改版就是按它 + reeoo 参考做的，后台美化同样以它为基准。
- **后台和门户是两套视觉语言，不要互相拷贝**：后台 = Element Plus + 深蓝玻璃拟态 + 强圆角；门户 = 黑白扁平、`--surface`/`--border` 那套手写 token、无 UI 库。跨端复制样式只会两边都别扭。
- 三条硬性规则跨端通用：
  1. **不编造数据**。缺价格显示「待核价」，缺库存显示「库存待确认」，取不到就退化成占位，不要拿假数据填充（后端枚举翻译见 `portal/src/utils/format.ts` 的做法）。
  2. 动效必须有 `@media (prefers-reduced-motion: reduce)` 降级，`design-system.css` 末尾已有全局兜底，新加的动画仍要自查。
  3. 权限不足时前端只做「不展示 / 不请求」，不做假成功。

## 5. 质量门禁与当前基线

`RELEASE_GATE.md` 是完整发布门禁（后端 ruff/pytest、前端 vue-tsc/eslint/vitest/build、compose 校验、迁移、依赖审计、浏览器门禁）。下面是 2026-07-30 实测的基线，**动手前先跑一遍，确认不是你改坏的**：

| 命令 | 结果（2026-07-30） |
| --- | --- |
| `cd frontend && npx vue-tsc --noEmit` | 通过，退出 0 |
| `cd frontend && npx vitest run` | **19 个文件 / 148 条全绿** |
| `cd frontend && npx eslint . --max-warnings=0` | **10 errors（既有欠债）** |
| `cd portal && npm run build` | 通过（`vue-tsc --noEmit` + vite build） |
| `cd portal && npx playwright test` | **6/6 通过** |

那 10 个 eslint 错误全部在测试文件里，`src/` 是干净的：`tests/components/ShareResultDialog.spec.ts` 7 个、`ProposalDetail.spec.ts` 2 个、`ProductDetail.spec.ts` 1 个，规则是 `@typescript-eslint/no-unused-vars` 和 `no-var-requires`。这是接手前就存在的状态，顺手修可以，但别和界面改动混在一个提交里。

2026-07-31 验收退回返工后的复测（同样的命令，数字变了是因为这轮加了用例）：

| 命令 | 结果（2026-07-31） |
| --- | --- |
| `cd frontend && npx vue-tsc --noEmit` | 通过，退出 0 |
| `cd frontend && npx vitest run` | **22 个文件 / 167 条全绿** |
| `cd frontend && npx playwright test` | **74 通过 / 2 跳过**（跳过的是 env 门控的 `manuals-real.spec.ts`） |
| `cd portal && npx playwright test` | **16/16 通过** |
| `backend`：`/tmp/pimtestenv/bin/python -m pytest tests/unit -q` | **90 通过**（宿主上首次真跑起来，配方见 `README-OPS.md` 排障 §12） |

> `vue-tsc` 只覆盖 `src/**`（`frontend/tsconfig.json` 的 `include`），**新写的 spec 不会被它类型检查**。
> 加了测试文件时别把「vue-tsc 通过」当成 spec 没问题。
> `backend/tests/integration` 在这台机器上仍然跑不了（生产库没发布 5432、本机 PG18 的 `pim` 不是 superuser、建不了 `vector` 扩展）。

测试布局：

- 后台单测/组件测：`frontend/tests/unit`（8 个 spec）+ `frontend/tests/components`（14 个 spec），`vitest` + jsdom，只收这两个目录。
- 后台 E2E：`frontend/tests/e2e` 10 个 spec（`auth`/`ai-features`/`audit`/`gap-analysis`/`manuals-real`/`product-grid-detail`/`product-proposal`/`proposals`/`sales-flow`/`sharing`），Playwright `baseURL http://localhost:5173`（被占用时用 `E2E_PORT` 换端口），项目 `chromium` + `Mobile Chrome`(Pixel 5)，`fullyParallel: false`，会自动起 `npm run dev`。登录态用 `tests/e2e/helpers.ts` 里的 mock JWT（`ADMIN_TOKEN` / `USER_TOKEN`），不依赖真后端签发。
  - `product-grid-detail.spec.ts` 是 2026-07-31 那条「卡片视图点卡片白屏」的回归钩子，同时钉住列表封面只能请求 `w=192`/`w=480`。
  - `product-proposal.spec.ts` 有个已知抽风（表格重排竞态，约 3 次跑 1 次失败），先重跑再怀疑自己的改动。
- 门户 E2E：`portal/tests/e2e/`（`portal.spec.ts` + `chat-contract.spec.ts`），`baseURL http://127.0.0.1:5174`，项目 `desktop` + `mobile`，8 条 × 2 = 16 条。
- 后端单元测：`backend/tests/unit`（21 个模块）。这一层有硬约定（`backend/tests/unit/conftest.py`）：只许 import 不牵连 `app.main` / `app.core.database` 的叶子模块；撞上了就去改应用的 import 链，不许把整个 app 拖进单元层。`app/services/thumbnails.py` 就是为此从 `app/api/v1/files.py` 抽出来的。

## 6. 不能碰的红线

1. **`portal/tests/e2e/portal.spec.ts` 是钩子，不许改测试去迁就代码。** 它锁了三件事：`.card-list` 第一个是产品区、第二个是来源区（顺序不能变）；输入框占位文字必须是 `输入产品搜索、问资料、查质量或做比较`；页面上只能有一处 `打开` 按钮。改门户任何结构前先看它。
2. **版本号锚点是 `frontend/package.json` 的 `version`**（`版本控制规范和Git.md` §1）。每个正式版本必须有 annotated tag（`git tag -a vX.Y.Z -m "..."`）。构建时 `APP_VERSION` / `VITE_APP_VERSION` 注入同一版本；没注入时 `src/config/version.ts` 会回落到 `package.json` 的值，后台「版本」页 `src/views/Version.vue` 展示的就是它，并和后端 `build_id` / `git_commit` 比对是否同版。
3. **提交规范**：Conventional Commits（`feat:` / `fix:` / `docs:` / `refactor:` …），一个提交一个目的；不提交 `.env`、令牌、构建产物、依赖目录；不用 `--no-verify`；不对共享分支 force push。
4. **分支**：规范要求功能走 `feature/<主题>` 再 PR 合并 `main`，但 `v1.8.0`–`v1.8.5` 实际都是直接在 `main` 上发布的。沿用哪种由用户定，别自己改约定。
5. `.gitignore` 已忽略 `.opencode/`（另一个 AI 工具目录，含 `node_modules`）和 `MANIFEST.txt`（自动生成的 3.5 万行文件清单），两者都不要提交。

## 7. 上一棒交付了什么（`v1.8.5`，知道边界就行）

门户首屏按 reeoo.com 复刻：巨号标题 + 胶囊输入框 + 扇形叠放产品卡堆 + 四格能力入口，回答/待确认动作/比较表/来源/技术详情全部下移、滚动逐段淡入。卡堆默认放推荐产品，AI 返回产品后整堆替换；没有 `product:view` 权限时退化成空白占位卡。

涉及文件（**这次不需要再动**）：`portal/src/views/Conversation.vue`、`portal/src/components/{HeroDeck,CapabilityBar,ChatInput}.vue`、`portal/src/utils/reveal.ts`、`portal/src/styles/main.css`、`portal/src/api/index.ts`。

`README.md` 概览表里的「当前版本」和「当前迁移 head」曾停在 `v1.8.0` / `0014_knowledge_tables`，已随本轮 T12 更新为 `v1.8.5` / `0017_operation_log_username`；版本号到底要改哪几处，现在写在 `CHANGELOG.md` 顶部和 `版本控制规范和Git.md` §1.1。

## 8. 你的任务指派

用户已明确的方向：**后台（`frontend/`）界面美化 + 小部分功能调整**。具体范围、视觉方向和功能清单由用户当面指派，本文不代为决定。

接手后建议的前三步：

1. 跑基线：`npx vue-tsc --noEmit`、`npx vitest run`、`npm run dev` 起后台，确认现状可运行（eslint 那 10 个既有错误是预期的）。
2. 逐页看现状：登录 → 产品列表 → 产品详情 → 方案/报价 → 系统管理 → AI 功能，记下视觉问题清单，桌面和 `≤600px` 各看一遍。
3. 和用户确认改动范围与优先级，再动 `design-system.css` / `MainLayout.vue`；全局令牌一改会影响 23 个页面，先小范围验证再铺开。

改完的验收口径沿用上一棒：`npx vue-tsc --noEmit` + `npx vitest run` + `npm run build` 必须全绿，涉及交互改动时补跑 `frontend/tests/e2e` 对应 spec；截图桌面 + 移动两个视口自查后再交付。

## 9. 其他常用位置

- 项目文档：`docs/00-项目概述.md` ~ `09-测试计划.md`，AI 相关设计在 `AI-Docs/01`~`08`（`04-门户交互与API契约.md` 是门户与后端的契约）。
- 进度与欠债：`TODO.md`、`PROJECT_MANAGEMENT.md`、`BUILD_LOG.md`（只在大版本更新）。
- 运维：`README-OPS.md`、`scripts/`（备份、恢复、健康检查、发布门禁、演示服务器 `start_demo.sh`/`stop_demo.sh`）。
- Nginx 路由：`docker/nginx/conf.d/`；迁移 head 为 `0017_operation_log_username`（0014 之后又加了 `0015_pending_actions`、`0016_embedding_dim_2048`、`0017_operation_log_username`）。

## 10. 部署现状（2026-07-31 实测）

1. **每次开工第一条命令**：`cd /home/AI-PIM/RiChangPIM && bash scripts/where-am-i.sh`。
   它打出后端连的是哪个库、alembic 版本、生产库数据规模、各入口状态、本机进程各自指向哪个后端。
   起因是 2026-07-31 出过一次事故：本机原生 PostgreSQL 18 里有一个**同名的空 `ai_pim` 库**，
   一个开发后端指到 `localhost:5432/ai_pim`，页面完全正常但只有 1 个用户 0 个商品，
   于是所有真实口令都被判为「错」。空库已 dump 后删除，脚本会对它再次出现报警。
   生产库正常应该是「用户 7 / 商品 15」量级。

2. **端口固定这一套，不要换**（换了 Windows portproxy 和 Funnel 都得跟着改）：

   | 用途 | 地址 |
   | --- | --- |
   | 门户 / 分享页 / API（生产 nginx `888:80`） | `http://127.0.0.1:888/` |
   | 管理后台（生产 nginx） | `http://127.0.0.1:888/admin/` |
   | 管理后台（演示服务器） | `http://127.0.0.1:5173/admin/` |
   | AI 对话页 | `http://127.0.0.1:5173/chat` |
   | 公网 | Funnel → Windows `3001` → portproxy → WSL `5173`（**不经过 nginx**） |
   | 后端直连 `:8000` | **不可用**，Windows 系统进程占着 |

   后台入口这样起（`PIM_DEMO_BACKEND` 必须是 `:888`，默认的 `:8000` 会导致**登录一直转圈不返回**）：

   ```bash
   PIM_DEMO_PORT=5173 PIM_DEMO_BACKEND=http://127.0.0.1:888 bash scripts/start_demo.sh
   curl -s --noproxy '*' http://127.0.0.1:5173/__demo/health   # backendTarget 必须是 :888
   ```

3. **前端上生产要两步**：`bash scripts/build_frontends.sh`（不要用裸 `npm run build`：它还负责版本注入
   和 `export VITE_BASE_PATH=/admin/`），然后 `docker compose build nginx && docker compose up -d --no-deps nginx`
   ——`frontend/dist` / `portal/dist` 是 `COPY` 进 nginx 镜像的，不是 bind mount。
   后端同理：`docker compose build backend && docker compose up -d --no-deps backend`。
   **重建/重启 backend 前先 export `APP_VERSION` / `BUILD_ID` / `GIT_COMMIT` / `BUILD_TIME`**
   （值抄 `build_frontends.sh` 的输出，`BUILD_ID` 必须和前端产物里的一致）：compose 这四项默认
   `dev` / `dev-local` / `unknown`，漏了后端会自报 `dev`，后台「版本」页按 `build_id` 判成
   「前后端版本不一致」。命令见 `README-OPS.md`「升级发布 runbook」第 3 步。
   演示服务器相反，它直接读宿主机 dist，build 完刷新浏览器就生效；但改了
   `scripts/pim-demo-server.mjs` 本身必须重启那个进程（node 已把脚本读进内存）。

4. **`:888/admin/` 与 `/share/` 已修好（2026-07-31 返工）**，别把下面任何一条改回去：
   - 后台按 `VITE_BASE_PATH=/admin/` 构建（`scripts/build_frontends.sh`），产物引用 `/admin/assets/...`；
     旧的 `merge_admin_static`（把 admin 资产拷进 `portal/dist`）已删除。
   - `docker/nginx/conf.d/default.conf` 加了 `location = /admin { return 301 /admin/; }`
     和 `absolute_redirect off`（否则 `:888/admin` 会被 301 到不带端口的 `http://localhost/admin/` → 白屏）。
   - `/share/{token}` 由门户承载（`portal/src/views/SharePage.vue`），nginx 不再为它单开 location，
     靠 `location /` 回落到门户 index.html。
   - 前端代码里**不许**再用根绝对路径导航（`window.open('/products/x')`、`location.href='/login'`）：
     后台的 base 是 `/admin/`，这类跳转会绕过 base 落到门户 → 白屏。用 `router.push`，
     必须拼 URL 时从 `import.meta.env.BASE_URL` 派生（`frontend/src/api/index.ts` 里有例子）。
     回归钩子：`frontend/tests/e2e/product-grid-detail.spec.ts`。
   - 残留：后台包里那条 `/share/:token` 路由（`frontend/src/router.ts`）和
     `frontend/tests/e2e/sharing.spec.ts` 还在，线上到不了，属于待清理项。

5. **列表缩略图**：产品列表的封面走 `GET /api/v1/files/{id}/content?w=<短边宽度>`，
   白名单 `96/192/240/480/960`，其它值 422；缓存在 MinIO 的 `derived/thumb/w{width}/{oss_key}.webp`。
   实现在 `backend/app/services/thumbnails.py`（叶子模块，`backend/tests/unit/test_thumbnails.py` 覆盖），
   前端档位在 `frontend/src/views/Products.vue`（`TABLE_THUMB_WIDTH=192` / `TILE_THUMB_WIDTH=480`）。
   动这两处要同时动，否则要么 422 要么性能退回（原来一页 14 张 4000×3000 原图 ≈ 5 MB、上亿像素，
   滚动必掉帧）。细节见 `README-OPS.md` 排障 §11。

6. 完整实机流程见 `/home/AI-PIM/从启动到穿透.md`（在仓库外，上一级目录）和 [README-OPS.md](README-OPS.md)。
   `docs/06-部署方案.md` 是方案文档，与实机有偏差，头部已标注。


