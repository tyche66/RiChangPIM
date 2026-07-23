# AI-PIM RiChangPIM

AI 驱动的企业级产品信息管理平台（AI-PIM）- 日常构建版本

## 快速开始

### 开发环境

```bash
# 1. 启动依赖中间件
docker compose -f docker-compose.dev.yml up -d

# 2. 后端
cd backend
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 3. 前端（新终端）
cd frontend
npm install
npm run dev
```

### 生产环境

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env 修改密码与密钥
# 必须设置强随机 ADMIN_PASSWORD；缺失时后端 fail-closed，不启动服务

# 2. 构建前端
cd frontend && npm install && npm run build && cd ..

# 3. 配置 TLS 证书。仅本地验收可生成自签名证书；生产环境必须放置受信任证书
./scripts/generate_dev_tls.sh

# 4. 启动全部服务（backend 容器会自动完成 迁移 -> 初始管理员 -> 种子数据 -> 启动）
docker compose up -d
```

> 数据库迁移、初始管理员、RBAC 种子数据由 `backend/docker/backend-entrypoint.sh` 在容器启动后
> **自动执行**，无需手动 `alembic upgrade head` / `init_admin`。任意步骤真实失败时容器以非零状态退出，
> 不会对外提供服务。手动 migrate/seed 仅用于故障恢复与维护（详见 `backend/README.md`）。

访问地址: https://localhost（开发自签名证书需要浏览器手动信任）

### V1.2 运维

- OCR 默认关闭：`OCR_ADAPTER=none`。仅在受控环境改为 `tesseract`，扫描 PDF 才会调用内部 OCR 服务。
- AI 默认关闭：`AI_ADAPTER=none`。外部 AI Key 只能通过未提交的 `.env` 或秘密管理系统注入。
- PostgreSQL 备份/恢复：`scripts/db_backup.sh`、`scripts/db_restore.sh`。
- MinIO 备份/恢复：`scripts/minio_backup.sh`、`scripts/minio_restore.sh`。
- 本地 TLS：`scripts/generate_dev_tls.sh`；生产必须使用受信任证书或外部 TLS 终止。
- 当前 migration head：`0012_product_scene_image_partial_unique`；长 revision ID 兼容说明见
  `docs/v1.2-verification.md`。

## 技术栈

| 层次 | 技术 |
| --- | --- |
| 表现层 | Vue3 + Vite + Element Plus + Pinia |
| 业务层 | FastAPI (Python) |
| 基础设施 | PostgreSQL + pgvector + Redis + MinIO |

## 项目结构

```
RiChangPIM/
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── api/v1/            # API 路由
│   │   ├── core/              # 核心配置
│   │   ├── models/            # ORM 模型
│   │   ├── schemas/           # Pydantic 模型
│   │   ├── services/          # 业务逻辑
│   │   ├── adapters/          # AI Service Adapter
│   │   └── main.py            # 应用入口
│   ├── alembic/               # 数据库迁移
│   └── Dockerfile
├── frontend/                   # Vue3 前端
│   ├── src/
│   │   ├── api/               # API 请求封装
│   │   ├── views/             # 页面视图
│   │   ├── layouts/           # 布局组件
│   │   └── router.ts          # 路由配置
│   └── package.json
├── docker/                     # Docker 配置
├── docker-compose.yml          # 生产环境
├── docker-compose.dev.yml      # 开发环境
└── .env.example               # 环境变量示例
```

## API 文档

启动后访问: http://localhost/docs

- 接口总览：`docs/04-api-overview.md`
- V1.2 近期变更与验证：`docs/v1.2-verification.md`
- 后端部署与故障排查：`backend/README.md`

## MVP 功能范围

- 用户管理、RBAC 基础权限
- 产品 CRUD、分类管理、标签管理
- 方案生成与基础明细
- H5 分享 + 二维码 + 基础访问控制

## 许可证

Proprietary
