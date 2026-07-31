# CHANGELOG

本文件是**「当前版本号」的唯一现值来源**。别的文档要么引用这里，要么写的是历史记录（见下面「不要去改的历史记录」）。
版本号规则（语义化版本、锚点、annotated tag）见 `版本控制规范和Git.md` §1 / §1.1。

## 改版本号要动哪几处

发一个新版本 `vX.Y.Z` 时，**手改这 7 处，一处不能漏**：

| # | 位置 | 说明 |
| --- | --- | --- |
| 1 | `frontend/package.json` → `version` | 规范 §1 指定的版本锚点，先改这里 |
| 2 | `portal/package.json` → `version` | 必须和 1 完全一致（门户和后台同版发布） |
| 3 | `backend/app/core/config.py` → `VERSION` | `APP_VERSION` 没注入时的兜底值，兜底值也必须是真话 |
| 4 | 本文件顶部 | 新增一节 `## vX.Y.Z — YYYY-MM-DD` 并写清变更 |
| 5 | `README.md` 概览表 → 「当前版本」 | 迁移有变时同时更新「当前迁移 head」 |
| 6 | `AI-Docs/README.md` 头部 → 「当前版本」 | |
| 7 | annotated tag | `git tag -a vX.Y.Z -m "..."` + `git push origin vX.Y.Z` |

自动派生，**不要手改**：

- `frontend/src/config/version.ts`：读 `VITE_APP_VERSION`，没注入就回落到 `frontend/package.json`（所以第 1 处是锚点）。
- `/api/v1/version`、`/health`、`/api/v1/observability/*`、FastAPI OpenAPI 的 `version`：全部是 `settings.APP_VERSION or settings.VERSION`。
- `APP_VERSION` / `BUILD_ID` / `GIT_COMMIT` / `BUILD_TIME`：构建期注入（`backend/Dockerfile` 的 ARG→ENV、`docker-compose.yml` 的 build args、CI 的 `build-metadata` job）。
- 后端接口不返回前端版本。以前 `/api/v1/version` 返回过 `frontend_version`，值是抄的 `backend_version`，前后端真不同版时也显示一致，已删除并由 `backend/tests/test_version.py` 锁住不许加回来。

**不要去改的历史记录**（改了就是篡改发布史）：`BUILD_LOG.md` 的构建记录、`PROJECT_MANAGEMENT.md` 的发布台账、`TODO.md` 的「已发布」条目、`docs/08-开发路线图.md` 的里程碑行。`RELEASE_GATE.md` 已改成版本无关，不需要跟着版本走。

## 已知缺口（本轮未修，属部署/CI 配置）

- `docker-compose.yml` 把 `APP_VERSION` 默认成 `dev`。用 compose 起服务且没传 `APP_VERSION` 时，后端报的是 `dev`，压不到第 3 处的兜底值——兜底只在环境变量完全没设时生效。
  重建 backend 前必须按 `README-OPS.md`「升级发布 runbook」第 3 步导出 `APP_VERSION` / `BUILD_ID` /
  `GIT_COMMIT` / `BUILD_TIME`，否则后台「版本」页会判成「前后端版本不一致」（2026-07-31 返工时踩过）。
- `.env.example` 里 `VITE_APP_VERSION=dev` 同理。
- 前端没有独立镜像（无 `frontend/Dockerfile`）：`frontend/dist` 由宿主机构建后 `COPY` 进 nginx 镜像。
  从 2026-07-31 起改用 `scripts/build_frontends.sh` 构建，它会注入真实的 `VITE_APP_VERSION` /
  `BUILD_ID` / `GIT_COMMIT` / `BUILD_TIME`，「版本」页显示的是真话；但**裸 `npm run build` 仍会退化**
  成 `frontend/package.json` 的值 + `dev-local` + `unknown`。

## 未发布

- （暂无）

## v1.9.0 — 2026-07-31

后台（`frontend/`）界面与交互成套改版发布，含 2026-07-30 之后累积的全部后台改造、两轮验收返工、
生产部署与运维脚本。annotated tag `v1.9.0`，沿用 v1.8.x 的做法直接发布在 `main`。
MINOR 位进到 9 而不是发 v1.8.6：本轮换掉的是表格排版体系、状态语言和列宽算法，属成套功能变更，不是补丁。
迁移 head 不变，仍是 `0017_operation_log_username`。

