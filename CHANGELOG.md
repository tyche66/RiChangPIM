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

## v1.9.9 — 2026-10-31

本版把产品知识卡的向量索引从「每分钟常驻轮询」改为「夜间窗口调度」，修复了导致同一批内容被反复 embedding 的重复计费根因；后台新增「向量索引」管理页（启停、窗口、报告、积压、手动灰度）。同时合并一组安全加固：登出撤销 refresh token、Redis 故障时撤销检查 fail closed、分享口令改存哈希、口令长度边界统一、日志路径脱敏、健康检查与 CORS 收敛。

### 夜间向量索引调度（替代常驻 knowledge-indexer）

- 新增 `app/services/knowledge_index_scheduler.py`：默认 **Asia/Shanghai 01:00–02:30** 窗口，**02:25 安全截止**后不再发起新的 embedding；窗口外完全空闲，不再每分钟全表扫描。未完成任务留在队列，次夜续跑。
- 单例互斥：进程内 `asyncio.Lock` + 跨进程 Postgres advisory lock，多个 backend worker / CLI 进程不会并行跑同一轮。
- 重复计费根因修复：
  - reconcile 不再把 `failed` 任务重置为立即 `pending`，也不清空 `next_attempt_at`；只有内容 hash / pipeline / embedding model 变化或管理员显式「重置重试」才重开确定性失败。
  - embedding 前先比对产品卡内容 hash、embedding model/version 与现存有效向量，全部匹配则跳过外部调用（零 token）。
  - 上游超时、`AIAdapterError` 与未知错误均递增 `attempt_count` 并走指数退避，达到上限进入 dead/隔离；429 不消耗重试预算。
  - 写库按产品 `savepoint` + 逐产品提交隔离，单个产品失败不再回滚同批其他产品；确定性数据库错误直接隔离，不反复重算。
  - `KnowledgeJobDispatcher.enqueue_job` 不再复用 `failed` 任务（编辑/导入/克隆不会绕过退避），改为新建 pending，旧 failed 保留计数并让位。
  - 领取任务按「同组最新一条非终态」去重，历史多条 failed 并存时同一产品每轮也只 embedding 一次。
  - 启动恢复只回收本进程启动前遗留的 `running` 报告，且仅在 `current_run_id` 指向该报告时清空；某个 worker 重启不会抹掉其他 worker 正在跑的报告。
- 管理端手动 run-now 由后端硬限 **200 个不同产品**，CLI `--once` 与 API 共用同一约束（`RUN_NOW_HARD_CAP`），不受配置项放大。
- dead 任务保留 **90 天**，分批清理；pending / processing / 未过期记录不触碰。
- 服务心跳、调度状态与下次运行时间落库，`/status` 不再以容器 Up 状态 判断「在工作」；运行报告不外泄任何 Key、口令或 DSN。
- 迁移 `0037_knowledge_index_scheduler`：`knowledge_index_setting`、`knowledge_index_run`、调度状态单例表；`knowledge_index_job` 活动任务部分唯一索引（pending/dispatched/processing）；`knowledge_document` 活动文档部分唯一索引（同键仅一个未删除文档，重复行软删而非物理删除）；种子 `knowledge:index` 权限并绑定 admin。
- 新增管理 API（`PermissionChecker` + 审计，仅管理员）：设置读改、运行报告（最近一次 + 近 30 次）、队列积压、run-now、授权失败任务重置。
- 后台新增「向量索引」页：启停开关、窗口与批大小配置、下次运行/安全截止倒计时、心跳与当前状态、积压与 dead 统计、近 30 晚报表、run-now（标注最多 200 个）、失败/隔离清单与重置；页面时间按调度时区 `Asia/Shanghai` 显示，不随浏览器时区漂移。

### 安全加固

- 登出同时撤销 access 与 refresh token；前端登出显式提交 `refresh_token`，后端仅在 `sub` 一致且类型为 refresh 时撤销。
- `is_jti_revoked` 在 Redis 不可用或查询异常时按 `APP_ENV=production` **fail closed**：无法确认撤销状态就拒绝该 token，不再静默放行已撤销凭证；测试环境保持不依赖 Redis。
- 新增迁移 `0038_share_password_hash`：`share_token` 口令改存 bcrypt 哈希（`password_hash`）。存量明文在升级时原地哈希，并同时写回 `password` 列，使回滚到旧版本时分享变为需口令而非变成无口令；`$2a$/$2b$/$2y$` 前缀视为已哈希，幂等。
- 口令统一 72 字节（bcrypt）上限与最小长度校验，后端 `ensure_bcrypt_compatible` 与前端 `passwordRules` 同规则。
- 审计中间件、可观测性接口与后台管理接口补充管理员/内部来源约束；`/api/v1/share/{token}`、`/api/v1/files/{id}/*` 在 nginx 与后端访问日志中做路径脱敏，`/share/` 下发 `no-referrer`。
- 健康检查与 CORS 收敛到显式白名单，不再默认放开。

### 数据与部署

