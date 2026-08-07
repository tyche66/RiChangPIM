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

## v1.9.1 — 2026-08-07

本版本将当前工作区中尚未发布的产品媒体导入、Knowledge Gateway / AI 能力增强、媒体访问和运维编排改动统一发布，并同步项目文档与迁移交付物。

### 产品与媒体导入

- 产品批量导入支持 XLSX/XLSM 内嵌图片、ZIP 图片和按产品编号前缀自动归属。
- 支持主图、产品附图和场景图绑定，按 SHA-256 去重并写入 MinIO。
- 导入按行使用 SAVEPOINT 隔离失败，新增导入模板下载和图片处理结果明细。
- 导入限制、外链抓取 SSRF 防护、图片格式和超时行为同步到 API 文档。

### AI 与知识能力

- 更新 OpenAI-compatible Adapter、Knowledge Gateway、模型规划、产品工具和推荐链路。
- 保持 AI 业务数据回查、权限控制和待确认动作边界；AI-Docs 继续作为独立可插拔设计目录。

### 运维与文档

- 同步媒体访问、缩略图、nginx 上传限制和 Compose 配置。
- 新增双语 README、数据卷文档、MinIO 文档和云端更新包文档。
- 将历史概念方案、旧部署方案、旧路线图、审查 / 交付报告和未实现热插拔设计归档到 `docs/过时/`。
- 创建 v1.9.1 全量迁移包和不含业务数据的云端更新包，包内均附 `1.9.1-V-Log.md`。

### 已知缺口（本轮未修，属部署/CI 配置）

- `docker-compose.yml` 把 `APP_VERSION` 默认成 `dev`。用 compose 起服务且没传 `APP_VERSION` 时，后端报的是 `dev`，压不到第 3 处的兜底值——兜底只在环境变量完全没设时生效。
  重建 backend 前必须按 `README-OPS.md`「升级发布 runbook」第 3 步导出 `APP_VERSION` / `BUILD_ID` /
  `GIT_COMMIT` / `BUILD_TIME`，否则后台「版本」页会判成「前后端版本不一致」（2026-07-31 返工时踩过）。
- `.env.example` 里 `VITE_APP_VERSION=dev` 同理。
- 前端没有独立镜像（无 `frontend/Dockerfile`）：`frontend/dist` 由宿主机构建后 `COPY` 进 nginx 镜像。
  从 2026-07-31 起改用 `scripts/build_frontends.sh` 构建，它会注入真实的 `VITE_APP_VERSION` /
  `BUILD_ID` / `GIT_COMMIT` / `BUILD_TIME`，「版本」页显示的是真话；但**裸 `npm run build` 仍会退化**
  成 `frontend/package.json` 的值 + `dev-local` + `unknown`。

### 媒体库分页修复（`GET /files` 排序改为全序 + 服务端排序）

媒体库「没有翻页控件、也看不到全部文件」是两个独立原因叠在一起。翻页控件早就写在源码和
`frontend/dist` 里，但线上跑的 nginx 镜像还是旧的，容器里 `MediaLibrary-ah9VSZWl.js` 一次
`media-pagination` 都搜不到，且旧 `media` chunk 根本不发 `page` / `size`，后端按默认
`size=20` 只给 20 条 —— 3104 个文件里看得见 20 个。更要紧的是第二个原因：即使翻页控件在，
按当时的排序也翻不全。`ORDER BY create_time DESC` 不是全序（3104 行只有 25 个不同的
`create_time`，其中 2637 行是同一次带图导入写下的同一个时间戳），并列行在 `OFFSET/LIMIT`
下的先后是不确定的 —— 实测 32 页 × 100 条走完，拿回 3104 行里只有 2628 个不同 id，314 行重复、
**476 个文件哪一页都翻不到**。

- `backend/app/api/v1/files.py`：新增排序白名单 `_SORT_ORDERS`，四种排序（`newest` /
  `nameAsc` / `nameDesc` / `size`）全部以 `Attachment.id` 结尾作末位比较键，让整体顺序唯一确定。
  新增 `sort` 查询参数（默认 `newest`），不在白名单里返回 422 `42206`。修复后同样走 32 页：
  `total` 3104、取回 3104 行、3104 个不同 id、0 重复 0 遗漏；`sort=nameAsc` 的分页序列与单条
  `ORDER BY file_name, id` 全量查询逐行一致。
