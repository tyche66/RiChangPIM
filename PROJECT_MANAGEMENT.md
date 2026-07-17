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

### V1-AI Pilot (当前阶段) - AI 效能起飞

- AI 智能条件推荐
- 方案生成与 AI 润色
- 报价单导出 PDF
- 访问统计看板
- 字段级权限

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