- 迁移链 head：`0038_share_password_hash`（`0037` → `0038`，均为幂等 DDL，可在生产的 `0024` 基线上连续升级）。
- **切换顺序**：先停旧的常驻 `knowledge-indexer` 容器，再启动新后端。旧容器不走 advisory lock，与新调度器并存会双发 embedding。
- 首晚建议先用 run-now 灰度（≤100 产品）验证，再放开全量夜间窗口。
- 回滚：代码回退到 v1.9.8 前，先确认 `0038` 的 `password` 列仍是可用的 bcrypt 哈希（迁移已双写）。

## v1.9.8 — 2026-10-30

本版把产品列表的分类筛选重做成**三级筛选导航**，补齐**产品交货期**字段，并让产品 / 说明书
变更**自动触发知识卡片重建**（含产品图视觉标注）；门户比较表补上主图与 MD / PDF 导出。

### 产品列表三级筛选导航
- 新增 `GET /api/v1/products/filter-options`：`series / brand / supplier / status / stock / category` 六个维度的二级、三级选项与计数全部由产品表实时聚合，没有产品的选项不会出现，重复值由 `GROUP BY` 去重。
- 「系列」三级只取 `tag_type='series'` 的标签，「品类」三级取规格第一段（`1200*600*750` → `1200`，兼容 `W2000*1000*750`）；两个维度的三级数据源相互独立，同名二级分类不会串数据。
- 产品列表与导出新增 `tag_type`、`spec_length_mm` 过滤参数；分类筛选改为包含全部后代分类，与菜单计数口径一致（系列维度用 `tag_type=series` 对齐「有系列标签」的计数）。
- 后台产品页：一级滑动标签（系列 / 品牌 / 供应商 / 状态 / 库存 / 品类）+ 二级分类 + 三级标签，胶囊行固定行高、超量滚动，深色模式沿用设计令牌；原品牌 / 供应商 / 系列 / 状态 / 库存表单项与「高级筛选」移除，关键词、价格区间、查询/重置与其余工具栏保留。

### 产品交货期
- `product.delivery_period`（迁移 0036）+ API schema + 导入表头别名（交货期 / 交期 / 货期 / lead_time）+ 导入模板列 + 导出列，打通「导出 → 改 → 导回」。
- 产品列表表格 / 卡片、详情页、编辑表单均展示；知识卡片 facts 同步收录，参与检索。

### 知识索引自动重建与视觉标注
- 产品新增 / 修改 / 删除 / 克隆、图片增删与封面变更、批量导入、说明书创建 / 解析 / OCR / 删除全部接入 `KnowledgeJobDispatcher`，自动登记 upsert / delete 任务。
- 产品卡片新增「类目路径」「交货期」「外观标签」；新增 `product_image.vision_tags` 与 `ai_provider_config.vision_model`（迁移 0036）。
- 新增 `app/knowledge/vision/tagger.py`：按需调用多模态模型给产品图打 3–8 个外观标签（每产品最多 3 张），未配置视觉模型时静默跳过；适配器新增 `vision_chat`，AI 配置中心可填视觉模型。
- 迁移 `0035_knowledge_chunk_partial_unique`：`knowledge_chunk` 唯一索引改为只约束未删除行，避免内容重建与软删除历史行冲突。

### 产品详情与门户
- 产品详情页顶部新增大图 hero 与缩略图灯箱，点击查看全部产品图。
- 门户比较表新增主图列（点击灯箱放大）、MD 导出与 PDF 导出（`POST /api/v1/products/compare-pdf`，复用 Gotenberg，只接受产品 ID 并回库取数）。

### 其他
- `.gitignore` 增加 `回收站/` 与 `.qoder/settings.local.json`；回收站内历史文件清理。
- `.env.example` 增加 `AI_VISION_MODEL`；新增知识索引常驻脚本 `backend/app/scripts/knowledge_indexer.py`。

## v1.9.7 — 2026-10-29

两件事：**方案平面图**（分享页「方案信息」右侧展示、可全屏缩放）与**产品包重传**
（先预检、再选覆盖 / 追加 / 跳过）。

### 方案平面图（Track D）
- 新增 `proposal_floor_plan` 表（迁移 `0032_proposal_floor_plans`）：图片本体仍在媒体库（MinIO + `attachment`），本表只存「方案 / 项目归属 + 展示名 + 排序」，删除绑定不删媒体文件。
- 新增 `GET|POST /api/v1/proposals/{id}/floor-plans`、`POST .../batch`、`PUT|DELETE .../{floor_plan_id}`，权限沿用 `proposal:view` / `proposal:edit`，方案确认后仍可维护（平面图是展示物料，不是价格事实）。
- 方案详情接口随响应返回 `floor_plans`（带 15 分钟短 token 地址）；公开分享接口在 `content.floor_plans` 透出，匿名访客仍不接触 MinIO 地址。
- 媒体库：被平面图引用的附件计入引用数，删除时提示「方案平面图」并拒绝，引用详情新增 `proposal_floor_plans`。
- 迁移 `0033_sales_media_permissions`：给 `sales` 补 `media:view` / `media:upload`（不含 delete / replace），否则业务员无法从媒体库选图或上传。
- 后台：方案详情页新增「方案平面图」区块（上传 / 从媒体库选用 / 改名 / 上下移 / 删除 / 预览），新增方案对话框可先暂存多张，方案创建成功后一次性绑定；「上传平面图」按钮对 `proposal:edit` 之外的只读用户禁用。
- 门户：分享页「方案信息」改成左右两栏，右侧为平面图缩略图（超过 4 张显示 `+N`），点击进原生 `<dialog>` 全屏查看器，支持滚轮 / 双指 / 按钮缩放（0.5x–5x）、放大后拖拽、左右键切换。

