# RiChangPIM 项目管理

## 项目概览

- **项目名称**: RiChangPIM (日常PIM)
- **项目类型**: AI 驱动的企业级产品信息管理平台
- **技术栈**: Vue3 + FastAPI + PostgreSQL + Redis + MinIO
- **构建方式**: Docker Compose 容器化

## 阶段规划

### MVP-RC - 前端全链路集成 ✅ GO

**目标**: 打通"产品录入 → 方案生成 → H5 分享"核心销售链路，并完成可部署 Release Candidate 门禁。

**交付内容**:
- 用户管理、RBAC 基础权限
- 产品 CRUD、分类管理、品牌管理、供应商管理、标签管理
- 方案生成与基础明细
- H5 分享 + 二维码 + 基础访问控制

**当前结论**: GO。生产 Compose 冷启动通过，六服务 (postgres/redis/minio/gotenberg/backend/nginx) 全部健康，migrate → init_admin → seed_data → uvicorn 顺序执行正常，前端/API/登录/核心链路/分享/PDF/RBAC 全量通过。

### V1.1 - 内部试点首发 ✅ GO

- 25/25 production regression PASS（详见 docs/v1.1-verification.md）
- 13 条铭达试点产品 + 待核价占位 + OCR 解析状态 + 字段级 RBAC + 备份脚本与恢复演练
- AI/OCR 默认 fail-closed (AI_ADAPTER=none / OCR_ADAPTER=none)

### V1.2 - 内部试点运营加固 ✅ GO

- CI 与发布门禁升级（完整后端 pytest / 前端 tsc / ESLint / Vitest / build / Compose / migration upgrade / pip-audit / npm audit）
- 运维可观测性（零依赖 /metrics、扩展 /health/ready、/ops/status、5xx rolling 计数、日志脱敏）
- 备份自动化（批次 ID + manifest + SHA-256 + 原子 rename + systemd timer / cron + recover drill）
- 试点数据质量闭环（Quality.vue 看板 + quality-summary/list/export + 列表 quality_flag/completeness_status 筛选）
- 审计与运营页面加固（时间范围 / 状态徽章 / 重置与分页 / Logs.spec + audit.spec / 后端 redact+5xx 单测）
- 性能规模与并发基线（seed_scale.py 1x/10x/100x；报价 confirm 真正幂等）
- 文档与版本治理（v1.2-plan + RELEASE_GATE + TODO/PROJECT_MANAGEMENT/BUILD_LOG 更新至 V1.1 GO）
- 明确不做：多租户、ERP/CRM、完整审批引擎、向量 RAG 生产启用、Kubernetes 等

### V1.8.0 - AI 能力生产就绪 ✅ GO

**目标**: 将 AI 从验证级升级为可演示生产能力，统一演示入口。

**交付内容**:
- Knowledge Gateway 正式上线（`POST /api/v1/knowledge/query` + SSE 流式协议）
- RuleBasedPlanner 支持中文实体提取（铭达、办公桌等）+ 价格排序意图识别
- 只读产品搜索/比较/质量查询工具 + 供应商比较工具
- 混合检索（pgvector + 关键词）
- 角色级字段投射（销售/viewer 隐藏成本价等敏感字段）
- OpenAI-compatible 适配器默认启用（AI_ADAPTER=openai）
- 模型默认 `agnes-2.5-flash`，OpenRouter embedding 2048 维
- DigestConversationStore + 配额检查
- AI Portal 演示服务器（`portal/dist` 入口 + `/chat` 对话页 + `/admin/` 反向代理）
- 演示脚本增强：健康检查端点、端口冲突检测、死进程清理、Windows 888 端口转发
- docker-compose.yml AI 配置全环境变量化

**当前结论**: GO。后端 healthy，AI 状态 ok，Knowledge Gateway 全链路可用，Portal 演示页面可达。

### V2 - 企业集成

- 企微/钉钉打通
- CRM/ERP 接口对接
- 多租户隔离 (SaaS)
- 审批流引擎集成

### V3 - 全面智能

- 多模态 Agent
- AI 自动化采购
- 数据驾驶舱看板
- 全场景智能客服

## 任务分配

### 后端任务

