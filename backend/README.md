# AI-PIM 后端部署与运维

FastAPI 后端（AI-PIM / RiChangPIM）。本文档聚焦「装后」必备步骤：数据库迁移、初始管理员、RBAC 种子数据。

## 1. 安装依赖

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 2. 环境变量

基于仓库根 `.env.example` 准备 `.env`（或导出环境变量），至少包含：

- `DATABASE_URL`（如 `postgresql://pim:pim_password@localhost:5432/ai_pim`）
- `JWT_SECRET`、`MINIO_*`、`REDIS_URL` 等（详见 `.env.example`）

## 3. 数据库迁移（必须）

```bash
# 执行全部迁移（含 0001 建表 / 0002 RAG / 0003 报价小计 / 0004 种子数据）
alembic upgrade head
```

- 升级：`alembic upgrade head`
- 回滚到上一版本：`alembic downgrade -1`
- 回滚全部：`alembic downgrade base`（会清掉所有表，仅用于全新环境）

`0004_seed_data` 为**数据迁移**，幂等：重复执行不会重复插入角色/权限/映射。

## 4. 初始管理员

```bash
python -m app.scripts.init_admin
```

默认创建：用户名 `admin` / 密码 `admin123` / 角色 `系统管理员`。已存在则跳过。

## 5. RBAC 种子数据

```bash
# 角色 / 权限 / 角色-权限映射 + admin 用户（幂等）
python -m app.scripts.seed_data

# 仅校验缺失项，不写入
python -m app.scripts.seed_data --check

# 仅写入角色/权限/映射，不创建 admin 用户
python -m app.scripts.seed_data --no-admin
```

种子内容（4 角色 / 多模块权限 / 角色-权限映射）见 `docs/seed-data.md`，与
`alembic/versions/0004_seed_data.py` 保持一致。

## 6. Docker 一键部署

`docker/backend-entrypoint.sh` 在容器启动后**自动**完成：

```
等待 PostgreSQL 就绪 -> alembic upgrade head -> 初始管理员 -> 种子数据 -> 启动 uvicorn
```

任意必要步骤**真实失败**时（DB 不可达、迁移失败、种子异常），容器以**非零状态退出**，
绝不会以“看似成功”的状态对外提供服务。各步骤均幂等，重复 `docker compose up` 安全。

```bash
# 默认即自动完成 migrate/seed，无需手动执行
docker compose up -d
```

### 手动 migrate / seed（仅故障恢复与维护）

正常部署**不需要**手动执行。仅在以下场景使用：

- 迁移中断需补跑；
- 需要从特定版本回滚；
- 数据修复 / 重新种子。

手动执行须让 Alembic 指向容器内 `postgres` 主机（仓库 `alembic.ini` 写死了 `localhost`，
entrypoint 已用临时 ini 自动处理；手动执行请复用同一手法）：

```bash
# 进入容器
docker compose exec backend bash

# 容器内生成临时 ini 并迁移（务必用 postgres 主机名）
sed "s#^sqlalchemy.url = .*#sqlalchemy.url = postgresql://pim:${POSTGRES_PASSWORD:-pim_password}@postgres:5432/ai_pim#" alembic.ini > /tmp/alembic.ini
alembic -c /tmp/alembic.ini upgrade head

# 初始化管理员 / 种子数据（幂等，已存在则跳过）
python -m app.scripts.init_admin
python -m app.scripts.seed_data
```

> 单行等价写法：
> ```bash
> docker compose exec backend bash -c \
>   'sed "s#^sqlalchemy.url = .*#sqlalchemy.url = postgresql://pim:${POSTGRES_PASSWORD:-pim_password}@postgres:5432/ai_pim#" alembic.ini > /tmp/alembic.ini \
>    && alembic -c /tmp/alembic.ini upgrade head'
> ```

## 7. 运维脚本

> ⚠️ 以下脚本位于**仓库根目录 `scripts/`**，依赖 PostgreSQL 客户端（`pg_dump` / `pg_restore`），
> **不在后端 Python 镜像内**，也不可在 backend 容器内直接运行。

| 脚本（仓库根目录） | 用途 |
| --- | --- |
| `scripts/db_backup.sh` | `pg_dump` 全量备份（带时间戳，保留最近 7 份） |
| `scripts/db_restore.sh <file>` | `pg_restore` 恢复 |
| `scripts/healthcheck.sh` | 探测 `/api/v1/health` 判定服务健康 |

备份/恢复依赖 `pg_dump`/`pg_restore`，两种运行方式：

1. **宿主机直接运行**（宿主机已装 PostgreSQL 客户端，端口映射到 localhost）：
   ```bash
   POSTGRES_HOST=localhost ./scripts/db_backup.sh
   POSTGRES_HOST=localhost ./scripts/db_restore.sh backups/ai_pim_xxx.sqlc
   ```
2. **经 `docker compose exec postgres` 运行**（postgres 镜像自带客户端，无需宿主机安装）：
   ```bash
   docker compose exec -T postgres pg_dump -U pim -d ai_pim -Fc > backups/ai_pim_$(date +%Y%m%d_%H%M%S).sqlc
   docker compose exec -T postgres pg_restore -U pim -d ai_pim --clean --if-exists --no-owner -f - < backups/ai_pim_xxx.sqlc
   ```

## 8. 本地启动

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# API 文档: http://localhost:8000/docs
```
