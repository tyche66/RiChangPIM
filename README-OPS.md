# AI-PIM RiChangPIM 运维交接

本文档是 RiChangPIM 的运维版 README，重点记录启动、健康检查、备份、恢复、TLS、发布门禁和常见排障路径。它面向值班、交接和故障恢复，不重复产品需求和业务说明。

## 目录

- [这台机器的实机真相（先看这个）](#这台机器的实机真相先看这个)
- [环境与前提](#环境与前提)
- [服务拓扑](#服务拓扑)
- [启动方式](#启动方式)
- [升级发布 runbook](#升级发布-runbook)
- [健康检查](#健康检查)
- [备份](#备份)
- [恢复](#恢复)
- [TLS 与公网入口](#tls-与公网入口)
- [发布门禁](#发布门禁)
- [排障](#排障)
- [已知缺口](#已知缺口)
- [常用文件](#常用文件)

## 这台机器的实机真相（先看这个）

本节是 2026-07-31 在实机（Windows 11 + Docker Desktop + WSL 发行版 `RiChangPIM`）实测的状态。
下面几节的通用说明与本节冲突时，**以本节为准**。完整的启动/穿透流程见 `/home/AI-PIM/从启动到穿透.md`。

开工第一条命令：

```bash
cd /home/AI-PIM/RiChangPIM && bash scripts/where-am-i.sh
```

| | 生产 | 本地开发 | 集成测试 |
| --- | --- | --- | --- |
| 承载 | Docker Desktop 的 compose 栈（7 服务） | 本机 uvicorn / vite | 本机原生 PostgreSQL 18 |
| 数据位置 | 命名卷 `richangpim_go_postgres_pg16_data_20260716` | 取决于 `DATABASE_URL` | 原生 PG18 集群 |
| 库名 | `ai_pim` | `ai_pim` | `ai_pim_test` |
| 宿主机能否直连库 | **不能**，5432 未发布，只能 `docker exec` | localhost:5432 | localhost:5432 |
| 平时状态 | 常驻 | 按需 | **必须 down** |
| 真实数据 | **只有这一套** | 否 | 否 |

- 对外入口只有 **`http://127.0.0.1:888/`**（nginx `888:80`）：`/` 门户、`/share/<token>` 分享页、
  `/admin/` 管理后台、`/api/v1/*`。
- backend 的 `8000:8000` **实际没绑上**——Windows 有系统进程占着 `0.0.0.0:8000`。别在 8000 上找后端。
- postgres / redis / minio / gotenberg / ocr **都没有发布端口**，只在 compose 网络内可达。
- `frontend/dist`、`portal/dist` 是 **`COPY` 进 nginx 镜像**的，不是 bind mount。
  只在宿主机 `npm run build` **不会改变 `:888` 上的任何东西**（要 `docker compose build nginx`）。
- `:888/admin/` 从 2026-07-31 起可用（后台改按 `base '/admin/'` 构建 + `default.conf` 加了
  `location = /admin` 的 301 和 `absolute_redirect off`）。演示服务器的 `:5173/admin/` 仍然并存，
  公网隧道走的是它。
- **本机原生 PG18 里不允许存在名为 `ai_pim` 的库。** 它和生产库同名但是空的，
  任何后端误指到 `localhost:5432/ai_pim` 都会看到一套「所有密码都错」的假数据
  （2026-07-31 已发生过一次，空库已 dump 后删除）。

## 环境与前提

- 仓库根目录：`RiChangPIM/`（实机路径 `/home/AI-PIM/RiChangPIM`，在 WSL 发行版 `RiChangPIM` 里）
- 依赖服务通过 Docker Compose 管理
- 后端容器内监听 `8000`；**宿主机上只能通过 nginx `888` 访问**
- 前端开发默认监听 `5173`（Admin）/ `5174`（Portal）
- 生产 nginx 宿主机端口 `888` → 容器 `80`
- 备份目录：`./backups`
- 本地日志目录：`./logs`
- Node 由 nvm 装，不在默认 PATH：`export PATH="$HOME/.nvm/versions/node/v24.18.0/bin:$PATH"`
- distro 里用 docker CLI 需要指定 socket，否则会 panic：
  `export DOCKER_HOST=unix:///mnt/wsl/docker-desktop/shared-sockets/host-services/docker.proxy.sock`
- compose 命令必须在 distro 内、从仓库根执行（项目身份带 `working_dir` label，且有相对 bind mount）

## 服务拓扑

### 开发环境

- `docker-compose.dev.yml`：PostgreSQL、Redis、MinIO、Gotenberg
- 本地后端：`backend/` 下的 FastAPI 进程
- 本地前端：`frontend/` 下的 Vite 进程

### 生产环境

- `nginx`：对外入口，宿主机 `888` → 容器 `80`；**`frontend/dist` 与 `portal/dist` 在 build 时 `COPY` 进镜像**
- `backend`：FastAPI API 服务（`8000:8000` 在本机没能绑上，见上文）
- `postgres`：PostgreSQL 16 + pgvector（未发布端口）
- `redis`：缓存（未发布端口）
- `minio`：对象存储（未发布端口）
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

> ⚠️ 起本地后端前先确认 `DATABASE_URL` 指向哪里。**绝不要指到 `localhost:5432/ai_pim`**，
> 那不是生产库；生产库只能从 compose 网络内以主机名 `postgres` 访问。

### 生产环境

```bash
cp .env.example .env
# 编辑 .env，确认 POSTGRES_PASSWORD / MINIO_ROOT_* / JWT_SECRET / ADMIN_PASSWORD 已设置

export PATH="$HOME/.nvm/versions/node/v24.18.0/bin:$PATH"
bash scripts/build_frontends.sh    # 不要直接 npm run build，见下

./scripts/generate_dev_tls.sh
docker compose up -d
```

**为什么必须用 `scripts/build_frontends.sh`**：它在两个前端 build 之外还做两件缺一不可的事——
注入真实版本元数据（`VITE_APP_VERSION` / `BUILD_ID` / `GIT_COMMIT` / `BUILD_TIME`，否则「版本」页显示假值），
以及 `export VITE_BASE_PATH=/admin/`（后台必须按这个 base 构建：裸 `npm run build` 出来的 index.html
引用 `/assets/...`，这个请求在 nginx 上会落到 `location /` → 门户目录 → 后台 JS/CSS 全 404 → 白屏。
2026-07-31 实测过：`GET :888/assets/index-CY12cIKj.js` 404，而文件就在容器的
`/usr/share/nginx/admin/assets/` 里）。

原先这里还有一步「把 `frontend/dist/assets` 合并进 `portal/dist/assets`」（`merge_admin_static`），
那是后台按 `base '/'` 构建时代的补丁，分享页迁到门户后已删除，**别再加回来**。

**改完前端或 nginx 配置必须重建镜像**（dist 是 `COPY` 进去的，不是挂载）：

```bash
bash scripts/build_frontends.sh && docker compose build nginx && docker compose up -d --no-deps nginx
```

后端同理（没有源码挂载）：`docker compose build backend && docker compose up -d --no-deps backend`。

生产容器启动后会自动执行：

`等待 PostgreSQL 就绪 -> alembic upgrade head -> 初始化管理员 -> 种子数据 -> 启动 uvicorn`

其中「初始化管理员」会**用 `.env` 的 `ADMIN_PASSWORD` 重算 hash 覆盖数据库里的 admin 口令**，
每次 backend 容器启动都会做。所以在界面上改的 admin 密码会在下次重启后被 `.env` 的值盖回去。

### 管理后台入口（演示服务器）

两个入口并存，都可用：`:888/admin/`（生产 nginx）和 `:5173/admin/`（演示服务器，公网隧道落在它上面）。
演示服务器端口固定 **5173**（`windows_demo_ports.ps1` 的默认值、Funnel `3001` 已指向它，不要再换）：

```bash
export PATH="$HOME/.nvm/versions/node/v24.18.0/bin:$PATH"
PIM_DEMO_PORT=5173 PIM_DEMO_BACKEND=http://127.0.0.1:888 bash scripts/start_demo.sh
```

`PIM_DEMO_BACKEND` 必须指向 `:888`；默认值 `:8000` 在本机是死的，会得到一个空壳——
页面能开但**登录一直转圈不返回**。起完顺手确认一眼：

```bash
curl -s --noproxy '*' http://127.0.0.1:5173/__demo/health   # backendTarget 必须是 http://127.0.0.1:888
```

停止用 `PIM_DEMO_PORT=5173 bash scripts/stop_demo.sh`（按端口停，不会误杀其他实例）。

## 升级发布 runbook

顺序固定：**备份 → 构建 → 重建容器 → 确认迁移 → 验收**。

```bash
cd /home/AI-PIM/RiChangPIM
export PATH="$HOME/.nvm/versions/node/v24.18.0/bin:$PATH"
export DOCKER_HOST=unix:///mnt/wsl/docker-desktop/shared-sockets/host-services/docker.proxy.sock

# 1) 备份（迁移不可逆，这一步不能省）
TS=$(date +%Y%m%dT%H%M%S)
docker exec richangpim-postgres-1 pg_dump -U pim -d ai_pim -Fc -f /tmp/d.sqlc \
  && docker cp richangpim-postgres-1:/tmp/d.sqlc "backups/pre_upgrade_${TS}.sqlc" \
  && docker exec richangpim-postgres-1 rm -f /tmp/d.sqlc

# 2) 构建前端产物（含版本注入与 base '/admin/'），并记下它注入的那一套值
bash scripts/build_frontends.sh          # 输出里有 APP_VERSION / BUILD_ID / GIT_COMMIT / BUILD_TIME

# 3) 把同一套版本值导出给 backend（否则 compose 默认值会让后端自报 dev，见下）
export APP_VERSION=1.9.0                 # = frontend/package.json 的 version
export BUILD_ID=local-20260731T101832Z   # 抄第 2 步输出，必须和前端产物里的一致
export GIT_COMMIT=dbce35e-dirty
export BUILD_TIME=2026-07-31T10:18:32Z
export APP_ENV=production

# 4) 重建镜像并只替换需要的服务
docker compose build backend nginx
docker compose up -d --no-deps backend nginx

# 5) 确认迁移已到 head（entrypoint 自动跑，这里只是核对）
docker exec richangpim-backend-1 alembic current

# 6) 验收
bash scripts/where-am-i.sh
curl -s --noproxy '*' http://127.0.0.1:888/api/v1/health   # version 必须是真版本号，不是 dev
```

只改前端时第 4 步可以只做 `nginx`；只改后端时只做 `backend`。
**不要**用 `docker compose up -d` 不带 `--no-deps` 去重建单个服务，那会顺带重启依赖服务。

第 3 步不能省。`docker-compose.yml` 把 `APP_VERSION` / `BUILD_ID` / `GIT_COMMIT` / `BUILD_TIME`
同时当作 build args 和运行时 env，两处默认值都是 `dev` / `dev-local` / `unknown`。
不导出就重建 backend，`/api/v1/health` 和 `/api/v1/version` 会自报 `dev`，
后台「版本」页按 `build_id` 比对（`frontend/src/config/version.ts` 的 `compareBuilds`）
就会显示「前后端版本不一致」。2026-07-31 返工时踩过一次：漏导出重建了 backend，
`/api/v1/health` 变成 `"version":"dev"`；补一条 `docker compose up -d --no-deps backend`
（带上面这些 export）就恢复成 `1.8.5` / `local-20260731T101832Z`，**不需要重建镜像**
（env 覆盖镜像里的 ENV；而 `backend/Dockerfile` 的 ARG 在第 3~7 行，改 ARG 会让 apt/pip 层全部失效）。
回滚：`docker compose build` 会留下上一版镜像（`docker images | grep richangpim`），
`docker tag` 回去再 `up -d --no-deps <service>`；所以升级后先别清理镜像。

## 健康检查

### 后端健康检查

```bash
HEALTH_URL=http://127.0.0.1:888/api/v1/health ./scripts/healthcheck.sh
```

脚本默认检查 `http://localhost:8000/api/v1/health`，**在本机这个地址是不通的**（8000 未绑上），
所以必须显式传 `HEALTH_URL` 指向 nginx 的 `:888`。

裸 curl 时记得 `--noproxy '*'`：发行版里 export 了 `http_proxy=http://127.0.0.1:7890`，
不加会连 `127.0.0.1` 都被送去代理，拿回 502 让人误判服务挂了。

```bash
curl -s --noproxy '*' http://127.0.0.1:888/api/v1/health
```

### Docker 检查

```bash
docker compose ps
docker compose logs --tail=200 backend
docker compose config --quiet
```

## 备份

### ⚠️ 先读这条：`db_backup.sh` / `backup.sh` 在本机连不到生产库

`scripts/db_backup.sh` 默认连 `localhost:5432/ai_pim`。生产 Postgres **没有发布端口**，
这个地址到不了生产库。更危险的是：如果本机原生 PG18 恰好起着并且里面又有一个 `ai_pim`，
脚本会**静默备份错的那个库并报成功**。

在这台机器上备份生产库只用这一种写法（2026-07-31 实测通过）：

```bash
cd /home/AI-PIM/RiChangPIM
export DOCKER_HOST=unix:///mnt/wsl/docker-desktop/shared-sockets/host-services/docker.proxy.sock
TS=$(date +%Y%m%dT%H%M%S)
docker exec richangpim-postgres-1 pg_dump -U pim -d ai_pim -Fc -f /tmp/d.sqlc \
  && docker cp richangpim-postgres-1:/tmp/d.sqlc "backups/manual_${TS}.sqlc" \
  && docker exec richangpim-postgres-1 rm -f /tmp/d.sqlc \
  && ls -la "backups/manual_${TS}.sqlc"
```

要在 distro 的 shell 里跑：从 Windows 侧 `wsl.exe -- sh -c '...'` 套进来时 `$(date +%Y%m%d…)`
里的 `%` 会被 interop 吃掉，文件名会变成 `manual_.sqlc`。

下面几节是脚本的通用用法，**适用于 postgres 端口可达的部署**（例如把 5432 发布出来的环境），
在本机请用上面那条。

### 一体化备份

```bash
./scripts/backup.sh
```

这个脚本会用同一个 `batch_id` 生成 PostgreSQL 和 MinIO 两部分备份，并写入 `./backups/last_status.json`。

### 数据库备份

```bash
POSTGRES_HOST=<可达的 postgres 主机> POSTGRES_PASSWORD=<password> ./scripts/db_backup.sh
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

默认会生成到 `docker/nginx/certs/`。**本机只用于验收**——生产 nginx 只发布 `888:80`，没有 `443`。

### 入口说明（本机固定这一套，不要换端口）

| 用途 | 地址 |
| --- | --- |
| 门户 / 分享页 / API（生产 nginx） | `http://127.0.0.1:888/` |
| 管理后台（生产 nginx） | `http://127.0.0.1:888/admin/`（`:888/admin` 会 301 到带尾斜杠的） |
| 管理后台（演示服务器） | `http://127.0.0.1:5173/admin/` |
| AI 对话页 | `http://127.0.0.1:5173/chat` |
| 公网 | Funnel → Windows `3001` → portproxy → WSL `5173`（**不经过 nginx**） |
| 后端直连 `:8000` | **不可用**，Windows 系统进程占着 |

Windows 管理员 PowerShell 建立映射（脚本默认 `-FrontendTargetPort 5173`，正常不用带参数）：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\windows_demo_ports.ps1
```

```powershell
tailscale funnel 3001
```

改完必须确认 `curl -s --noproxy '*' http://127.0.0.1:3001/__demo/health` 的 `backendTarget`
是 `http://127.0.0.1:888`。2026-07-31 出过一次：5173 上跑着一个指向已消失的 `:8010` 的旧实例，
页面能开但登录无响应，公网入口等于是坏的。

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

### 6. 「所有密码都错」

**先怀疑连错库，不要先怀疑密码。** 跑 `bash scripts/where-am-i.sh`，看「数据规模」是不是「用户 7 / 商品 15」量级；
看到「用户 1 / 商品 0」就是连到空库了。生产库的主机名只能是 `postgres`（compose 网络内），
出现 `localhost:5432` / `127.0.0.1:5432` 一定是错的。详见本文开头的实机真相和 `/home/AI-PIM/从启动到穿透.md` §1。

### 7. 改了前端但 `:888` 没变化

`frontend/dist` 和 `portal/dist` 是 `COPY` 进 nginx 镜像的，不是 bind mount。
必须 `bash scripts/build_frontends.sh && docker compose build nginx && docker compose up -d --no-deps nginx`。
演示服务器（`5173`）相反，它直接读宿主机的 dist 目录，build 完刷新浏览器就生效。

### 8. curl 拿到 502 / 空回复

发行版里 export 了 `http_proxy=http://127.0.0.1:7890`，不加 `--noproxy '*'` 连 `127.0.0.1` 都会走代理。
这会让人误判服务挂了。

### 9. distro 里 docker CLI panic

`~/.docker` 存的 `desktop-linux` context 指向 Windows npipe。改用 Docker Desktop 铺在 `/mnt/wsl` 下的 socket：

```bash
export DOCKER_HOST=unix:///mnt/wsl/docker-desktop/shared-sockets/host-services/docker.proxy.sock
export DOCKER_CONTEXT=default
```

### 10. 后台起的进程一退出就死

从 Windows 侧 `wsl.exe -- sh -c` 调进来时，interop 会话结束会带走整个进程组，`nohup` 不管用，要用 `setsid`
（`scripts/start_demo.sh` 已经改成 `setsid`）。

改了 `scripts/pim-demo-server.mjs` 本身**必须重启进程**（node 已经把脚本读进内存了）；
只重新构建 dist 不用重启，它每个请求都是从磁盘读文件。

### 11. 产品列表滚动卡顿 / 封面很慢

列表用的是服务端缩略图，不是原图：`GET /api/v1/files/{id}/content?w=<宽度>`。

- 宽度是白名单 `96 / 192 / 240 / 480 / 960`（短边），别的值回 **422**（`code 42205`），
  **不会**静默退回原图——退回的话前端写错宽度永远发现不了，性能悄悄退回原点。
- 实现在 `backend/app/services/thumbnails.py`（叶子模块，`backend/tests/unit/test_thumbnails.py` 覆盖）；
  `app/api/v1/files.py` 只做宽度校验 + `asyncio.to_thread`。
- 缓存是 MinIO 里的派生对象 `derived/thumb/w{width}/{oss_key}.webp`，读穿式：首次现缩并回写，之后直接读。
  替换文件时按 5 个宽度逐个 `remove_object` 清掉旧派生物。
- 前端两个档位写在 `frontend/src/views/Products.vue`：表格 `TABLE_THUMB_WIDTH=192`、卡片 `TILE_THUMB_WIDTH=480`。
  改这两个数必须同时在 `THUMB_WIDTHS` 里有对应档位（单元用例钉住了）。
- 2026-07-31 实机复测（重建后的 `:888`，14 张封面）：表格视图 20,030 B / 位图 1.02 MP，
  卡片视图 72,900 B / 4.56 MP，没有一个请求缺 `w=`；原图那条路径不变（不带 `w` 仍回原始 JPEG）。
  同一宽度冷启动 460 ms（现缩+回写）、命中缓存 8~9 ms，字节完全一致。
- 排查顺序：桶里有没有 `derived/thumb/**` → 接口带 `w` 时 `content-type` 是不是 `image/webp` →
  浏览器 Network 里封面 URL 有没有 `w=`。缺 Pillow 只会让这一条路 500，其余接口不受影响
  （`requirements.txt` 里 `pillow==10.2.0; python_version < '3.13'`，生产镜像是 `python:3.11-slim`）。

### 12. 在宿主机跑 `backend/tests`

宿主 python 是 3.14，缺 `pgvector` / `pytest-asyncio` / `pillow`，而 PEP 668 不让往系统 python 装。
建一个继承系统包的临时 venv，走发行版那个代理（pypi 直连实测超时，`http://127.0.0.1:7890` 通）：

```bash
python3 -m venv --system-site-packages /tmp/pimtestenv && /tmp/pimtestenv/bin/pip install --proxy http://127.0.0.1:7890 pgvector==0.3.6 pytest-asyncio==1.4.0 pillow
```

```bash
cd /home/AI-PIM/RiChangPIM/backend && /tmp/pimtestenv/bin/python -m pytest tests/unit -q
```

`pillow` 不钉 `10.2.0`（3.14 上没轮子、源码也编不过），宿主只是跑测试，生产镜像仍是 3.11 + 10.2.0。
`tests/integration` 仍然跑不了：生产库没发布 5432，本机 PG18 里的 `pim` 不是 superuser、建不了 `vector` 扩展。
用完 `rm -rf /tmp/pimtestenv` 就干净了（不要装进系统 python，也不要写进仓库）。

## 已知缺口

按严重程度排：

1. **后台包里还留着一条被门户取代的分享页路由。** 公开分享页现在由门户承载
   （`portal/src/views/SharePage.vue`，nginx 靠 `location /` 回落到门户 index.html），但后台的
   `frontend/src/router.ts` 里那条 `/share/:token` 和 `frontend/tests/e2e/sharing.spec.ts` 还在，
   删不删都不影响线上（`:888/share/*` 到不了后台包），只是两处实现并存容易误改错的那个。
   `:888/admin/` 本身已经在 2026-07-31 修好：后台按 `VITE_BASE_PATH=/admin/` 构建、
   `default.conf` 加了 `location = /admin` 的 301 与 `absolute_redirect off`，
   `merge_admin_static` 和 `/share/` 的 alias 都已删除。
2. **`scripts/db_backup.sh` / `backup.sh` / `healthcheck.sh` / `minio_backup.sh` 的默认地址在本机全是死的**
   （都指向宿主机端口，而生产只发布 `888`）。`db_backup.sh` 最危险：本机若同时存在同名库，它会静默备份错的库并报成功。
   用上面「备份」一节的 `docker exec` 写法。
3. **`docker-compose.yml` 把 `APP_VERSION` / `BUILD_ID` / `GIT_COMMIT` / `BUILD_TIME` 默认成
   `dev` / `dev-local` / `unknown`**，`.env.example` 的 `VITE_APP_VERSION=dev` 同理；
   不显式传就会报假版本（`build_frontends.sh` 会给前端注入真值，裸 `npm run build` 不会；
   backend 侧要靠「升级发布 runbook」第 3 步手工 export，漏了后台「版本」页会报「前后端版本不一致」）。
4. **backend 的 `8000:8000` 绑不上**（Windows 系统进程占着）。不影响使用，但所有「后端地址」都必须写 `:888`。
5. **前端没有独立镜像**（无 `frontend/Dockerfile`），dist 由宿主机构建后 `COPY` 进 nginx 镜像，
   所以「构建机 = 宿主机」这个隐含依赖没法从 compose 文件里看出来。

## 常用文件

- `scripts/where-am-i.sh`：**环境体检，每次开工第一条命令**
- `scripts/build_frontends.sh`：两个前端构建 + 版本注入 + 后台按 `base '/admin/'` 构建（不要用裸 `npm run build`）
- `backend/docker/backend-entrypoint.sh`：容器启动时的迁移 / 管理员 / 种子顺序
- `/home/AI-PIM/从启动到穿透.md`：**实机启动与穿透全流程**（在仓库外，上一级目录）
- `docker-compose.yml`：生产编排
- `docker-compose.dev.yml`：开发编排
- `docker/nginx/conf.d/default.conf`：生产路由（`/` 与 `/share/{token}` 门户、`/admin/` 后台产物、`/api/` 反代）
- `scripts/start_demo.sh` / `scripts/stop_demo.sh`：演示服务器（后台入口），按 `PIM_DEMO_PORT` 起停
- `scripts/windows_demo_ports.ps1`：Windows 侧 portproxy + 防火墙（`-FrontendTargetPort` 要和演示端口一致）
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