| 任务 | 状态 | 优先级 | 负责人 |
| --- | --- | --- | --- |
| 项目骨架搭建 | ✅ 完成 | P0 | - |
| 数据库模型定义 | ✅ 完成 | P0 | - |
| 用户/权限 API | ✅ 完成 | P0 | - |
| 产品管理 API | ✅ 完成 | P0 | - |
| 方案管理 API | ✅ 完成 | P0 | - |
| 分享管理 API | ✅ 完成 | P0 | - |
| AI Service Adapter 抽象层 | ✅ 完成 | P1 | - |
| 文件上传服务 | ✅ 完成 | P1 | - |
| 数据库 Alembic 迁移 | ✅ 完成 | P1 | - |
| 单元/集成测试 | ✅ 完成 | P1 | - |
| 角色权限持久化契约 | ✅ 完成 | P0 | 主控 |

### 前端任务

| 任务 | 状态 | 优先级 | 负责人 |
| --- | --- | --- | --- |
| 项目骨架搭建 | ✅ 完成 | P0 | - |
| 登录页面 | ✅ 完成 | P0 | - |
| 主布局框架 | ✅ 完成 | P0 | - |
| 产品列表页 | ✅ 完成 | P0 | - |
| API 请求封装 | ✅ 完成 | P0 | - |
| 产品分类/品牌/供应商管理页 | ✅ 完成 | P1 | Agent C |
| 标签和导入页面 | ✅ 完成 | P1 | Agent C |
| 方案管理页 | ✅ 完成 | P1 | Agent D |
| 报价、分享、AI、统计页面 | ✅ 完成 | P1 | Agent D |
| 用户、角色、权限页面 | ✅ 完成 | P1 | Agent E |
| 分享页面 (H5) | ✅ 完成 | P1 | Agent D |
| API/auth/RBAC 共享层 | ✅ 完成 | P0 | Agent A |

### DevOps 任务

| 任务 | 状态 | 优先级 | 负责人 |
| --- | --- | --- | --- |
| Docker Compose 生产环境 | ✅ 完成 | P0 | - |
| Docker Compose 开发环境 | ✅ 完成 | P0 | - |
| Nginx 配置 | ✅ 完成 | P0 | - |
| CI/CD 流水线 | ✅ 基线完成 | P2 | Agent B |
| Docker 全栈运行态验证 | ⛔ 失败 | P0 | 需解除 host 5432 端口冲突后重跑 |

## MVP-RC 验证快照

| 范围 | 命令 | 结果 |
| --- | --- | --- |
| Backend compileall | `venv/bin/python -m compileall -q app tests` | PASS |
| Backend Ruff | `venv/bin/ruff check app tests` | PASS |
| Backend collection | `venv/bin/python -m pytest --collect-only -q` | 111 collected |
| Backend tests | `venv/bin/python -m pytest -W error::DeprecationWarning` | 111 passed, 0 failed, 0 skipped |
| Frontend install | `npm ci` | PASS，381 packages installed，0 vulnerabilities |
| Frontend typecheck | `npx vue-tsc --noEmit` | PASS |
| Frontend lint | `npx eslint . --ext .vue,.js,.jsx,.cjs,.mjs,.ts,.tsx` | PASS |
| Frontend tests | `npm run test` | 36 passed |
| Frontend build | `npm run build` | PASS，产物在 `frontend/dist` |
| Compose config | `docker compose -f docker-compose.yml config --quiet` | PASS，仅 `version` obsolete warning |
| Backend image | `docker compose build backend` | PASS，`richangpim-backend:latest` |
| Compose runtime | `docker compose up -d postgres redis minio gotenberg backend nginx` | PASS，六服务全部健康 |
| Runtime frontend | `curl -I http://localhost/` | PASS，200 |
| Runtime H5 SPA | `curl -I http://localhost/share/test-token` | PASS，200 |
| Runtime API | `curl http://localhost/api/v1/health` | PASS，200 |
| Runtime login | `curl -X POST http://localhost/api/v1/auth/login` | PASS，返回 JWT |
| Runtime core chain | 产品 → 方案 → 报价 → 分享 | PASS，全链路通过 |
| Runtime PDF | 报价单导出 | PASS，Gotenberg 返回 `application/pdf` |
| Runtime RBAC | 角色权限 CRUD + 按钮级鉴权 | PASS，49 权限持久化验证通过 |

## 开发规范

### Git 分支策略

- `main` - 生产环境稳定版本
- `develop` - 开发集成分支
- `feature/*` - 功能开发
- `fix/*` - 缺陷修复

### Commit 规范

采用 Conventional Commits:
- `feat(scope): description` - 新功能
- `fix(scope): description` - 缺陷修复
- `docs(scope): description` - 文档变更
- `refactor(scope): description` - 重构

### 代码规范

**后端 (Python)**:
- Ruff 格式化 + Lint
- 异步优先 (async/await)
- 类型注解 (TypeScript-like)