### 产品包重传：预检 + 覆盖 / 追加 / 跳过
- 新增 `POST /api/v1/products/import/preflight`：上传后只解析、只查重，**零写库**，返回 token（2 小时有效）+ 新增 / 已存在 / 无法导入计数 + 冲突清单（最多 200 条）。
- 新增 `POST /api/v1/products/import/commit`：按 `overwrite` / `append` / `skip` 真正写库，返回 `created_count / updated_count / appended_count / skipped_count / images_replaced / images_appended / backup_id`；token 单次消费，重复提交返回 409。
- 新增 `DELETE /api/v1/products/import/preflight/{token}`：取消预检并立刻删除暂存；暂存目录 `PRODUCT_IMPORT_STAGING_DIR`（默认 `/tmp/pim_import_staging`，TTL 2 小时，预检入口每小时限频清理一次）。
- **合并规则（关键）**：`RowFields.provided` 记录「这一行真的填了哪些列」。覆盖只写填了值的单元格，空白保留库里原值（面价、状态、库存都不会被空白打回默认）；追加只在库值为空时写；图片覆盖整套替换（该行没图则保留原图），追加按附件去重后追加；场景图软删除行会恢复而不是重复 INSERT（`product_scene_image` 主键是二元组）；标签覆盖整组替换、追加取并集。
- **标签自动创建（2026-10-29 追加）**：表格里出现系统还没有的标签（例如新系列「摩耳」）不再只记一条「已忽略」，提交时自动创建并绑定。类型取「单元格显式类型 > 导入参数默认类型」：单元格支持 `系列:摩耳`、`系列=摩耳`、`摩耳(系列)`、`series:Moer`，不写类型时按预检弹窗里选的「系列（默认）/ 未分组」创建；同名已有标签直接复用，不会重复建。预检会列出「将新建 N 个标签」及其名称，提交结果增加 `created_tags` / `new_tag_names`。
- 面价占位价 99999 与 `completeness_status=pending` 联动：写占位价必带 pending，写真实价格则把悬挂的「待补充」恢复成 complete。
- 覆盖前快照：`services/product_import_backup.py` 把受影响产品的原值与图片附件 id 写成 JSON（返回 `backup_id`），恢复入口 `python -m app.scripts.restore_import_backup <backup_id> [--dry-run]`；产品 id 不变，方案 / 报价 / 分享引用不受影响。
- 后台导入页：去掉「跳过已存在」勾选框，改成「上传 → 预检弹窗（三选一 + 冲突示例 + 无法导入明细）→ 结果面板（新增 / 更新 / 追加 / 跳过 / 失败 + 图片替换与追加 + 快照 id）」。旧 `POST /products/import?skipIfExists=` 保留兼容。

## v1.9.6 — 2026-10-28

本版交付**首批 20 系列产品属性索引**（词典 `series` 选项 + 217 条系列级 mapping，
回填 17879 条产品属性值，全部条目已业务确认）；修复「现代风格」这类自然语言查询
返回空的三层根因（词典别名不全、模型字典上下文只有 option code、纯英文词被误判成
产品型号）；在关键词/属性精确层一无所获时新增两级语义兜底（先把自然语言**归一元
到受治理属性取值**再查一次，仍无果才对召回候选做**语义筛选**）；门户新增浏览器
本地查询历史；并修复 AI 配置中心的改动约 15 秒后静默回落环境变量的问题。

### 系列属性索引扩充（2026-10-28 数据工具，随后端镜像重发布生效）
- `seed_attribute_dictionary` 新增 `SERIES_OPTIONS`：20 个系列选项 + 65 个别名，`option_code` 取系列 `tag_name`，使「灵多系列」这类问句能在查询理解层解析成 `series=灵多`。
- `backfill_product_attributes` 新增「系列（+可选类目）」条目形态：按 `product_tag`(`tag_type=series`) 展开到该系列全部在售产品，展开不到成员时告警，幂等语义不变。
- 新增 `backend/app/scripts/data/series_attribute_mapping.json`：217 条系列级规则（series/style/shape/material/color），覆盖 20 个系列。系列自身条目是 `product_tag` 事实回填；风格/桌形/材质/颜色由产品图视觉 + 官方画册/培训教材判定，其中新中式（领瑞、大都会）与现代（I-瓦尔纳Ⅱ）以官方培训教材「产品地图」分区为准，修正了视觉的 modern 误判。
- 全部 197 条 AI 候选已于 2026-10-27 经业务逐行确认，`verified` 置 true；确认范围、确认人与日期写入 mapping 的 `_confirmed_by`/`_confirmed_at`/`_confirmed_scope`，逐条 note 亦追加确认信息。`source` 保持原值（`ai_inferred` 保留 AI 溯源），回退仍可按 `source`+写入日期精确软删。
- 本地 `--check`：created=17879 / skipped=0 / unresolved=0。生效方式为容器内 `--check`→`--apply`；验收走知识网关问句与 `product_attribute_value` 统计。回退按 `source`+日期软删 `product_attribute_value`，不硬删、不清表。

