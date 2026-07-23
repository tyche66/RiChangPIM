# AI-PIM RiChangPIM Release Candidate 构建日志

## 当前发布状态

- V1.1 已发布并 GO：25/25 production regression PASS，详见 `docs/v1.1-verification.md`。
- 当前阶段：V1.2 内部试点运营加固，详见 `docs/v1.2-plan.md` 与 `RELEASE_GATE.md`。
  V1.2 已落地 M1-M4 工作包，RC 阶段执行全量门禁与扩展生产回归至 35-40 项。
- 2026-07-22 完成产品详情 500、详情错误状态、版本页/版本接口、统一构建元数据、登录数据库
  凭据漂移和 Alembic 长 revision 兼容修复，详见 `docs/v1.2-verification.md`。
- 历史构建版本: MVP-RC-20260716（初次 NO-GO 的根因 host 5432 端口冲突已在 V1.1 阶段解除）。

## 构建信息

- 最近构建时间: 2026-07-22（产品详情、版本功能、登录与迁移兼容增量验证）
- 构建版本: v1.2.0（M1-M4 实施完成；RC 阶段待全量门禁后正式 GO）
- 构建环境: /home/AI-PIM/RiChangPIM
- 后端根目录: /home/AI-PIM/RiChangPIM/backend
- 前端根目录: /home/AI-PIM/RiChangPIM/frontend
- 构建产物位置: /home/AI-PIM/RiChangPIM/frontend/dist
- 最终结论: 当前进度 V1.2 RC 候选，待 RC 全量门禁通过后判定 GO。

## V1.2 阶段任务完成表（截至 2026-07-22）

| 任务 | 状态 | 说明 |
| --- | --- | --- |
| M1 基线冻结 | 完成 | docs/v1.2-plan.md 与 RELEASE_GATE.md 已落地；冻结 migration head 0009、PG16、3 个 Docker volume、AI/OCR=none 默认。 |
| M2 工程门禁 | 完成 | .github/workflows/ci.yml 升级为完整后端 pytest + compileall + ruff、前端 tsc + ESLint + Vitest + build、Compose 校验、migration upgrade、pip-audit / npm audit 阻塞门禁，artifact 上传。 |
| M3 可观测性 | 完成 | app/observability/metrics.py（零依赖 Prom 1.0）；扩展 /health/ready；新增 /api/v1/metrics 与 /api/v1/ops/status；AuditMiddleware 写指标与 5xx rolling counter；敏感模块 body 落库 [redacted]。 |
| M3 备份自动化 | 完成 | db_backup.sh / minio_backup.sh 升级批次 + manifest + SHA-256 + 原子 rename；backup.sh wrapper；systemd timer / cron 样例；restore_drill.sh 独立 PG16 / MinIO 恢复演练。 |
| M3 数据质量 | 完成 | app/services/quality.py + 三端点；Quality.vue 看板；列表支持 completeness_status + quality_flag；导出不泄露 cost_price / 敏感供应商字段；UI/导出始终显示待核价。 |
| M4 审计页面加固 | 完成 | Logs.vue 时间范围 + 状态徽章 + 空状态/错误状态 + 时间本地化；Logs.spec.ts (4) + audit.spec.ts (3)；test_audit.py 补 redact/5xx 单测。 |
| M4 性能规模 | 完成 | scripts/seed_scale.py 1x/10x/100x 合成数据生成，强制 SEED_DATABASE_URL 含 seed/test/scale/synthetic 标记；quotation confirm 真正幂等（重复不写重复审计行）。 |
| 产品详情稳定性 | 完成 | 修复 ProductImage ORM 与附件字段的 Pydantic 序列化不匹配；详情关系显式加载；新增无图/产品图/场景图/说明书/404/非法 UUID/鉴权测试。 |
| 前端详情错误状态 | 完成 | 区分 loading/not-found/forbidden/server-error/network-error/success；500 与网络错误支持原地重试。 |
| 版本可见性 | 完成 | 新增 `/api/v1/version`、`/version` 页面、导航高亮、构建指纹和 build ID/commit/version 逐级一致性判断。 |
| 构建与凭据一致性 | 完成 | Docker/Vite/后端统一构建变量；开发 Compose 读取统一 PostgreSQL/MinIO 环境变量；登录真实路径恢复 200。 |
| 0012 迁移兼容 | 完成 | 保留已发布长 revision ID，并在写入前扩展 `alembic_version.version_num` 至 VARCHAR(64)，兼容空库和现有库。 |
| RC 全量门禁 | 待执行 | 待全量 pytest（含集成）+ 浏览器 e2e + Compose 启动 + 恢复演练 + secret_scan + 35-40 项 production_regression。 |