### 后台界面与小功能（本版主体）

- 表格排版体系（列宽 / 字体 / 对齐 / 行高）统一；AI 选品改为嵌入门户 `/chat`；用户习惯持久化；
  顶栏显示当前用户 + 退出确认；操作日志记真实用户名；真实最后登录时间；版本页去掉假数据。

### 产品列表三项验收退回（本版最后一轮）

- **2K 屏表格不满屏宽**。新增 `frontend/src/utils/columnFill.ts`（DOM 无关的水填充列宽算法）+
  `frontend/tests/unit/columnFill.spec.ts` 17 条。Element Plus 两种现成行为都不合用：`:fit="false"` 时
  表格总宽 = Σ 列宽，是个常量，2560 上右侧留白；`fit=true` 把余量**平均**分给只写了 `min-width` 的列，
  宽屏上产品名称照样挤。算法：canvas `measureText` 量各列自然宽 → 按 `grow` 权重分配
  `容器 − Σ自然宽`、逐列在 `max` 处截断 → 锚列（产品名称，`max = ∞`）吸收取整余数，
  保证 **Σ 列宽严格等于容器宽**；容器装不下 Σmin 时停在 Σmin 转横向滚动，不再继续压缩。
  实测 2560×1440：容器 2194、Σ 列宽 2194（80/260/626/220/201/173/177/130/127/200）；1920：1554 = 1554；
  `¥19340.00` 单行右对齐不折行，`独立主管桌` 不截断。表头拖过的列变成固定列，其余列重新填充。
- **去竖分割线**。`el-table` 的 `border` 去掉，横线改用 `td::after` 伪元素画 ——
  `design-system.css` 的斑马纹用的是 `background` 简写，直接把 `background-image` 画的分割线冲掉。
  首列 / 末列的线内缩 14px，最后一行不画线；表头下划线同样内缩，用 `--pim-line-strong`。
- **状态标识改单文字**。`el-tag` 和实色胶囊全部去掉，改 `<span class="status-text tone-*">`：
  只保留降了饱和度的文字色（`#4f6b57` / `#8a6a3c` / `#8f5b57` / `rgba(30,50,90,.7)`），
  无背景、无圆角、无内边距，白底对比度 5–5.9:1。`.product-table` 里 `el-tag` 计数为 0。

### 发布门禁（2026-07-31 实测）

- 通过：`vue-tsc --noEmit`；`vitest run` **23 文件 / 184 通过**；后台 Playwright **74 通过 / 2 跳过**
  （env 门控的 `manuals-real.spec.ts`）；门户 Playwright **16 通过**；`backend/tests/unit` **90 通过**、
  `pytest -q` 全量 **383 通过 / 136 跳过**（需要真库 + pgvector 的集成层在本机自动跳过）；
  `compileall app`；`docker-compose.yml` 与 `docker-compose.dev.yml` 的 `config --quiet`；
  `scripts/secret_scan.sh` **0 命中**；`bash -n` 四个备份脚本。
- 未清的既有基线（本轮一条没新增，涉及文件与 HEAD 逐字一致）：`ruff check app` 60 条（52 条 E501）；
  `eslint . --max-warnings=0` 11 error / 54 warning（10 条在三个 `tests/components/*.spec.ts`，
  1 条是 `MediaPicker.vue` 的 `vue/no-dupe-keys`）。本轮新增的 `backend/app/services/thumbnails.py`
  ruff 干净。

### 过程记录（下面两段发生时还没改版本号，随本版一并发布）

