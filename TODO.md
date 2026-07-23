# AI-PIM RiChangPIM 开发 TODO

## 当前状态

- V1.1 已发布并 GO（详见 docs/v1.1-verification.md，25/25 production regression PASS）。
- 当前阶段: V1.2 内部试点运营加固（详见 docs/v1.2-plan.md）。
- V1.2 唯一基线: docs/v1.2-plan.md；本文件仅作为任务跟踪辅助，与 plan 冲突时以 plan 为准。
- 发布门禁: RELEASE_GATE.md。
- V1-AI Pilot 历史判定已并入 V1.1 GO 状态（见 docs/v1.1-verification.md）。

## V1.2 内部试点运营加固

工作包进度(依据 docs/v1.2-plan.md):
- [x] M1 基线冻结: 写入 docs/v1.2-plan.md + RELEASE_GATE.md，冻结 migration head 0009、PG16、3 个 Docker volume、AI/OCR=none 默认。
- [x] M2 工程门禁: .github/workflows/ci.yml 升级为完整后端 pytest + compileall + ruff、前端 vue-tsc + ESLint + Vitest + build、Compose 校验、migration upgrade、pip-audit / npm audit 是 release 阻塞门禁。本地等价命令全部通过。
- [x] M3 可观测性: 新增 app/observability/metrics.py（零依赖 Prom 1.0 文本）、扩展 /health/ready（G/OCR/volume/版本）、新增 /api/v1/metrics、/api/v1/ops/status（admin RBAC）、AuditMiddleware 写请求/5xx 指标、敏感模块 body 落库为 [redacted]。
- [x] M3 备份自动化: 重写 scripts/db_backup.sh + scripts/minio_backup.sh（批次ID / manifest.json / SHA-256 / 原子 rename / 状态文件）、新增 scripts/backup.sh wrapper、scripts/ai-pim-backup.service + .timer + .cron 调度样例、scripts/backup.env.example、scripts/restore_drill.sh（独立 PG16 + MinIO 容器，绝不挂载生产卷）。
- [x] M3 数据质量: 新增 app/services/quality.py + /products/quality-summary / /quality-list / /quality-export 端点；frontend/src/views/Quality.vue 看板；finetuned list_products 支持 completeness_status + quality_flag 过滤；UI/导出始终显示待核价，不裸 99999；不导出 cost_price 与敏感供应商字段。
- [x] M4 审计页面加固: Logs.vue 增时间范围筛选 / 状态徽章 / 时间本地化 / 加载失败与空状态 / 重置与页码回到第一页；新增 frontend/tests/components/Logs.spec.ts（4 项） + frontend/tests/e2e/audit.spec.ts（3 项：admin 可访问 & body 不进 DOM / sales / viewer 被 RBAC 拦截）；后端 test_audit.py 补敏感模块 redacted 与 5xx rolling counter 单测。
- [x] M4 性能与并发: 新增 scripts/seed_scale.py（1x = 13 / 10x = 1500 / 100x = 100,000，强制 SEED_DATABASE_URL 含 seed/test/scale/synthetic 标记，永不写生产） quotation confirm 修为真正幂等（重复 confirm 不再写 OperationLog 重复行）。
- [x] 产品详情稳定性: 修复带产品图片时 Pydantic/ORM 附件字段不匹配导致的 500，显式加载详情序列化关系并补 7 项 PostgreSQL 集成测试。
- [x] 产品详情错误状态: 前端区分 404/403/401/500/网络错误，服务器与网络错误提供原地重试。
- [x] 版本可见性: 新增 `/api/v1/version`、`/version` 导航页面、构建元数据注入和前后端一致性判断。
- [x] 部署凭据与迁移兼容: 开发 Compose 统一读取 PostgreSQL/MinIO 环境变量；修复登录数据库凭据漂移和 0012 长 revision ID。
- [ ] RC 全量门禁: 当前已本地通过后端 ruff + compileall + pytest 非集成、前端 tsc + eslint + vitest + build + compose 校验；待 RC 阶段执行完整 35-40 项生产回归、迁移升级、恢复演练、secret_scan。
- [ ] RC 扩展 production_regression: 当前 25 项，需新增 备份状态 / quality 看板 / 审计页面 / migration head / 容量检查 / 非管理员 403 到 35-40 项。