**前端 (TypeScript)**:
- ESLint + Prettier
- Vue 3 Composition API
- 组件 PascalCase 命名

## 部署清单

### 首次部署

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env

# 2. 启动服务（backend 容器自动完成 迁移 -> 初始管理员 -> 种子数据 -> 启动）
docker compose up -d

# 3. 验证
curl http://localhost/api/v1/health
```

> 数据库迁移、初始管理员、RBAC 种子数据由 `backend/docker/backend-entrypoint.sh` 在容器启动后
> **自动执行**，无需手动 `alembic upgrade head` / `init_admin`。任意步骤真实失败时容器以非零状态退出，
> 不会对外提供服务。手动 migrate/seed 仅用于故障恢复与维护（详见 `backend/README.md`）。

### 更新部署

```bash
git pull origin main
docker compose build backend
docker compose up -d backend
```

## 相关链接

- 项目文档: `/home/AI-PIM/docs/`
- API 文档: http://localhost/docs
- 前端: http://localhost
- 后端: http://localhost:8000

## 修订记录

| 日期 | 修订内容 | 修订人 |
| --- | --- | --- |
| 2026-07-14 | 项目初始化创建 | Agent |
| 2026-07-16 | MVP 前端全链路集成与 RC 门禁；因 Docker 不可用判定 NO-GO | 主控 Agent |
| 2026-07-16 | RC 最终验收复跑；Docker 可用且 backend 镜像构建通过，但 Compose 因 host 5432 端口冲突失败，维持 NO-GO | RC 最终验收 Agent |
| 2026-07-16 | RC 端口冲突解除后全量复跑；Compose 六服务健康，backend migrate/init_admin/seed_data/uvicorn 顺序通过，frontend/API/login/core/share/PDF/RBAC 全量通过，backend 111 passed / frontend 36 passed，判定 GO。MVP-RC 关闭，进入 V1-AI Pilot。 | 主控 Agent |
| 2026-07-22 | 修复带图片产品详情 500 和前端错误状态；新增版本接口、版本页面及统一构建元数据；修复 Compose 凭据漂移导致的登录 500 和 Alembic 长 revision 兼容。详见 `docs/v1.2-verification.md`。 | 主控 Agent |
| 2026-07-29 | V1.8.0 发布：Knowledge Gateway + AI Portal 正式上线；docker-compose AI 配置全环境变量化；Portal 演示服务器支持同源 /api 转发与 /admin/ 反向代理；演示脚本增强。 | 主控 Agent |
| 2026-07-30 | 门户界面三轮迭代发布：v1.8.1（界面美化，`5024c16`）、v1.8.2（界面重构 + 技术信息折叠，`669b14d`）、v1.8.5（首屏改版为扇形卡堆 + 推荐产品 + 滚动淡入，`dbce35e`，annotated tag `v1.8.5`）。v1.8.1 / v1.8.2 没有打 annotated tag，v1.8.3 / v1.8.4 从未存在。 | 主控 Agent |
| 2026-07-30 | 版本号治理：新增 `CHANGELOG.md` 作为当前版本的唯一现值来源并列出「改版本号要动哪几处」；`版本控制规范和Git.md` 补 §1.1 单一事实来源；后端兜底版本 0.1.0 → 1.8.5、门户 `package.json` 0.1.0 → 1.8.5；`/api/v1/version` 不再替前端报 `frontend_version`；README/AI-Docs/BUILD_LOG/TODO/路线图/RELEASE_GATE/HANDOFF 的旧版本号与旧迁移 head（0014 → 0017）一并纠正。 | 主控 Agent |
| 2026-07-31 | v1.9.0 发布：后台界面与交互成套改版（表格排版体系、产品列表列宽水填充算法、去竖分割线、状态标识改单文字、缩略图管线、操作日志真实用户名与北京时间、AI 选品嵌入门户 `/chat`）+ nginx `/admin/` `/share/` 路由修复 + 运维脚本（`build_frontends.sh` / `where-am-i.sh`）。annotated tag `v1.9.0`，直接发布在 `main`；迁移 head 不变（`0017_operation_log_username`）。门禁与实测数据见 `CHANGELOG.md` v1.9.0 节。 | 主控 Agent |
| 2026-08-07 | v1.9.1 发布：产品媒体批量导入、媒体库稳定分页、AI / Knowledge Gateway 增强、双语 README、API / 数据卷 / MinIO / 部署文档同步；历史方案归档至 `docs/过时/`。迁移 head 不变（`0017_operation_log_username`）。 | OpenCode |