## 阶段任务完成表（历史 MVP-RC-20260716，已废弃）

| 任务 | 状态 | 说明 |
| --- | --- | --- |
| 前端 API 与 backend OpenAPI 契约对齐 | 完成 | 共享 `frontend/src/api/index.ts` 覆盖 auth/product/master-data/proposal/quotation/share/file/stats/AI。 |
| 登录、刷新 Token、退出、401/403、路由守卫 | 完成 | Pinia auth store、刷新互斥队列、`skipAuth` 公开分享、路由权限守卫已接入。 |
| 49 项 PERMISSIONS 前端建模 | 完成 | `frontend/src/types/permissions.ts` 与 backend seed 权限一致。 |
| 产品、分类、品牌、供应商、标签、用户、角色管理 | 完成 | MVP CRUD 页面已接 API 和权限按钮。 |
| 方案、报价、分享、附件、AI、统计核心链路 | 完成 | 方案到报价到分享页面已打通；报价单 PDF 导出已接 Gotenberg 返回 `application/pdf`。 |
| H5 分享页公开访问 | 完成 | `/share/:token` public route，API 请求使用 `skipAuth`，不发送后台 JWT。 |
| 敏感字段泄漏防护 | 完成 | backend 字段过滤测试通过；前端成本/供应商敏感展示 fail-closed。 |
| 前端 TypeScript、ESLint、Vitest、Vite build | 完成 | 全部命令退出 0；npm audit 当前 0 vulnerabilities。 |
| backend 测试保持 0 failed、0 skipped | 完成 | 当前为 109 passed, 0 failed, 0 skipped；新增 PDF 导出回归测试。 |
| docker compose 全栈构建和启动验证 | 失败 | `docker compose config --quiet` 与 `docker compose build backend` 通过；`docker compose up -d postgres redis minio gotenberg backend nginx` 因本机 `127.0.0.1:5432` PostgreSQL 进程占用端口失败，postgres/backend 未启动。 |
| 阶段报告 GO/NO-GO | 完成 | 因生产 Compose 启动与 `/api` 生产访问失败，按门禁判定 NO-GO。 |

## 各 Agent 交付清单

| Agent | 文件所有权 | 交付 |
| --- | --- | --- |
| Agent A | `frontend/src/api`, `frontend/src/stores`, `frontend/src/types`, `frontend/src/router.ts`, auth tests | API envelope、auth store、JWT 解码、刷新 Token、401/403、公开分享免鉴权、49 权限模型。 |
| Agent B | compose、nginx、Docker/CI | compose 静态修复、backend `.dockerignore`、nginx HTTP 入口、CI compose validation；本次生产运行门禁暴露 host 5432 端口冲突阻塞。 |
| Agent C | 产品与基础资料页面 | 产品、详情、分类、品牌、供应商、标签、导入页面集成。 |
| Agent D | 销售、分享、AI、统计页面 | 方案、报价、分享管理、公开 H5、AI 选品、统计页面集成。 |
| Agent E | 用户、角色、权限页面 | 用户管理、角色权限管理、49 权限选择器。 |
| 主控 | backend role contract、门禁、报告 | 修复角色权限持久化和返回契约，补回归测试，执行最终门禁并更新报告。 |

## 前后端 API 契约结果

- Auth: `/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/me`, `/auth/change-password` 已对齐。
- Public share: `/api/v1/share/{token}` 已由 backend 测试确认不挂 `PermissionChecker`，前端不发送 Authorization；本次 nginx 静态路由 `http://localhost/share/test-token` 返回 200 SPA 入口，但后端公开分享 API 因 backend 未启动未能生产实测。
- Products/master data: 产品、分类、品牌、供应商、标签 CRUD 与 backend 路由一致。
- Sales: proposals/quotations/shares 使用 backend 当前路由；quotation delete 未暴露，因为 backend 无删除路由。
- Files: 仅暴露 upload/delete/download/preview，因为 backend 无 list/get 路由。
- Stats: 使用 `/stats/shares` 与 `/stats/products/hot`，移除不存在的 `/stats/overview` 假设。
- Roles: backend 修复后创建/更新/列表返回 `permission_ids` 权限代码，前端角色权限编辑可真实持久化。

## RBAC 和敏感字段核查结果

- 49 项权限来自 backend `seed_data.PERMISSIONS`，前端 `PERMISSIONS` 数量为 49。
- 路由守卫按页面 `meta.permissions` 检查，按钮按共享 `hasPermission` 检查。
- 前端按钮隐藏不作为安全边界，backend `PermissionChecker` 仍是最终防线。
- 成本价、利润、供应商等敏感字段由 backend 字段过滤测试覆盖；前端成本相关列/表单只在明确高权限角色下展示，未知角色 fail-closed。
- `UserResponse` 不返回 `password_hash`；前端未展示密码哈希、Token 或生产连接串。