### 自然语言检索与查询历史（2026-10-28 修复「现代风格」返回空）
- **根因（三层）**：① 规则层只认词典别名，说法没列进别名表就没有硬条件；
  ② 模型规划器拿到的字典上下文**只有 option code，没有中文名和别名**，
  模型无法把「现代风格」映射到 `modern`；③ 纯英文词被型号正则误判成
  `product_no`（「modern」→`product_no IN ('modern')`，把属性命中结果全部过滤空）。
- **词典补齐**：每个 style/shape/material/color 选项都补「…风格/…风」后缀与
  英文别名；`board` 补「板式」，`rect` 补「方桌/矩形桌」。
- **模型规划器**：字典上下文改为 `code(中文名): option(别名|别名)` 形态，
  并明确要求把多字少字、口语化、带程度词的说法按语义归到已定义取值。
- **型号提取**：`_extract_product_nos` 增加形态判据（必含数字或 `-._/`）与
  词典别名排除；本库 4024 个在售型号全部含数字，判据安全。`alias_labels`
  修正为存整条别名（原先 `list(字符串)` 把「现代风格」拆成了单字）。
- **新增 `app/knowledge/semantic.py`**：关键词/属性精确层一无所获时的两级兜底。
  先 `resolve_facets`——让模型把自然语言归一到受治理取值（词典内 fail-closed，
  编造的属性/取值一律丢弃）再跑一次精确 SQL；仍无果再 `screen_products`——
  对宽松/文本召回候选做一次语义筛选，挑最贴切的若干款。两级都不成立保持为空
  （「巴洛克式会议桌」仍然为空）。响应新增 `semantic_interpretation` 字段。
- **停用词**：「风格/样式/款式/系列」这类结构后缀不再作为 AND 关键词，
  否则「现代简约风格」剔除「现代简约」后剩下的「风格」会清空结果。
- **门户查询历史**：新增浏览器 localStorage 历史（`richangpim.portal.queryHistory.v1`，
  上限 30 条，只存查询文本与时间，隐私模式下降级不报错），点击条目可重跑；
  「本次查询」回显补充时间戳。不新增任何服务端存储。
- 测试：新增 `tests/unit/test_knowledge_semantic.py`（47 例：解析容错、fail-closed、
  负向保持空、型号提取、归一/筛选/兜底链路）；全量 `tests/unit` 554 passed / 5 skipped。

### AI 配置中心：模型改动 15 秒后失效（2026-10-28 修复）
- **现象**：在 AI 配置中心把选品检索模型改成 `agnes-3.0-flash`，供应商后台收到的调用仍是 env 里的 `agnes-2.5-flash`。
- **根因**：`ai_config` 的进程内缓存只在「启动」与「保存配置」时刷新，没有周期刷新；`peek()` 超过 `CACHE_TTL_SECONDS`(15s) 就返回 None，`get_config()` 随即回落环境变量——管理员的显式配置被静默丢回 env。内容工坊 scope 同理。
- **修复**：`peek()` 过期也返回旧快照（TTL 只是「该续期了」，不是「作废」）；`main.lifespan` 增加短于 TTL 的周期刷新任务，缓存始终是 DB 覆盖层真值；DB 抖动仍保留旧快照，不清空、不回落 env。
- 验收：改配置后等 20 秒（超过旧 TTL）再查询，知识网关 `usage.model` 为 DB 覆盖值。
- 测试：`tests/unit/test_ai_config_ttl.py`（过期快照仍生效、空缓存才回落 env、DB 抖动保留旧快照）；`test_ai_config.py::test_cache_ttl_expires` 改为锁新行为。

## v1.9.5 — 2026-10-26

本版本交付 AI 配置中心（`AI 功能 → AI 配置中心`，仅管理员）：选品检索与内容工坊两个域的 API 地址、API Key、对话模型 ID、可选模型列表、嵌入模型与超时改为可在后台维护，数据库覆盖优先、留空回落环境变量，保存后约 15 秒生效无需重启。同时重写内容工坊/独立选题的提示词（写作规则前置、合规规则改为后台执行），并把产品事实从 3 个字段扩展到 12 个（含受治理属性，价格/库存/供应商等隐私字段一律不进提示词）。

### AI 配置中心
- 新增 `ai_provider_config` 表（迁移 `0031_ai_provider_config`）与 `ai:config` 权限码（仅 admin）。
- 两个 scope：`knowledge`（选品检索/知识库/润色/推荐）与 `content`（内容工坊/独立选题）；逐字段覆盖，空值回落环境变量，关闭开关即整域回落。
- 读取一律返回密钥掩码；`POST /ai/config/{scope}/test` 做最小连通性探测（10s 超时、不重试、不回传上游响应体）。
- 适配器缓存按配置指纹重建，改 Key/模型后无需重启后端；启动时预热缓存。
- `GET/PUT` 命中 `PermissionChecker("ai:config")` 并显式校验 `role_code=admin`，非管理员 403。

