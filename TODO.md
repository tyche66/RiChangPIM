# AI-PIM RiChangPIM 开发 TODO

## 当前状态

- MVP-RC 前端全链路集成: 已完成，判定 GO。
- 当前阶段: V1-AI Pilot（效能起飞）。
- MVP-RC 结论: GO。生产 Compose 冷启动通过，六服务 (postgres/redis/minio/gotenberg/backend/nginx) 全部健康，migrate → init_admin → seed_data → uvicorn 顺序执行正常，frontend/API/login/core/share/PDF/RBAC 全量通过。
- MVP-RC 基线计数: backend 111 passed, frontend 36 passed。
- V1-AI Pilot 当前判定: **NO-GO**。后端、前端、受控 OpenAI-compatible 协议和生产降级验证已通过；说明书上传/索引浏览器 UI、真实 PDF/DOC Parser、完整历史 25 项生产 HTTP 回归尚未完成。

## V1-AI Pilot

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
- [ ] 重放并记录原有 25 项生产 HTTP/RBAC/PDF 回归。

## P0 阻塞项

- [x] 执行 `docker compose -f docker-compose.yml config --quiet`，命令通过但提示 `version` obsolete warning。
- [x] 执行 `docker compose build backend`，backend 镜像构建通过。
- [x] 解除 host `5432` 端口冲突后重新启动 PostgreSQL、Redis、MinIO、Gotenberg、backend、nginx；六服务全部健康。
- [x] 验证 backend 容器 migrate -> init_admin -> seed_data -> serve 顺序；运行日志确认顺序正确。
- [x] 注入迁移或 seed 失败场景，验证 backend fail-fast 且不对外服务；entrypoint `set -euo pipefail` 确认。
- [x] 通过生产 nginx 验证 frontend dist、`/api` 代理、健康检查、登录、产品到方案到分享核心链路。
- [x] 验证 `/share/:token` H5 公开访问不依赖后台 JWT。

## P1 后续项

- [x] 处理历史依赖漏洞；本次 `npm audit --json` 为 0 vulnerabilities。
- [x] 完成 Gotenberg PDF 导出闭环，替换当前 pending task 占位体验。
- [x] 为 AI、方案和公开分享补充组件测试及 Playwright E2E；说明书 UI E2E 仍列在 V1-AI Pilot 未完成项。
- [ ] 增加操作日志列表 API 后，将 Logs 页面从统计看板扩展为审计查询。

## P2 改进项

- [x] 优化 Vite 大 chunk，添加 Rollup manualChunks 拆分 Vue、Element Plus 和 vendor。
- [x] 为 Vitest 登录组件测试补 router plugin，消除 router injection warning。
- [ ] 生产 TLS 不随仓库提交证书/key；当前 nginx HTTP-only，后续由外部终止或独立证书配置完成。
- [ ] 增加 PostgreSQL 和 MinIO 备份脚本。

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

## 最近验证统计

| 范围 | 命令 | 结果 |
| --- | --- | --- |
| Backend | `venv/bin/python -m compileall -q app tests` | PASS |
| Backend | `venv/bin/ruff check app tests` | PASS |
| Backend | `venv/bin/python -m pytest --collect-only -q` | 111 collected |
| Backend | `venv/bin/python -m pytest -W error::DeprecationWarning` | 111 passed, 0 failed, 0 skipped |
| Frontend | `npm ci` | PASS, 381 packages installed, 0 vulnerabilities |
| Frontend | `npx vue-tsc --noEmit` | PASS |
| Frontend | `npx eslint . --ext .vue,.js,.jsx,.cjs,.mjs,.ts,.tsx` | PASS |
| Frontend | `npm run test` | 36 passed |
| Frontend | `npm run build` | PASS |
| Compose | `docker compose -f docker-compose.yml config --quiet` | PASS, obsolete `version` warning |
| Compose | `docker compose build backend` | PASS, `richangpim-backend:latest` |
| Compose | `docker compose up -d postgres redis minio gotenberg backend nginx` | PASS, 六服务全部健康 |
| Runtime | `curl -I http://localhost/` | PASS, 200 |
| Runtime | `curl -I http://localhost/share/test-token` | PASS, 200 SPA fallback |
| Runtime | `curl http://localhost/api/v1/health` | PASS, 200 |
| Runtime | `curl -X POST http://localhost/api/v1/auth/login` | PASS, 返回 JWT |
| Runtime | 产品 → 方案 → 报价 → 分享核心链路 | PASS |
| Runtime | 报价单 PDF 导出 (Gotenberg) | PASS, `application/pdf` |
| Runtime | RBAC 角色权限 CRUD + 49 权限持久化 | PASS |
| V1 Backend | `venv/bin/python -m pytest -q` | 291 passed, 0 failed, 0 skipped, 4 warnings |
| V1 Frontend | `npm run test -- --run` | 68 passed, 0 failed |
| V1 Playwright desktop | `npx playwright test --project=chromium` | 26 passed, 0 failed, 3 skipped |
| V1 Playwright mobile | 全量后修复响应式失败并定向复跑 | 25 passed, 1 failed, 3 skipped；失败用例修复后 1 passed |
| V1 AI enabled | 受控 OpenAI-compatible mock | chat 200；embedding 200/1536；5xx→502；timeout→504 |
| V1 AI disabled | 生产 `AI_ADAPTER=none` | AI chat 503；readiness ready；核心数据保留 |