## 自动化测试准确统计

### Backend

| 命令 | 结果 |
| --- | --- |
| `venv/bin/python -m compileall -q app tests` | PASS |
| `venv/bin/ruff check app tests` | PASS |
| `venv/bin/python -m pytest --collect-only -q` | 109 collected |
| `venv/bin/python -m pytest -W error::DeprecationWarning` | 109 passed, 0 failed, 0 skipped |

说明：本次 backend 测试数为 109，不是先前基线 106。差异来自新增回归覆盖，包括 Gotenberg PDF 导出和数据库探针/启动安全相关测试；本次未删除测试，完整 pytest 无 failed、无 skipped。

### Frontend

| 命令 | 结果 |
| --- | --- |
| `npm audit --json` | PASS；0 info, 0 low, 0 moderate, 0 high, 0 critical, total 0 vulnerabilities |
| `npm ci` | PASS；381 packages installed；0 vulnerabilities |
| `npx vue-tsc --noEmit` | PASS |
| `npx eslint . --ext .vue,.js,.jsx,.cjs,.mjs,.ts,.tsx` | PASS |
| `npm run test` | 3 files passed, 36 tests passed |
| `npm run build` | PASS；产物写入 `frontend/dist`；Vue/vendor/Element Plus 分包，无大 chunk warning |

## 生产构建与部署结果

| 项目 | 结果 |
| --- | --- |
| frontend production build | PASS，`frontend/dist/index.html` 与 assets 已生成。 |
| `docker compose -f docker-compose.yml config --quiet` | PASS；仅提示 `version` 字段 obsolete warning。 |
| `docker compose build backend` | PASS；生成/更新 `richangpim-backend:latest`。 |
| `docker compose up -d postgres redis minio gotenberg backend nginx` | FAIL；PostgreSQL 绑定 host `0.0.0.0:5432` 失败，原因是本机进程 `postgres` 已监听 `127.0.0.1:5432`。 |
| PostgreSQL healthy | FAIL；`richangpim-postgres-1` 状态为 `created`，未运行。 |
| Redis healthy | PASS；`richangpim-redis-1` 状态为 `running healthy`。 |
| MinIO running | PASS；`richangpim-minio-1` 状态为 `running healthy`。 |
| Gotenberg running | PASS；`richangpim-gotenberg-1` 状态为 `running`，未配置 healthcheck。 |
| backend healthy | FAIL；`richangpim-backend-1` 状态为 `created`，未运行。 |
| nginx running | PASS；`richangpim-nginx-1` 状态为 `running`。 |
| `http://localhost/api/v1/health` | FAIL；curl 10s timeout，backend 未启动导致 `/api` 代理无响应。 |
| frontend dist 通过 nginx 访问 | PASS；`curl -I http://localhost/` 返回 200，`http://localhost/share/test-token` 返回 200 SPA 入口。 |
| `/api` 代理正常 | FAIL；`/api/v1/health` 与 `/api/v1/auth/login` 均 10s timeout。 |
| 登录可用 | FAIL；backend 未启动，登录接口无法响应。 |
| 产品到方案再到分享核心链路 | FAIL；backend 未启动，无法生产实测。 |
| H5 `/share/:token` 公开访问，不依赖后台 JWT | PARTIAL；nginx SPA 路由公开返回 200，backend public share API 的生产访问未能实测。 |
| backend migrate/init_admin/seed_data/serve 顺序日志正确 | PARTIAL；`backend/docker/backend-entrypoint.sh` 静态顺序为 DB wait -> alembic -> init_admin -> seed_data -> uvicorn，因 backend 容器未启动无运行日志。 |
| migration/seed 失败时 backend fail-fast，不启动服务 | PARTIAL；entrypoint 使用 `set -euo pipefail`，关键步骤失败会非零退出；未能在生产容器中注入失败场景实测。 |

## 未解决问题

### P0

- 生产 Compose 启动失败：本机 PostgreSQL 进程占用 host `5432`，导致 `richangpim-postgres-1` 无法绑定端口，backend 依赖 postgres healthy 未启动。按强制门禁，compose 或 nginx 生产 API 访问失败必须 NO-GO。

### P1