- `frontend/src/api/media.ts`：`listPage` 透传 `sort`。
- `frontend/src/views/MediaLibrary.vue`：删掉对 `rawItems` 的本地排序。本地排序只能把当前这
  一页摆好看，跨页顺序还是后端那套 —— 选「文件名 A-Z」翻到第 2 页会从中间某个字母重新开始。
  排序整体交给后端。
- `backend/tests/test_media_and_permissions.py` 新增两条回归用例：造 10 个同一 `create_time`
  的附件，四种排序各逐页走完，断言「取到的 id 去重后正好是全部」（这条用例在修复前的代码上
  会以「有文件被重复返回、另有文件翻不到」失败）；以及未知 `sort` 必须 422 `42206`。
- 文档：`docs/04-接口规范(OpenAPI).md` 原来没有 `GET /api/v1/files` 的条目，新增 §14.5
  「媒体库文件列表」，写明六个查询参数、42201 / 42206，以及「**排序必须是全序**」——
  以后加新排序字段也必须在末尾补 `id`。接口计数行「文件管理」由 4 改为 5。

**本轮验证**：`vue-tsc --noEmit` 干净；`vitest run` 23 文件 / 184 通过；`eslint` 全量 11 error /
54 warning，与既有基线一致，本轮改的两个前端文件 0 条；`ruff check app/api/v1/files.py` 3 条
（UP028 + 两条 E501），与改动前的基线逐条相同，未新增；媒体套件 23 passed，媒体 + 场景 32 passed；
后端全量 `5 failed, 577 passed, 2 skipped`，5 条失败均为环境原因（3 条 rag-indexer 需
`AI_EMBEDDING_DIM=1536`，补上后该文件 16 条全通过；2 条版本用例需要容器里不存在的同级
`frontend/package.json`）。构建先按要求跑了裸 `npm run build`（`✓ built in 6.51s`），随后按上面
「已知缺口」用 `scripts/build_frontends.sh` 重跑以恢复 `/admin/` base 和真实版本元数据。

**部署方式的例外**：`docker compose up -d` 目前会失败在
`stat /run/guest-services/distro-services/richangpim.sock: no such file or directory`
（Docker Desktop 对本 WSL 发行版的集成 socket 不存在），所以本轮是把新 dist 和改过的
`files.py` 用 `docker cp` 送进正在运行的容器，再 `nginx -s reload` / `docker restart backend`
完成的。`docker compose build nginx backend` 已经成功、镜像是新的，socket 问题解决后应按
runbook 正常 `up -d --no-deps` 重建一次容器。

### 批量导入支持产品图 / 场景图（`POST /products/import` 重写）

导入接口原来只认文字列：表里贴着的图片、和表格一起发来的图片文件夹全都被丢掉，导完还得逐个产品手动上传主图
—— 「批量」省下的工在这一步又赔回去了。本轮把三种给图方式接上，并把「一行失败带走整批」的老毛病改成按行隔离。

- 新增 `backend/app/services/excel_images.py`：从 xlsx 里解出内嵌图片并算出它落在哪一行哪一列。
  浮动图片（drawing anchor）、WPS 的「嵌入单元格」（`DISPIMG` + `cellimages.xml`）、
  Excel 365 的「置于单元格内」（richValue）是三套不同的 OOXML 表示，各走一条路。
- 新增 `backend/app/services/product_import.py`：表头识别（中英文别名、列名带 `*`、表头不必在第一行，
  向下扫 16 行）+ 行解析（面价占位值 99999 ↔ `completeness_status=pending`、多值列拆分、超长截断）
  + `build_import_template()` 生成模板（`产品` / `填写说明` 两页）。
- 新增 `backend/app/services/product_import_media.py`：图片归属（主图列→封面、产品图列→附图、
  场景图列→场景图）、zip 包解包、按产品编号前缀自动归属、外链抓取（默认关，带逐跳公网 IP 校验）、
  sha256 批内去重 + MinIO 上传。
- 重写 `POST /api/v1/products/import`：先把图片落到对象存储和 `attachment` / `scene_image`，
  再按行开 SAVEPOINT 建产品并绑图。同一张图（按 sha256）全批只传一次、只建一条 attachment；
  同一张场景图被多行引用时只建一条 `scene_image` 由多个产品共享。返回体新增
  `image_count` / `scene_image_count` / `uploaded_count` / `image_sources` / `image_warnings` /
  `header_row` / `unknown_headers` / `blank_rows`。