- **2026-07-31 生产部署**
  - 用 `scripts/build_frontends.sh` 重建两个前端产物并重建 backend / nginx 镜像；
    `/api/v1/version` 实测 `1.8.5 / local-20260731T063641Z / dbce35e-dirty / 2026-07-31T06:36:41Z / production`。
  - 生产库迁移 `0016_embedding_dim_2048` → `0017_operation_log_username`（head）；
    迁移前备份 `backups/pre_0017_20260731T142024.sqlc`。验收：用户 7 / 商品 15，四个入口全 200。
  - 事故与善后：本机原生 PostgreSQL 18 上存在一个**同名的空 `ai_pim` 库**，一个开发后端指到
    `localhost:5432/ai_pim`，导致「所有真实口令都错」。该空库已 dump 后删除
    （`backups/native_pg18_ai_pim_pre_drop_20260731T145648.sqlc`），PG18 停回 down 只留 `ai_pim_test`。
  - 新增 `scripts/where-am-i.sh`（环境体检，被各文档定为开工第一条命令）与
    `scripts/build_frontends.sh`（版本注入 + 后台按 `base '/admin/'` 构建；
    当天早先那版还带 `merge_admin_static` 资产合并，见下面的返工条目）。
  - `scripts/start_demo.sh` 修了 3 个问题（`nohup` 改 `setsid`、后端探活、端口参数化），
    `scripts/stop_demo.sh` 改为按 `PIM_DEMO_PORT` 停，不再误杀其他实例。
    演示服务器端口统一固定 **5173**，`PIM_DEMO_BACKEND=http://127.0.0.1:888`。
  - 文档：重写 `/home/AI-PIM/从启动到穿透.md`（旧版教人起本机 uvicorn，是事故根因），
    `README-OPS.md` 增「这台机器的实机真相」「升级发布 runbook」「已知缺口」，
    `README.md` / `HANDOFF.md` 同步实机口径，`docs/06-部署方案.md` 头部标注与实机的偏差。
  - 更正了一处长期写错的根因：`:888/admin/` 资源 404 **不是** nginx 正则 location 优先级问题
    （`default.conf` 里没有正则 location），而是后台按 `base '/'` 构建、index.html 引用 `/assets/...`
    落到了门户目录。`scripts/build_frontends.sh` 的头注释与相关文档已改。
  - 已知未修（当天晚些时候的返工条目已修掉第一条）：`:888/admin/` 硬刷新会掉到门户页；
    `scripts/db_backup.sh` 默认连 `localhost:5432/ai_pim`，
    在本机连不到生产库且可能**静默备份错的同名库并报成功**（两份运维文档已改成 `docker exec` 写法）。

- **2026-07-31 验收退回后的返工（当时仍标 `v1.8.5`）** —— 用户在上一次「四个入口全 200」
  之后退回了 4 条：卡片视图点卡片白屏、`:888/admin` 与公网 `/admin` `/share` 白屏、产品列表滚轮卡顿、
  操作日志时间要北京时间 24 小时制。逐条的修法与实测：

  - **白屏（根路径跳转）**：后台是按 `base '/admin/'` 构建的，任何 `window.open('/products/x')` /
    `location.href='/login'` 这类根绝对路径都绕过 base，落到 nginx 的 `location /`（门户）→ 白屏。
    卡片改成 `router.push`，`frontend/src/api/index.ts` 的登录跳转改成从 `import.meta.env.BASE_URL` 派生。
    新增 `frontend/tests/e2e/product-grid-detail.spec.ts` 钉住（3 用例 × 2 项目）；
    做过反向验证：把 `window.open` 加回去，正好那两条导航用例失败。
  - **白屏（`:888/admin` 与公网入口）**：`docker/nginx/conf.d/default.conf` 加 `absolute_redirect off`
    （nginx 默认把 301 的 Location 拼成 `http://$host` 不带端口 → `:888/admin` 被跳到 80 端口）
    和 `location = /admin` 的 301；`/share/` 不再 alias 到后台目录，交给 `location /` 回落到门户
    （分享页现在是 `portal/src/views/SharePage.vue`）。`merge_admin_static` 已删除。
  - **滚轮卡顿**：列表封面改走服务端缩略图 `GET /api/v1/files/{id}/content?w=<短边宽度>`，
    白名单 `96/192/240/480/960`，白名单外回 422（`code 42205`，不静默退回原图）；
    缓存是 MinIO 派生对象 `derived/thumb/w{width}/{oss_key}.webp`，读穿式，替换文件时逐宽度清理。
    实现从 `app/api/v1/files.py` 抽到新的叶子模块 `backend/app/services/thumbnails.py`
    （`files.py` 为了 `get_db` 牵连 `app.core.database`，按 `backend/tests/unit/conftest.py` 的约定进不了单元层），
    新增 `backend/tests/unit/test_thumbnails.py` 8 条。
    实机复测（重建后的 `:888`，14 张封面）：表格视图 5,112,803 B → 20,030 B、位图 1.02 MP；
    卡片视图 72,900 B / 4.56 MP；缺 `w=` 的请求 0 个；同一宽度冷 460 ms → 热 8~9 ms 且字节一致。
  - **操作日志时间**：新增 `frontend/src/utils/beijingTime.ts`（固定 `Asia/Shanghai` + 24 小时制，
    不跟随浏览器时区），`frontend/src/views/Logs.vue` 改用它，配 `frontend/tests/unit/beijingTime.spec.ts`
    与 `frontend/tests/components/Logs.spec.ts`。
  - **顺手修掉的潜在故障**：`files.py` 顶层无条件 `from PIL import Image`，而 `requirements.txt` 里
    `pillow==10.2.0; python_version < '3.13'` 是条件依赖 —— 在 3.13+ 的机器上整个 app import 即崩。
    改成在 `encode_thumbnail` 内部 import，缺 Pillow 时只有缩略图这一条路降级。
  - **返工中自己踩的一个坑（已修）**：重建 backend 镜像时没导出 `APP_VERSION` / `BUILD_ID` /
    `GIT_COMMIT` / `BUILD_TIME`，compose 的默认值生效，`/api/v1/health` 自报 `"version":"dev"`，
    后台「版本」页会按 `build_id` 判成「前后端版本不一致」。带上这四个 export 重新
    `docker compose up -d --no-deps backend`（**不用重建镜像**，运行时 env 覆盖镜像 ENV）后实测
    `/api/v1/version` = `1.8.5 / local-20260731T101832Z / dbce35e-dirty / 2026-07-31T10:18:32Z / production`，
    与 `frontend/dist` 里注入的 `BUILD_ID` 完全一致。`README-OPS.md` 的「升级发布 runbook」已把这一步
    写成第 3 步，「已知缺口」#3 同步扩写。
  - 验收记录：`vue-tsc --noEmit` 通过；`vitest run` 22 文件 / 167 通过；后台 Playwright 74 通过 / 2 跳过
    （env 门控的 `manuals-real.spec.ts`）；门户 Playwright 16 通过；`backend/tests/unit` 90 通过
    （宿主上首次真正跑起来，见 `README-OPS.md` 排障 §12 的临时 venv 配方）。
    四个入口在 `:888`、`:5173` 和公网三条链路上都用真浏览器验过渲染内容，不只看状态码。