### 内容生成质量
- 内容工坊两个 DNA Skill 与独立选题模板重写：标题/正文写作规则前置，"事实规则只在后台执行，绝不能变成正文的口吻"，禁止把免责/核验话术写进 title/body/hashtags。
- 生成侧 system 消息改为写手人格（`SYSTEM_PERSONA`），合规继续由后置守卫与 `verification_gaps` 兜底。
- 产品事实扩展到 12 字段（品类/品牌/材质/材质说明/颜色/描述/受治理属性），仅保留可信来源属性值，`ai_inferred` 未确认的丢弃；`face_price`/`stock_status`/`data_source` 等一律不进提示词。
- `--refresh` 种子模式：用代码模板原地刷新已存在的运营 Skill（原模式对已存在行只跳过）。

### 发布后修复（并入 v1.9.5）
- **迁移 0031 列名错误**：向 `permission` 插 `ai:config` 时用了不存在的 `code`/`name` 列，backend 启动即崩；已改为真实的 `perm_code`/`perm_name`，与 `0020_crm_perms` 写法对齐。
- **AI 配置中心页面空白**：前端 `src/api/aiConfig.ts` 多读了一层 envelope（`resp.data.data`），恒取到空数组；已改为仓库约定的 `resp.data`。
- **发布后白屏（须刷新才好）**：nginx 原本完全不发 `Cache-Control`，浏览器 heuristic 缓存旧 `index.html`，代码更新后旧入口 chunk 名 404。现入口 HTML 一律 `no-cache` 重新校验，带内容哈希的 `/admin/assets/` 与 `/assets/` 为 `public, max-age=31536000, immutable`。

## v1.9.4 — 2026-10-23

本版本合并三组能力：产品属性检索、内容 Skills/独立选题、方案空间与客户展示；同时把本地迁移链对齐到生产 `0024_attachment_biz_domain_compat` 基线，避免服务器升级时 revision 不识别。发布前并入一组界面修复：内容工坊改用「创作 Skills」口径、新增方案弹窗重排、分享页商品详情改为点击弹窗。

### 产品属性检索
- 引入受治理属性词典（类目、桌形、风格、材质、颜色、系列、尺寸、人数），支持中文别名、无空格组合、数值条件与否定条件。
- `product.search` 按属性硬过滤：不同属性 AND，同一属性别名 OR；`shape` 只匹配桌形属性，描述/材质文本不能冒充桌形。
- 三个业务确认的弧形会议桌（`P-104300001`/`P-104300002`/`P-104300003`）通过独立 mapping 回填 `shape=arc`；“弧形会议桌”精确命中且排除普通会议桌、弧形洽谈桌。
- 无精确结果时返回“未找到符合指定桌形的产品”，不静默放宽硬条件。

### 内容 Skills 与独立选题
- 新增 Skills 管理中心（仅管理员）、独立选题模块和 Skills 选用开关。
- 首批接入禹橙 DNA、言也 DNA 两套创作方法，各派生选题/内容 operational Skill；默认由模型自动选择，用户可手动覆盖。
- 选题按办公空间解决方案 30%、真实项目案例 25%、产品知识 20%、交付安装 15%、本地服务 10% 的滚动窗口动态分配。
- 内容域独立 `CONTENT_AI_*` 配置，模型白名单 `step-5-preview`/`sensenova-6.8-flash-lite`，不读取知识库 embedding 配置；缺少 key 时 fail-closed。
- 内容生成与选题保留 JSON Schema 校验、合规过滤、产品事实回查和待核验清单。

### 方案与客户展示
- 方案明细支持业务员自由输入楼层/空间名称，后台按项目回填/复用空间编号；无项目也可保存名称快照。
- 方案/报价保存产品快照、材质说明、楼层/空间标签；客户分享页按楼层/空间分组展示材质、颜色、材质说明。
- 报价 PDF 增加楼层、空间、材质说明、颜色列；报价预填复制方案空间与快照。
- 「新增方案」弹窗 640px → 920px，标签顶部对齐，名称/客户/关联客户/关联项目两列排布。
- 方案明细编辑器新增 `compact` 模式：数量/备注/楼层/空间两列网格，材质说明跨整行；商品搜索与「添加商品」同行，窄屏改单列。

### 界面对齐
- 内容工坊生成表单的「DNA 来源」更名为「创作 Skills」，选项显示 Skill 名称并浅色标注所属 DNA，避免把创作方法与方法来源混为一谈。
- 分享页商品列表只保留摘要列（商品/面价/数量/行合计）和「查看详情」，点击行弹出详情：规格、材质、颜色、材质说明、价格、数量与场景图缩略图网格，点缩略图从该图开始播放。
- `ProductSceneCarousel` 监听 `initialIndex`，重复打开轮播可定位到所选场景图。

