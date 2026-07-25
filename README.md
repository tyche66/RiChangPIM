# AI-PIM RiChangPIM

RiChangPIM 是当前这套 AI-PIM 项目的工作快照，面向产品信息管理、产品导入、方案/报价、媒体资源、分享页和基础 AI 能力。

这份 README 按常见项目文档结构组织，同时保留当前快照的代码索引、启动方式、数据位置和产品信息落点，便于交接、排障和复现。

## 目录

- [项目概述](#项目概述)
- [功能特性](#功能特性)
- [目录结构](#目录结构)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [数据与存储](#数据与存储)
- [产品信息索引](#产品信息索引)
- [初始化与种子](#初始化与种子)
- [测试](#测试)
- [文档](#文档)
- [许可证](#许可证)

## 项目概述

| 项目项 | 当前状态 |
| --- | --- |
| 仓库根目录 | `RiChangPIM/` |
| 后端 | `backend/`，FastAPI + SQLAlchemy + Alembic |
| 前端 | `frontend/`，Vue 3 + Vite + Element Plus + Pinia |
| 数据库 | PostgreSQL 16 + pgvector |
| 缓存 | Redis 7 |
| 对象存储 | MinIO |
| 文档转换 | Gotenberg 8 |
| OCR 服务 | `docker/ocr/` 容器内独立服务 |
| 当前迁移 head | `0012_product_scene_image_partial_unique` |
| 主要种子入口 | `backend/app/scripts/seed_data.py` + `backend/alembic/versions/0004_seed_data.py` |
| 产品试点数据文件 | `backend/data/sunon_pilot_products.json` |

## 功能特性

- 产品、分类、品牌、供应商、标签管理
- 产品导入导出与试点数据导入
- 方案、报价、分享页与权限控制
- 产品图片、场景图、说明书与媒体库管理
- 质量看板与数据完整性辅助视图
- OCR、AI 能力中心与 RAG 相关基础设施

## 目录结构

### 仓库根目录

- `README.md`：当前总览文档
- `docker-compose.yml`：生产编排
- `docker-compose.dev.yml`：开发依赖编排
- `.env.example`：根级环境变量示例
- `.env`：当前本地开发环境变量
- `scripts/`：备份、恢复、健康检查、TLS 生成、发布门禁等脚本
- `docs/`：需求、架构、数据库、接口、部署、测试等文档
- `backups/`：数据库备份与恢复演练文件
- `docker/`：Nginx、Postgres 初始化、OCR 容器等基础设施配置

### 后端代码 `backend/`

- `backend/app/main.py`：后端应用入口
- `backend/app/api/v1/`：所有 API 路由
- `backend/app/core/`：配置、数据库、权限、序列化、MinIO、速率限制等核心能力
- `backend/app/models/`：ORM 模型定义
- `backend/app/schemas/`：Pydantic 请求与响应模型
- `backend/app/services/`：业务服务层，如产品导出、RAG、OCR、质量分析、解析器等
- `backend/app/adapters/`：AI Adapter 抽象与实现
- `backend/app/middleware/`：审计等中间件
- `backend/app/scripts/`：初始化、种子、导入脚本
- `backend/alembic/`：数据库迁移
- `backend/tests/`：后端测试

### 前端代码 `frontend/`

- `frontend/src/main.ts`：前端入口
- `frontend/src/router.ts`：路由与权限控制
- `frontend/src/layouts/MainLayout.vue`：主布局
- `frontend/src/views/`：页面级视图
- `frontend/src/components/`：可复用组件
- `frontend/src/api/`：接口调用封装
- `frontend/src/stores/`：Pinia 状态管理
- `frontend/src/types/`：前端类型定义
- `frontend/src/utils/`：工具函数
- `frontend/src/config/version.ts`：前端版本展示相关配置
- `frontend/tests/`：前端测试，包括组件测试和 e2e

## 快速开始

### 1. 开发环境

本地开发建议使用 `docker-compose.dev.yml` 启动基础依赖，再分别启动后端和前端。

```bash
# 1) 启动依赖服务
docker compose -f docker-compose.dev.yml up -d

# 2) 启动后端
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 3) 启动前端
cd frontend
npm install
npm run dev
```

### 演示模式（Tailscale 公网）

如果需要把完整 PIM 演示到公网，推荐使用仓库内置的演示服务器：

```bash
# WSL / Linux 侧启动演示服务器
./scripts/start_demo.sh

# 停止演示服务器
./scripts/stop_demo.sh
```

Windows 管理员 PowerShell 侧执行端口转发：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\windows_demo_ports.ps1
```

然后在 Windows 侧启动 Funnel：

```powershell
tailscale funnel 3001
```

公网入口会落到前端，同源 `/api` 会由演示服务器转发到后端，因此产品图片、文件上传、分享页等功能都可以走完整链路。

开发环境默认端口：

- 前端：Vite 默认端口，通常为 `5173`
- 后端：`http://localhost:8000`
- API 文档：`http://localhost:8000/docs`

### 2. 生产 / 容器化环境

```bash
# 1) 配置环境变量
cp .env.example .env
# 编辑 .env，确保 ADMIN_PASSWORD、JWT_SECRET、POSTGRES_PASSWORD、MINIO_ROOT_* 都已设置

# 2) 构建前端
cd frontend
npm install
npm run build
cd ..

# 3) 生成本地 TLS 证书（仅本地验收可用，自签名证书需手动信任）
./scripts/generate_dev_tls.sh

# 4) 启动全套服务
docker compose up -d
```

生产 Compose 会在 backend 容器启动后自动执行：

`等待 PostgreSQL 就绪 -> alembic upgrade head -> 初始化管理员 -> 种子数据 -> 启动 uvicorn`

也就是说，正常部署不需要手工跑 `alembic upgrade head` 或 `python -m app.scripts.seed_data`。

## 配置说明

### 根级环境变量

- `RiChangPIM/.env`

这个文件用于当前本地开发快照，包含 PostgreSQL、JWT、MinIO、AI 等配置。

### 后端环境变量模板

- `RiChangPIM/backend/.env.example`
- `RiChangPIM/backend/.env`

后端配置读取逻辑在：

- `backend/app/core/config.py`

它会从 `backend/` 所在项目根解析 `.env`，不依赖启动时当前工作目录。

## 数据与存储

### 数据库

生产 `docker-compose.yml` 中使用的是命名卷：

- PostgreSQL：`richangpim_go_postgres_pg16_data_20260716`
- Redis：`richangpim_go_redis_data_20260716`
- MinIO：`richangpim_go_minio_data_20260716`

对应服务位置见 `docker-compose.yml`：

- `postgres`：`postgres_pg16_data:/var/lib/postgresql/data`
- `redis`：`redis_data:/data`
- `minio`：`minio_data:/data`

开发环境 `docker-compose.dev.yml` 默认使用项目目录内绑定挂载：

- `./docker/volumes/postgres_dev`
- `./docker/volumes/minio_dev`

### 备份目录

- `./backups`

生产 backend 容器会把该目录以只读方式挂载到 `/data/backups`，用于健康检查和容量状态读取。

### MinIO 对象存储

对象存储的逻辑 bucket 默认是：

- `MINIO_BUCKET=ai-pim`

实际对象 key 由上传逻辑决定，常见内容包括：

- 产品图片
- 场景图
- 说明书 / 资料附件
- 报价单相关文件

### 迁移与种子

- `backend/alembic/versions/`：数据库迁移历史
- `backend/alembic/versions/0004_seed_data.py`：RBAC 种子迁移
- `backend/app/scripts/seed_data.py`：可重复执行的种子脚本

## 产品信息索引

这一套 PIM 的“产品信息”不是只存在一个文件，而是分布在模型、接口、页面、导入脚本和数据文件中。

### 1. 产品数据模型

- `backend/app/models/product.py`
- `backend/app/schemas/product.py`

这里定义了产品的核心字段，包括：

- `product_no`
- `product_name`
- `brand_id`
- `supplier_id`
- `category_id`
- `face_price`
- `cost_price`
- `material`
- `stock_status`
- `status`
- `description`
- `specification`
- `colors`
- `data_source`
- `completeness_status`
- `tags`
- `images`
- `scene_images`

### 2. 产品 API

- `backend/app/api/v1/products.py`

这里是产品相关接口主入口，包含：

- 产品列表与详情
- 新增、编辑、删除、克隆
- 导入、导出
- 主图与场景图管理
- 质量看板与质量导出

### 3. 产品导入数据

- `backend/data/sunon_pilot_products.json`

这是当前试点产品的 JSON 数据文件，导入脚本会读取它。

- `backend/app/scripts/import_sunon_products.py`

这是试点产品导入脚本，特点是幂等、可校验、可更新已有产品。

- `backend/app/scripts/import_sunon_taxonomy.py`

这是圣奥 taxonomy 导入脚本，用于导入品类与系列标签。

### 4. 产品页面

- `frontend/src/views/Products.vue`
- `frontend/src/views/ProductDetail.vue`
- `frontend/src/views/Import.vue`
- `frontend/src/views/Manuals.vue`
- `frontend/src/views/SceneImages.vue`
- `frontend/src/views/MediaLibrary.vue`
- `frontend/src/views/Quality.vue`

### 5. 产品相关组件

- `frontend/src/components/ProductImageManager.vue`
- `frontend/src/components/ProductSceneCarousel.vue`
- `frontend/src/components/SceneImageSelector.vue`
- `frontend/src/components/MediaPicker.vue`
- `frontend/src/components/MediaUploader.vue`
- `frontend/src/components/ProposalItemEditor.vue`

### 6. 产品相关前端 API

- `frontend/src/api/index.ts`
- `frontend/src/api/media.ts`

### 7. 产品权限

- `frontend/src/types/permissions.ts`
- `backend/app/core/permissions.py`
- `backend/app/core/permission.py`
- `backend/app/scripts/seed_data.py`
- `docs/seed-data.md`

## 初始化与种子

### 数据库迁移

```bash
cd backend
alembic upgrade head
```

### 初始化管理员

```bash
cd backend
python -m app.scripts.init_admin
```

### RBAC 种子数据

```bash
cd backend
python -m app.scripts.seed_data
python -m app.scripts.seed_data --check
```

### 产品试点导入

```bash
cd backend
python -m app.scripts.import_sunon_products data/sunon_pilot_products.json
```

如只想校验输入，不写入数据库，可追加 `--check`。

## 测试

### 后端测试

```bash
cd backend
pytest
```

### 前端测试

```bash
cd frontend
npm run test
```

### 端到端与检查

- `frontend/tests/e2e/`：前端端到端测试
- `scripts/healthcheck.sh`：服务健康检查
- `scripts/release_gate.sh`：发布门禁检查

## 文档

- `docs/00-项目概述.md`
- `docs/01-产品需求(PRD).md`
- `docs/02-系统架构与设计(HLD).md`
- `docs/03-数据库设计(ERD).md`
- `docs/04-接口规范(OpenAPI).md`
- `docs/05-业务流程(BPM).md`
- `docs/06-部署方案.md`
- `docs/07-开发规范.md`
- `docs/08-开发路线图.md`
- `docs/09-测试计划.md`
- `docs/seed-data.md`
- `docs/v1.0.1-交接文档.md`
- `docs/v1.0.2-交接文档.md`

## 运行约定

- `OCR_ADAPTER=none` 时，OCR 默认关闭
- `AI_ADAPTER=none` 时，AI 默认关闭
- `ADMIN_PASSWORD` 不能为空，否则后端会 fail-closed，不启动服务
- 生产环境应优先使用环境变量注入，不要依赖提交到仓库的 `.env`
- 产品编号在未删除数据上要求唯一，相关约束见 `backend/app/models/product.py`

## 许可证

Proprietary
