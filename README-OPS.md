# AI-PIM RiChangPIM 运维交接

本文档是 RiChangPIM 的运维版 README，重点记录启动、健康检查、备份、恢复、TLS、发布门禁和常见排障路径。它面向值班、交接和故障恢复，不重复产品需求和业务说明。

## 目录

- [环境与前提](#环境与前提)
- [服务拓扑](#服务拓扑)
- [启动方式](#启动方式)
- [健康检查](#健康检查)
- [备份](#备份)
- [恢复](#恢复)
- [TLS 与公网入口](#tls-与公网入口)
- [发布门禁](#发布门禁)
- [排障](#排障)
- [常用文件](#常用文件)

## 环境与前提

- 仓库根目录：`RiChangPIM/`
- 依赖服务通过 Docker Compose 管理
- 后端默认监听 `8000`
- 前端开发默认监听 `5173`
- 生产环境由 `nginx` 对外提供 `80/443`
- 备份目录：`./backups`
- 本地日志目录：`./logs`

## 服务拓扑

### 开发环境

- `docker-compose.dev.yml`：PostgreSQL、Redis、MinIO、Gotenberg
- 本地后端：`backend/` 下的 FastAPI 进程
- 本地前端：`frontend/` 下的 Vite 进程

### 生产环境

- `nginx`：对外入口，挂载 `frontend/dist`
- `backend`：FastAPI API 服务
- `postgres`：PostgreSQL 16 + pgvector
- `redis`：缓存
- `minio`：对象存储
- `gotenberg`：文档转换
- `ocr`：OCR 容器

## 启动方式

### 开发环境

```bash
docker compose -f docker-compose.dev.yml up -d
```

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

```bash
cd frontend
npm install
npm run dev
```

### 生产环境

```bash
cp .env.example .env
# 编辑 .env，确认 POSTGRES_PASSWORD / MINIO_ROOT_* / JWT_SECRET / ADMIN_PASSWORD 已设置

cd frontend
npm install
npm run build
cd ..

./scripts/generate_dev_tls.sh
docker compose up -d
```

生产容器启动后会自动执行：

`等待 PostgreSQL 就绪 -> alembic upgrade head -> 初始化管理员 -> 种子数据 -> 启动 uvicorn`

## 健康检查

### 后端健康检查

```bash
./scripts/healthcheck.sh
```

默认检查 `http://localhost:8000/api/v1/health`，可通过环境变量覆盖：

```bash
PORT=8000 HEALTH_URL=http://localhost:8000/api/v1/health ./scripts/healthcheck.sh
```

### Docker 检查

```bash
docker compose ps
docker compose logs --tail=200 backend
docker compose config --quiet
```

## 备份

### 一体化备份

```bash
./scripts/backup.sh
```

这个脚本会用同一个 `batch_id` 生成 PostgreSQL 和 MinIO 两部分备份，并写入 `./backups/last_status.json`。

### 数据库备份

```bash
POSTGRES_HOST=localhost POSTGRES_PASSWORD=<password> ./scripts/db_backup.sh
```

输出位于 `./backups/<batch_id>/postgres.sqlc`。

### MinIO 备份

```bash
MINIO_ROOT_USER=<user> MINIO_ROOT_PASSWORD=<password> MINIO_ENDPOINT=http://localhost:9000 ./scripts/minio_backup.sh
```

输出位于 `./backups/<batch_id>/minio.tar.gz`。

### 备份约定

- 备份脚本默认保留最近 7 份
- 所有备份采用 fail-closed 策略，部分失败会标记为 `incomplete` 或 `failed`
- 备份目录只保存结果，不直接写业务数据

## 恢复

### PostgreSQL 恢复

```bash
POSTGRES_HOST=localhost POSTGRES_PASSWORD=<password> ./scripts/db_restore.sh backups/<batch_id>/postgres.sqlc
```

恢复脚本会执行 `pg_restore --clean --if-exists --no-owner`，请先确认目标库正确。

### MinIO 恢复

```bash
MINIO_ENDPOINT=http://localhost:9000 MINIO_ROOT_USER=<user> MINIO_ROOT_PASSWORD=<password> MINIO_BUCKET=<target-bucket> ./scripts/minio_restore.sh backups/<batch_id>/minio.tar.gz
```

MinIO 恢复仅面向明确授权的目标桶，不会删除 Docker volume。

### 恢复演练

- `scripts/restore_drill.sh`：恢复演练脚本
- `backups/`：演练产物与快照

## TLS 与公网入口

### 本地 TLS 证书

```bash
./scripts/generate_dev_tls.sh
```

默认会生成到 `docker/nginx/certs/`。

### 入口说明

- 本地开发：后端 `8000`，前端 `5173`
- 生产入口：`nginx` 暴露 `80/443`

如果你在 Windows 上通过 Tailscale Funnel 暴露端口，先确保指向的是当前真实前端端口，而不是旧的临时页面。

## 发布门禁

```bash
./scripts/release_gate.sh
```

它会执行：

- 后端 `ruff`
- 后端 `compileall`
- 后端 `pytest`
- 前端 `vue-tsc`
- 前端 `eslint`
- 前端 `vitest`
- 前端 build
- Compose 配置校验
- 迁移基线校验
- Secret scan
- 备份脚本语法检查

部分门禁在本地只会作为 optional 或提示性检查；完整 RC 仍以 CI 与真实服务回归为准。

## 排障

### 1. 后端启动失败

优先检查：

```bash
docker compose ps
docker compose logs --tail=200 backend
```

常见原因：

- `POSTGRES_PASSWORD` 不一致
- `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` 不一致
- `ADMIN_PASSWORD` 为空
- 迁移失败

### 2. 数据库连接失败

如果日志出现 `password authentication failed for user "pim"`，说明后端 `DATABASE_URL` 与 PostgreSQL 容器密码不一致。要统一 `.env`，不要只重建单个服务。

### 3. MinIO 认证失败

如果出现 `InvalidAccessKeyId`，检查后端环境变量和 MinIO 容器根账号是否一致：

- `MINIO_ROOT_USER`
- `MINIO_ROOT_PASSWORD`
- `MINIO_ACCESS_KEY`
- `MINIO_SECRET_KEY`

### 4. 登录 500

先看后端 traceback，不要先假设是密码错误。

### 5. 备份失败

先看：

```bash
cat ./backups/last_status.json
```

如果是空间不足，`scripts/backup.sh` 会提前 fail-closed。

## 常用文件

- `docker-compose.yml`：生产编排
- `docker-compose.dev.yml`：开发编排
- `scripts/backup.sh`：统一备份封装
- `scripts/db_backup.sh`：PostgreSQL 备份
- `scripts/minio_backup.sh`：MinIO 备份
- `scripts/db_restore.sh`：PostgreSQL 恢复
- `scripts/minio_restore.sh`：MinIO 恢复
- `scripts/healthcheck.sh`：健康检查
- `scripts/release_gate.sh`：发布门禁
- `scripts/generate_dev_tls.sh`：本地 TLS 生成
- `backend/README.md`：后端装后维护说明

## 备注

- 如果需要，我还可以继续补一个 `README-DEV.md`，把开发环境、测试和前端联调单独拆出来。