- 新增 `GET /api/v1/products/import-template`（需 `product:import`）：Import.vue 里一直写着
  「请下载模板文件」，却从来没有下载入口，用户只能照页面上那段中文说明猜列名。
- 新增配置项 `PRODUCT_IMPORT_*`：单文件 512MB、单次 5000 行、单张图 20MB、每行 10 张产品图 +
  30 张场景图、外链抓取开关与超时。
- nginx（`docker/nginx/nginx.conf` 的两个 server + `docker/nginx/conf.d/default.conf`）给
  `location /api/v1/products/import` 单独放宽：`client_max_body_size 512M`、
  `proxy_send_timeout` / `proxy_read_timeout` 900s。server 级的 100M 没动，改动范围只落在这个接口。
- 前端 `Import.vue`：模板下载入口、`accept=".xlsx,.xlsm,.zip"`、七条与后端行为对得上的填写说明、
  上传进度条 + 「文件已送达，服务端正在处理」的第二阶段提示、图片张数 / 取图方式 / 图片提示三块结果展示。
  `productApi.import` 超时从 30s 提到 905s（对齐 nginx 的 900s），并按 413 / 超时 / `detail.msg`
  分别给中文话术；失败明细那一列的 `prop` 从 `productNo` 改成后端真实的 `product_no`（原来整列是空的）。
- 文档：`docs/04-接口规范(OpenAPI).md` §8.8 按新返回体重写、新增 §8.9 模板下载（导出产品顺延为 §8.10）。

**有意保留的边界**：品牌 / 供应商 / 分类不会被导入自动新建（三者在库里都是 NOT NULL 外键，主数据归各自的
管理页维护，一个错别字凭空造出个品牌比这行导不进去更难收拾），所以在一个空系统里直接导模板会每行都失败；
`http(s)` 直链默认不抓（服务端替用户 GET 任意地址就是 SSRF，要开由管理员置
`PRODUCT_IMPORT_ALLOW_URL_FETCH=true`）；`.xls` 不再宣传（`requirements.txt` 里没有 xlrd）；
gif / bmp / tiff 需要 Pillow 才能转成 png，装了就转、没装就跳过并在 `image_warnings` 里写明原因。

**本轮验证**：`vitest run` 23 文件 / 184 通过、`vue-tsc --noEmit` 干净；ESLint 保持既有基线 10 errors / 0 warnings（未修改既有测试问题）；
`backend/tests/unit/test_excel_images.py` + `test_product_import.py` + `test_product_import_media.py`
本机 148 passed；导入媒体集成测试本机真实 PostgreSQL 测试库 5 passed；`ruff check` 仅保留
`products.py:657` 和 `products.py:862` 两条既有 E501 基线，未新增错误。

**真实样本实测（2026-08-03）**：圣奥样本表 4255 行、zip 259MB、包内 4242 张 JPG。
仅监听 `127.0.0.1` 的本机 uvicorn 通过落盘假 MinIO 接收对象，未连接真实 MinIO；鉴权仍走
`PermissionChecker("product:import")`，使用 `admin/admin123` 获取 token，没有绕过鉴权。HTTP 200，
墙上时间 27.68s，进程 `VmHWM=995956 kB`（约 972.6 MiB）；返回 `success_count=4011`、
`fail_count=244`、`image_sources=["zip"]`、`image_count=3998`、`scene_image_count=0`、
`uploaded_count=3078`、`header_row=1`、`unknown_headers=[]`、`blank_rows=0`、`image_warnings=[]`。
244 条失败全部是「分类为空（产品必须挂在分类下）」；另有 13 条成功行原始表的三种图片列
均为空，zip 里也没有以这些产品编号命名的图片，所以这 13 个产品没有图片，不是导入丢失。
数据库核对为 `product=4011`、`attachment=3078`、`product_image=3998`、`scene_image=0`、
`product_scene_image=0`；3998 个有图产品各一张 `is_cover=true`，13 个无图产品没有封面；
假 MinIO 落盘对象 3078 个，与 `uploaded_count` 一致。

**本轮验证**：前端 `vue-tsc --noEmit` 干净、`vitest run` 23 文件 / 184 通过；后端 unit
148 passed；导入媒体集成测试真实 PostgreSQL 测试库 5 passed。两份 nginx 容器配置使用临时
包装配置和自签证书分别通过 `nginx -t`。重建 frontend/portal 产物后，dist 中已不存在旧的
「仅支持 .xlsx / .xls 格式文件」提示。ruff 对本轮文件只剩既有 `products.py:657` 和 `:862`
两条 E501 基线。