- 已处理：`npm audit --json` 当前 0 vulnerabilities；升级 `vite`/`vitest`/`@vitest/coverage-v8`/`@vitejs/plugin-vue`/`@typescript-eslint` 后前端门禁通过。
- 已处理：Gotenberg PDF 导出已从 pending task 占位改为调用 `/forms/chromium/convert/html` 并返回真实 `application/pdf`；Gotenberg 不可用或失败返回 503/502。

### P2

- 已处理：Vite build 添加 manualChunks 拆分 `vue`、`vendor`、`element-plus`；当前构建无大 chunk warning。
- 已处理：Vitest Login.vue 单测注册内存 router plugin；当前测试无 router injection warning。
- 已确认：`docker/nginx/certs` 为空，nginx 当前 HTTP-only，只监听 80；未提交证书/key。生产 TLS 由外部终止或后续独立证书配置完成。
- `docker-compose.yml` 顶层 `version` 字段触发 Docker Compose obsolete warning，建议后续移除。

## Release Candidate 产物位置

- 前端生产产物: `/home/AI-PIM/RiChangPIM/frontend/dist`
- 后端应用源码: `/home/AI-PIM/RiChangPIM/backend/app`
- 后端镜像: `richangpim-backend:latest`
- Compose 配置: `/home/AI-PIM/RiChangPIM/docker-compose.yml`
- Nginx 配置: `/home/AI-PIM/RiChangPIM/docker/nginx/nginx.conf`

## 最终判定

NO-GO。

代码、契约、前后端自动化测试、前端生产构建和 backend 镜像构建已通过；但生产 Compose 启动在 PostgreSQL host 5432 端口绑定处失败，backend 未运行，`/api` 代理、健康检查、登录、核心业务链路、公开分享 API 和 fail-fast 运行态验证未通过。根据强制门禁，compose 或 nginx 生产访问失败时不得判定 GO。

---

## MVP-RC 最终验收复跑记录

- 复跑时间: 2026-07-16T18:10:00+08:00
- 构建版本: MVP-RC-20260716-FINAL
- 构建环境: /home/AI-PIM/RiChangPIM
- 最终结论: **GO**

### 生产 Compose 冷启动

| 服务 | 状态 |
| --- | --- |
| postgres | running healthy |
| redis | running healthy |
| minio | running healthy |
| gotenberg | running |
| backend | running healthy |
| nginx | running healthy |

### backend 启动序列

`backend-entrypoint.sh` 执行顺序确认：
1. `wait-for-it postgres:5432` — 等待数据库就绪
2. `alembic upgrade head` — 执行迁移
3. `python -m app.scripts.init_admin` — 初始化管理员
4. `python -m app.scripts.seed_data` — 注入 RBAC 种子数据
5. `uvicorn app.main:app --host 0.0.0.0 --port 8000` — 启动服务

运行日志确认 migrate → init_admin → seed_data → uvicorn 顺序正确，任意步骤失败时容器以非零状态退出（`set -euo pipefail`）。

### 运行态验证

| 检查项 | 结果 |
| --- | --- |
| frontend dist 通过 nginx 访问 | PASS，200 |
| H5 `/share/:token` 公开访问 | PASS，200 |
| `/api/v1/health` | PASS，200 |
| `/api/v1/auth/login` | PASS，返回 JWT |
| 产品 → 方案 → 报价 → 分享核心链路 | PASS |
| 报价单 PDF 导出 (Gotenberg) | PASS，`application/pdf` |
| RBAC 角色权限 CRUD | PASS |
| 49 权限持久化 + 按钮级鉴权 | PASS |

### 自动化测试基线（pre-Pilot）

| 范围 | 命令 | 结果 |
| --- | --- | --- |
| Backend compileall | `venv/bin/python -m compileall -q app tests` | PASS |
| Backend Ruff | `venv/bin/ruff check app tests` | PASS |
| Backend pytest | `venv/bin/python -m pytest -W error::DeprecationWarning` | **111 passed**, 0 failed, 0 skipped |
| Frontend install | `npm ci` | PASS，381 packages，0 vulnerabilities |
| Frontend typecheck | `npx vue-tsc --noEmit` | PASS |
| Frontend lint | `npx eslint . --ext .vue,.js,.jsx,.cjs,.mjs,.ts,.tsx` | PASS |
| Frontend test | `npm run test` | **36 passed** |
| Frontend build | `npm run build` | PASS |

### 差异说明

**docs-designed / code-not-complete**（无）：MVP-RC 范围内文档设计与代码实现已对齐，无设计文档已写但代码未完成项。

**code-complete / docs-stale**：
- `PROJECT_MANAGEMENT.md` 阶段规划中 V1 原名"效能起飞"，实际进入阶段命名为 V1-AI Pilot，文档已更新。
- `docker-compose.yml` 顶层 `version` 字段仍触发 obsolete warning，代码功能正常，文档已标注建议移除但未执行（P2 低优）。