### 数据库
- 迁移链以生产运行镜像的 `0024_attachment_biz_domain_compat` 为唯一基线重建：0018-0024 采用生产运行镜像版本（`0018_qwen_embedding_hnsw` / `0019_crm_base_tables` / `0020_crm_perms` / `0021_content_tables` / `0022_reminders` / `0023_crm_sales_links_compat` / `0024_attachment_biz_domain_compat`）；本地旧分支 `0018_crm_core` / `0019_crm_detail` 弃用（移入 `backend/alembic/versions/回收站/`，不删除）。
- 新增 `0025_crm_schema_compat`：在生产基线之后幂等补建 CRM 明细表（`project_members` / `entity_stage_logs` / `customer_dialogues` / `customer_dialogue_attachments` / `requirements` / `follow_ups` / `project_assets`），不再依赖 `create_all` 掩盖缺表；proposal/attachment 的 CRM 链接列仍由生产 0023/0024 负责，不重复加列。
- 本地新功能迁移重编号续链：`0026_catalog_attributes` / `0027_content_skills` / `0028_project_spaces` / `0029_project_remark` / `0030_content_dna_fields`（head，单 head）。
- 生产库（现 `0024`）沿 `0025 → 0026 → … → 0030` 连续链升级，全程幂等 DDL，不重复建表/列；`content:manage` 权限在生产 0024 库上由 `0027_content_skills` 补种。
## v1.9.3 — 2026-10-12

本版本引入 CRM-Lite 模块：客户域、项目域、驾驶舱、新媒体工坊和提醒引擎，新增 16 个权限码与 manager/designer/operator 角色，前端新增 7 个视图与通知组件。向后兼容，生产升级按 `docs/云端更新包.md` 正常执行迁移并保留数据卷即可；需求设计见 `docs/10-客户项目与新媒体(CRM-Lite).md`（其 A9 条原目标 v1.10.0，实际以本节声明的 v1.9.3 为准）。

### 新增
- 客户域：客户 CRUD、阶段状态机、PII 脱敏、对话/需求/跟进/方案子资源
- 项目域：项目 CRUD、成员管理、图纸资产（.dwg/.dxf/.skp/.psd 上传）
- 驾驶舱：5 端点（overview/funnel/sales/todos/content）+ 缓存层
- 新媒体工坊：AI 生成 + 合规守卫 + 发布登记 + 曝光录入 + Excel 导入
- 提醒引擎：R1/R1b/R2/R3/E1 规则 + worker + 通知
- 权限：16 新权限码 + manager/designer/operator 角色
- 前端：7 视图 + 3 组件 + echarts 懒加载

### 数据库
- 新增迁移 `0020_crm_perms`（16 个 CRM 权限码 + manager/designer/operator 角色种子）、`0021_content_tables`、`0022_reminders`，迁移 head 前进到 `0022_reminders`
- customers/projects 相关表由启动入口的初始化流程（`Base.metadata.create_all`）创建，不在迁移内

## v1.9.2 — 2026-09-29

本版本修复 AI 门户查询结果区的三类缺陷（卡片网格退化、推荐卡片不出图、答案 Markdown 原文直出），把后台与门户的深色模式从「逐页堆 `:global(.dark-mode)` 覆盖」重做为按语义 Token 的实现，并补一个非 Docker 的本机一键启动脚本。

### 门户（portal）：查询结果区修复

查询结果区此前有三处互相独立的缺陷：结果一多整堆卡片退化成普通网格、未查询时推荐卡片不显示图片、答案里的 Markdown 被当纯文本原样输出。

- `HeroDeck.vue` 重写：固定 5 个卡位（中心 + 左右各两环）做叠卡，`SLOT_ORDER` 按张数选卡位（1→中心；2→左右内环；3→中心+内环；4→两对内外环；≥5→全部），删掉原先「`products.length <= 9` 时才扇形、超过就落 `hero-deck--grid` 三列平铺」的分支，`:class` 恒为 `hero-deck--fan`。结果超过 5 条时用 `windowStart` 做循环窗口；滚轮用**函数 ref 手动挂 non-passive 监听**并 `preventDefault()`（模板 `@wheel` 在某些场景不可靠，passive 下 `preventDefault` 无效还会打警告），220ms 手势合并窗口防止触控板惯性连跳；键盘 `↑↓←→/PageUp/PageDown`（卡堆 `tabindex=0`）与窄屏「上一组/下一组」按钮共用同一 `step()`。卡片 key 为 `variant-index-业务ID`，轮换时数据索引与卡位一对一；`watch(() => props.products)` 在换一次查询时归零窗口（同时盯 length 和数组引用，同数量的重查也能复位）。
- `ProductCard.vue`：`failedUrl` 记录**哪一条地址**失败而非布尔值，`onError` 判重避免重复触发，换地址时 watch + `:key` 重置；媒体区固定 `aspect-ratio` + 图标文字占位块，加载前后卡片高度一致；新增 `data-image-state="ok|error|missing"` 便于排障。状态显式分流为 loading / empty / recommend / placeholder，不再互相顶替。
- `AnswerBody.vue` 改为 Markdown 渲染容器 + 角标事件委托。
- `Conversation.vue`：`deckMode` 收敛为五种互斥状态并补文档注释。
- 新增 `utils/image.ts`：图片 URL 统一解析。按优先级做字段兼容（`cover_image_url` → 13 个别名字段 → `images[].file_url` → `scene_images`），递归取第一个可用值；协议白名单（http/https/blob、`//` 协议相对、`data:image/*` 放行，`javascript:` 等判死）。修的是「有产品图但没设 `is_cover`」的产品 `cover_image_url` 为 `null`、前端没有回退字段、直接渲染占位块（表现为卡片不显示图片）的问题。`Product.cover_image`（`backend/app/models/product.py:138`）只在某张图显式 `is_cover=True` 时才返回，而 `is_cover` 仅由媒体导入流程写入，所以产品完全有图也可能取不到主图。**后端 `is_cover` 语义本轮未改**——那会影响详情页/分享页/报价等多个接口，超出本次范围；产品完全没有图片时（`images` 为空）仍是数据问题，只能显示统一占位块。
- 新增 `utils/markdown.ts`：无第三方依赖的 Markdown → 安全 HTML 渲染器，自写块级（标题/分隔线/代码块/引用/有序无序列表含嵌套/表格含对齐/段落软换行）与行内（粗体/斜体/删除线/行内代码/链接）解析。**安全模型**是不在输入上预转义，而是在输出时对每段文本 `escapeHtml`，最终 HTML 里出现的标签全部由本文件生成；链接走协议白名单；答案里的 `<img>` / `<script>` 被当纯文本转义，无注入面。
- `citations.ts` 新增 `answerSource()` / `citationInfoOf()`，并把角标折成私有区占位符（markdown 语法字符里没有这两个码位，解析不会动它），由 `markdown.ts` 在行内阶段还原为 `<button class="citation" data-source>`。复制答案、答案容器样式、`.citation` / `.citation--unresolved` 样式全部保留。
- `main.css`：叠卡卡位/固定高度/overflow、`.md-*` 排版（行高 1.85、标题/段落/列表间距、`.md-table-scroll` 横向滚动、`.md-pre` 代码块与等宽字体）、占位与骨架卡。同时删除 `.product-grid` 死规则。
- `AppHeader.vue`：新增 `showSubLabel` 属性，查询工作台（chat）把左上角让位给右上角的「进入后台 / 退出」两个文字入口，登录页和分享页保持默认 `true` 不动「门户」字样。
- 新增 `tests/e2e/deck-markdown.spec.ts`：15 条验收用例。