**全量回归结果**：在本地 Docker Desktop 开发栈运行中，使用临时测试 MinIO 端口和
`ai_pim_test`，全量 `pytest -q -p no:cacheprovider` 为 `582 passed, 1 warning`，耗时
`124.30s`。期间修正了认证异常降级路径在 `rollback()` 后继续访问过期 ORM 属性的问题，
并将迁移 schema 测试中遗留的 `0014_knowledge_tables` 断言更新为当前 head
`0017_operation_log_username`。

**未完成或不代表生产链路的验证**：裸 xlsx 对照上传未执行。真实样本导入仍使用落盘假
MinIO；全量回归使用的是临时测试 MinIO，不等同于生产对象存储。nginx 做了容器配置语法
校验，但没有启动生产云端 nginx。前端页面要等下一次 `docker compose build nginx` 才会
包含新 dist，本轮没有重建 nginx 镜像。

**本地 Docker Desktop 真实 HTTP 复测（2026-08-03）**：上面的限制已在本地开发栈补做。
此前用户通过 `127.0.0.1:888` 上传 259MB zip 得到 413，原因是运行中的 nginx 容器仍是旧镜像，
容器内 `default.conf` 只有 server 级 `client_max_body_size 100M`，没有新的导入 location。
使用当前源码重建并仅重建本地 `backend` / `nginx` 后，容器内实际配置确认了
`client_max_body_size 512M`、`proxy_send_timeout 900s`、`proxy_read_timeout 900s`。
同一个 `271,838,487` 字节 zip 通过用户实际访问的 `http://127.0.0.1:888`，携带真实本地
管理员 Bearer token，返回 HTTP 200，上传耗时 13.65s；首次导入因本地开发库缺少样本分类，
538 行成功、3717 行按行失败。补齐样本 101 个非空分类后，以 `skipIfExists=true` 重试，
3473 行成功、782 行按预期跳过，图片来源为 `zip`，图片计数 3463，上传对象 2637。
前后两次合计覆盖 4011 个产品、3998 张产品图；没有再次出现 413。随后在干净的
`ai_pim_test` 上用真实 uvicorn 和临时 MinIO 做裸 xlsx 对照，HTTP 200，`4011` 行成功、
`244` 行因分类为空失败，`image_count=0`、`uploaded_count=0`；所有填写图片名的行都产生了
“上传的文件里没有图片”的 `image_warnings`，文字导入没有被图片缺失整批阻断。


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

### 发布与上线（2026-07-31 实测）

- 提交 `9cd132c`、annotated tag `v1.9.0`，均已推到 `origin/main`（`github.com/tyche66/RiChangPIM`）。
- 生产栈按「升级发布 runbook」重建：`scripts/build_frontends.sh` 出产物后 `docker compose build backend nginx`
  + `up -d --no-deps`。`/api/v1/version` 实测
  `1.9.0 / local-20260731T134109Z / 9cd132c / 2026-07-31T13:41:09Z / production`，与 dist 里的
  `/admin/assets/index-EbCCaYhV.js` 同一套值，「版本」页不再报前后端不一致。
- 四个入口：`:888/` 200、`:888/admin` 301→`/admin/`、`:888/admin/` 200（后台 JS 200 `application/javascript`）、
  `:888/share/abc` 200、`:888/api/v1/health` 200；演示服务器 `:5173/admin/` 与 `:5173/chat` 200。
  `alembic current` = `0017_operation_log_username (head)`。
- 回滚镜像留了 `richangpim-nginx:pre-v190` / `richangpim-backend:pre-v190`，暂不清理。
- 全量备份迁移包：`/home/AI-PIM/RiChangPIM_v1.9.0_20260731_215300.tar.gz`（240,369,356 B，
  sha256 `cb4f9fc1…99ca6`），结构对齐 v1.8.0 参考包，`sha256sum -c` 20/20 通过，
  换目录解包复验过源码锚点与 bundle 内的 `v1.9.0` tag。打法与恢复步骤见新增的 `MIGRATION_BUNDLE.md`。
  打包全程未停、未重启任何服务；库走 `docker exec … pg_dump -Fc`。

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