### 最终判定

**GO**。

MVP-RC 全部门禁通过：代码、契约、前后端自动化测试（backend 111 / frontend 36）、前端生产构建、backend 镜像构建、生产 Compose 六服务冷启动、migrate/init_admin/seed_data/uvicorn 顺序、frontend/API/login/core/share/PDF/RBAC 运行态验证全部通过。端口冲突已解除，无阻塞项。MVP-RC 关闭，进入 V1-AI Pilot。

---

## V1-AI Pilot 构建记录

- 验证日期: 2026-07-16
- Alembic head: `0006_add_manual_indexing`
- 当前生产模式: `AI_ADAPTER=none`
- Pilot 判定: **NO-GO**

### 实现结果

- OpenAI-compatible Adapter 统一 `chat`、`chat_stream`、`parse_tool_calls`、`manage_session`、`embed`、`embed_one` 契约，并在 shutdown 关闭连接池。
- 下游 timeout/4xx/5xx/非法 JSON/Embedding 维度错误映射为安全 502/503/504，不返回 URL、Key、原始响应或堆栈。
- 说明书增加 pending/processing/indexed/failed、失败原因、内容 hash 和最后索引时间；chunk 采用 600 字符、80 重叠，幂等替换并校验 1536 维。
- RAG 返回 product_id/product_manual_id/chunk_id/chunk_index/chunk_text/score；无可靠来源时不调用模型并明确资料不足。
- 推荐输出经严格 Pydantic Schema 验证，解析失败返回 parse_failed/degraded 和空产品；结果强字段从当前 PostgreSQL 查询并标记 `_verified=true`、`_verified_by=business_api`。
- 方案润色仅发送允许字段，严格校验 summary/item_reasons/industry_phrases；失败不修改 proposal，成功才写 ai_polished/content/at/model。
- AIConversation、OperationLog、Redis 每用户每分钟 10 次限流、结构化 AI 日志、liveness/readiness 已实现。

### Migration

`0006_add_manual_indexing` 为 forward-only 新 migration，不修改历史 migration：

- `product_manual`: index_status/index_error/content_hash/last_indexed_at。
- `product_manual_chunk`: chunk_hash 和 `(product_manual_id, chunk_index)` 唯一约束。
- `ai_conversation`: model/token_usage/status/request_summary/response_summary。

空库升级、旧库升级和 downgrade 测试通过；现有生产 PG16 已升级到 `0006`，25 张表及产品/方案/报价/分享各 1 条基准数据保留。

### 准确测试统计

| 门禁 | 结果 |
| --- | --- |
| backend compileall | PASS |
| backend Ruff | PASS |
| backend pytest | 291 passed, 0 failed, 0 skipped, 4 warnings |
| frontend vue-tsc | PASS |
| frontend ESLint | PASS |
| frontend Vitest | 68 passed, 0 failed |
| frontend build | PASS |
| Playwright Chromium | 26 passed, 0 failed, 3 skipped |
| Playwright Mobile Chrome | 初次 25 passed, 1 failed, 3 skipped；响应式修复后失败用例 1 passed |
| docker compose config | PASS |
| backend image build | PASS |

### 运行态

- 受控 OpenAI-compatible mock（临时假 Key，仅 `/tmp`）：chat 200；Embedding 200 且 1536 维；下游 500 映射 502；1 秒 timeout 映射 504。
- AI disabled：chat 返回 503，不返回伪成功；readiness 为 ready，db/redis/minio=ok，ai=none。
- 生产恢复后 postgres/redis/minio/gotenberg/backend/nginx 全部 healthy；PG16 使用固定命名卷 `richangpim_go_postgres_pg16_data_20260716`。
- 临时 mock 容器、脚本、JWT、响应文件和假 Key 已删除；未停止或读写宿主 PostgreSQL 18 数据目录。

### 未完成与 NO-GO 原因

- 真实 PDF/DOC Parser 未接入；当前仅有 Parser Protocol 和受控测试适配器，生产路由不会把测试解析器伪装成 OCR。
- 说明书上传/关联/索引/RAG 问答前端 UI 尚未完成，对应 Playwright 3 项明确 skipped。
- 未形成上传说明书到方案润色的完整非 mock 浏览器 E2E。
- 本轮未重放历史原有 25 项生产 HTTP/RBAC/PDF 回归，仅保留 MVP-RC 已通过事实并验证容器、数据、health 与 AI 两种模式。

依据质量门禁，V1-AI Pilot 当前 **NO-GO**；MVP-RC 原 GO 结论不变。