### 后台与门户：深色模式重构

#### 根因

1. **颜色没有按语义角色分层**：视图里到处是硬编码（`rgba(30, 50, 90, α)`、`#fff`、`#5E6470`、`#f0f0f0`，合计约 600 处），深色模式只能靠每个视图再写一遍反色值。
2. **页面级「本地别名块」遮蔽全局变量**：`Products` / `ProductDetail` / `Manuals` / `Proposals` / `ProposalDetail` / `Quotations` / `ProposalItemEditor` 在 `.xxx-page` 上自定义了 `--glass-bg: rgba(255,255,255,.72)` 等别名，`:root` 的 Token 改了也会被它们盖掉。
3. **Element Plus 只换了 `--el-color-primary`**：下拉面板、弹窗、日期选择器、表格、消息提示的背景走 `--el-bg-color-overlay` / `--el-fill-color-blank` 等一整套变量，没换就还是白底。
4. **「实底 + 反白」控件没有独立的文字色 Token**：深色下主色变浅后出现白底白字（分页选中、视图切换选中、头像、实底按钮）。

#### 主题 Token（后台 design-system.css）

浅色值原样搬进 `:root`（视觉零变化，已用计算样式逐项比对旧部署验证 0 差异），深色挂在 `html.dark-mode`：

- 表面：`--pim-page #171e22` / `--pim-header` `--pim-sidebar` `--pim-surface-soft #202a2e` / `--pim-surface #283439` / `--pim-overlay` `--pim-field` / `--pim-media-bg`
- 文字：`--pim-text-primary #edf1ee` / `--pim-text-secondary #b9c8c2` / `--pim-text-soft` / `--pim-text-faint` / `--pim-text-disabled`
- 描边：`--pim-border` `--pim-surface-border` `--pim-line` `--pim-line-strong` `--pim-control-border #3e5052` 起
- 强调：`--pim-accent-solid #a4c8b4` + `--pim-on-accent #171e22`（松绿实底配深墨字），木色 `--pim-accent #d5bca4`，峡湾蓝 `--pim-fjord #a9c8dc` 与 `--pim-focus-ring`
- 状态：`--pim-success` / `--pim-warning` / `--pim-danger` / `--pim-info` 各自带 `-bg` / `-border` 档
- `--pim-brand` triplet 约定只经 `rgba(var(--pim-brand), α)` 使用：浅色是海军蓝淡色，深色自动变成近白淡色，约 200 处 tint（文字/描边/浅填充）一份代码两种主题

Element Plus 深色变量（`--el-bg-color` / `--el-bg-color-overlay` / `--el-fill-color-*` / `--el-text-color-*` / `--el-border-color*` / `--el-tag-*` / `--el-mask-color` / `--el-overlay-color-lighter` 等）在 `.dark-mode` 内成套赋值，下拉、弹窗、抽屉、日期面板、消息提示、加载遮罩随之全部变深；`effect="dark"` 的实底标签文字换成 `--pim-on-accent`（原反白只有 2.2:1）。

#### 门户（portal）深色模式