## V1-AI Pilot (历史)

- [x] OpenAI-compatible chat/stream/tool/embed 契约、统一错误映射和 adapter 关闭生命周期。
- [x] `AI_ADAPTER=none` 返回受控 503，核心 PIM/报价/分享继续运行。
- [x] 说明书状态、600/80 切片、Embedding 维度校验、幂等替换和事务失败语义。
- [x] RAG 来源追溯、无来源不足以确认、文档 Prompt Injection 边界。
- [x] 推荐严格 Schema、Business API/数据库回查、`_verified_by=business_api` 和敏感字段过滤。
- [x] 方案润色严格 Schema；失败不写 `ai_polished=true`，成功记录模型和时间。
- [x] AIConversation、OperationLog、Redis 10 次/分钟限流和 liveness/readiness。
- [x] 受控 OpenAI-compatible 运行态：chat 200、Embedding 1536 维、下游 500→502、timeout→504。
- [x] Playwright desktop: 26 passed；mobile 响应式失败修复后目标用例通过。
- [ ] 接入真实 PDF/DOC Parser（当前仅有 Protocol 和测试适配器，生产不伪装 OCR）。
- [ ] 增加产品说明书上传、关联、触发索引和 RAG 问答的完整前端 UI。
- [ ] 完成上传说明书→索引→带来源问答→推荐→方案润色的非 mock 浏览器 E2E。

## P1 后续项

- [x] 处理历史依赖漏洞；本次 `npm audit --json` 为 0 vulnerabilities。
- [x] 完成 Gotenberg PDF 导出闭环，替换当前 pending task 占位体验。
- [x] 为 AI、方案和公开分享补充组件测试及 Playwright E2E；说明书 UI E2E 仍列在 V1-AI Pilot 未完成项。
- [x] 增加操作日志列表 API 后，将 Logs 页面从统计看板扩展为审计查询。(V1.2 §5.5 已加固时间范围/状态/RBAC。)

## P2 改进项

- [x] 优化 Vite 大 chunk，添加 Rollup manualChunks 拆分 Vue、Element Plus 和 vendor。
- [x] 为 Vitest 登录组件测试补 router plugin，消除 router injection warning。
- [ ] 生产 TLS 不随仓库提交证书/key；当前 nginx HTTP-only，后续由外部终止或独立证书配置完成。
- [x] 增加 PostgreSQL 和 MinIO 备份脚本。(V1.2 §5.3 已升级为批次 + manifest + 调度 + 恢复演练。)

## 已完成任务

- [x] 后端 compileall、Ruff、pytest collection、完整 pytest 门禁通过。
- [x] 后端角色权限创建/更新/列表契约修复，并新增回归测试。
- [x] 前端共享 API/auth/RBAC/错误处理/公开分享免鉴权完成。
- [x] 前端 49 项权限模型与 backend PERMISSIONS 对齐。
- [x] 前端产品、分类、品牌、供应商、标签、导入页面完成。
- [x] 前端方案、报价、分享管理、H5 分享、AI、统计页面完成。
- [x] 前端用户、角色、权限管理页面完成。
- [x] 前端 `vue-tsc`、ESLint、Vitest、Vite build 门禁通过。
- [x] 生产前端产物生成至 `frontend/dist`。
- [x] 更新 `PROJECT_MANAGEMENT.md` 与 `BUILD_LOG.md`。
- [x] 新增 `docs/v1.2-verification.md`，记录产品详情、版本功能、构建变量、登录故障和迁移兼容修复。