## v1.8.5 — 2026-07-30

- 门户首屏按 reeoo 风格改版：巨号标题 + 胶囊输入框 + 扇形叠放产品卡堆 + 四格能力入口；回答、待确认动作、比较表、来源、技术详情下移并滚动逐段淡入。
- 卡堆默认放推荐产品，AI 返回产品后整堆替换；无 `product:view` 权限时退化为空白占位卡。
- annotated tag `v1.8.5`，直接发布在 `main`。

## v1.8.2 — 2026-07-30

- 门户界面重构，技术信息改为折叠。
- 发布提交 `669b14d`，**没有 annotated tag**（不符合规范 §1，记录在案）。

## v1.8.1 — 2026-07-29

- 门户界面美化。
- 发布提交 `5024c16`，**没有 annotated tag**（同上）。

## v1.8.0 — 2026-07-29

- Knowledge Gateway 上线：`POST /api/v1/knowledge/query` + SSE 流式协议 + RuleBasedPlanner。
- AI Portal 独立门户上线；统一演示入口（同源 `/api` 转发、`/admin/` 反向代理、健康检查端点）。
- `AI_ADAPTER=openai` 成为默认，`AI_CHAT_MODEL=agnes-2.5-flash`，`KNOWLEDGE_GATEWAY_ENABLED=1` 默认启用。
- annotated tag `v1.8.0`，发布门禁结论 GO（详见 `BUILD_LOG.md`）。

## v1.0.3 — 2026-07-23

- UI 打磨与布局改进。annotated tag `v1.0.3`。

## v1.0.2 — 2026-07-23

- 修复分享页图片不显示：分享接口改为返回后端代理的图片 URL。annotated tag `v1.0.2`。

## v1.0.1 — 2026-07-23

- 开始执行 `版本控制规范和Git.md`（规范 §1 的起始版本）。annotated tag `v1.0.1`。

---

版本号跨度说明：`v1.0.3` → `v1.8.0` 之间的 AI 基线工作（`afe7e77` phase 1 knowledge gateway、`b5a9525` AI planning baseline、`ad1ef5c` pluggable AI migration）没有单独发版；`v1.8.3` / `v1.8.4` 从未存在，不是漏记。