`portal/src/styles/main.css` 原本就是全 Token 化，新增 `.dark-mode` 语义块（页面 `#171e22` / 卡片 `#283439` / 一级容器 `#202a2e` / 文字 `#edf1ee`·`#b9c8c2` / 松绿 `#a4c8b4` / 峡湾蓝 `#a9c8dc` / 木质 `#d5bca4`）；实底按钮与选中胶囊的文字切到 `--on-ink` / `--on-pine`。新增 `utils/theme.ts`：与后台同源共用 `localStorage['theme']`，监听系统偏好变化与 `storage` 事件——后台切主题时，被 iframe 嵌入 AI 选品页的门户文档同步换肤。`AppHeader.vue` 右侧新增主题开关，并按主题切换彩色/白色两版 Logo。

#### 主题状态

- 新增 `frontend/src/composables/useTheme.ts`：`light / dark / system` 三态，`initTheme()` 在 `main.ts` 挂载 Vue **之前**落 `<html>` 类，登录页、分享页等没有 ThemeToggle 的界面首帧就是正确主题，不再先闪一帧浅色；`system` 下注册 `matchMedia` 监听，系统主题变化实时响应。
- `ThemeToggle.vue` 改用该单例；持久化键仍为 `localStorage['theme']`。

#### 迁移方式（29 个视图/组件/布局）

脚本化替换 + 人工语义修正：删除全部 `:global(.dark-mode)` 覆盖规则；`rgba(30,50,90,α)` → `rgba(var(--pim-brand),α)`；`#5E6470`/`#f0f0f0`/状态色/图片控件色按语义映射；本地别名块改指向全局 Token；「实底+反白」控件（分页选中、视图切换、头像、场景图角标、账户强按钮）改用 `--pim-accent-solid` + `--pim-on-accent`；产品缩略图/灯箱控制钮走 `--pim-media-bg` / `--pim-media-control-*`，图片本身不反色。分享结果弹窗的二维码保留浅底深码，外面加一圈白 tile 承托（扫描兼容性优先）。

#### 验收

Playwright 无头浏览器实测（桌面 1440×900 + 移动 390×844）：后台 18 个页面 + 产品详情 + 登录页 + 新增产品弹窗 + 品牌下拉 + 账户弹窗 + 分页 + 门户登录/chat/分享页，浅色与深色双主题截图；计算样式 WCAG 对比度审计 0 项低于 AA（正文 ≥4.5:1，大字 ≥3:1）；控制台无报错；重开页面无主题闪烁（`initTheme` 挂载前落类）；浅色模式与旧部署逐项计算样式比对 0 差异。已知限制：本机 AI 密钥不可用，chat 真实回答的 Markdown 用同构 DOM 注入验证（`.md-*` 全部通过）；`#93a69f` 及更弱文字在 `#2f3d42` 抬升面上为 4.4:1，仅出现在极少数组合。

### 运维脚本

- 新增 `scripts/start_local_stack.sh`：非 Docker 的本机一键启动/停止/重启/查询，拓扑为 nginx `:888`（门户 `/`、后台 `/admin/`、`/api` 反代 `127.0.0.1:8000`）+ backend `:8000` + 本机原生 PG18 `:5433` + redis `:6379` + minio `:9100`。脚本里的 MinIO 与数据库口令是它为本机栈自设的默认值，**不是生产凭据**（生产 MinIO 凭据只存在于 `.env`，未进仓库；生产实跑的是 `minioadmin` / `minioadmin123`）。
- 新增 `scripts/reembed_missing.py`：为缺失 embedding 的知识块补算。
- `scripts/windows_demo_ports.ps1`：`3001` 的默认目标端口由 `5173` 改为 `888`，公网入口直接落生产 nginx，不再经过演示服务器。

### 文档

- 新增 `docs/9-17新增数据仪表盘需求实现计划.md`。
- `README.md`「管理后台入口」一栏同步为生产 nginx，去掉已废弃的演示服务器端口。

**本轮验证**：`scripts/build_frontends.sh` 构建通过（`vue-tsc --noEmit` 0 error；admin `✓ built in 6.43s`、portal `✓ built in 1.19s`）；按本文件顶部清单重建 nginx 镜像与容器后，`:888` 六个入口（`/` `/chat` `/admin` `/admin/` `/share/` `/api/v1/health`）全部 200，容器内 8 个 portal 资产与宿主机构建产物 **md5 逐一一致**，真实浏览器渲染无白屏、无控制台报错；`scripts/secret_scan.sh` 0 hits。门户 e2e（含新增 15 条）在桌面 + 移动两个项目下全绿。

**已知缺口（本轮未修）**

- 后端 `/api/v1/health` 在本机报 `"version":"dev"`：`docker-compose.yml` 把 `APP_VERSION` 默认成 `dev`，压不到第 3 处的兜底值。要让版本页说真话，需按 `README-OPS.md`「升级发布 runbook」导出 `APP_VERSION` / `BUILD_ID` / `GIT_COMMIT` / `BUILD_TIME` 后重建 backend。
- 本轮未跑后端全量 `pytest` 与后台 `playwright test`（前端已跑 `vue-tsc --noEmit` + 构建 + 门户 e2e）。合并前应补跑 `版本控制规范和Git.md` §7 发布门禁。
- 门户窄屏（≤1024px）仍是横向 scroll-snap 卡片带而非扇形，为满足「移动端避免卡片溢出屏幕」的既有设计决策。

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
