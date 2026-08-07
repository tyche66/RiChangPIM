# 全量备份迁移包

本文档说明 RiChangPIM「全量备份迁移包」是什么、怎么打、怎么恢复、怎么校验。
它面向整机迁移与灾难恢复：**拿着一个 tar.gz 到一台干净机器上，把整套系统连数据一起重建起来。**

从 `v1.9.1` 起，全量迁移包根目录还必须包含 `<version>-V-Log.md`，记录本版功能、兼容性、升级注意事项和两类发布包边界。

日常的增量备份看 [README-OPS.md](README-OPS.md) 的「备份」一节，那是另一件事——
本文档描述的是发版时打的那种全量包，一次几百 MB。

## 目录

- [现有的包](#现有的包)
- [包内结构](#包内结构)
- [怎么打一份新的](#怎么打一份新的)
- [怎么恢复](#怎么恢复)
- [怎么校验](#怎么校验)
- [保密要求](#保密要求)
- [已知限制](#已知限制)
- [发版打包清单](#发版打包清单)

## 历史包与当前包

包放在**仓库外**的 `/home/AI-PIM/`（WSL 发行版 `RiChangPIM` 内），不进 git、不进镜像。

| 包 | 版本 | 大小 | 说明 |
| --- | --- | --- | --- |
| `RiChangPIM_v1.9.1_20260807_111932.tar.gz` | v1.9.1（`c299cb4`，tag `v1.9.1`） | 407,700,768 B | 当前包；sha256 `3d132907e197bc8574617d0fee36d51254328828d7414306428798586be7879d` |
| `RiChangPIM_v1.9.0_20260731_215300.tar.gz` | v1.9.0（`9cd132c`，tag `v1.9.0`） | 240,369,356 B | 历史参考包。sha256 见同目录 `.sha256` 文件 |
| `RiChangPIM_v1.8.0_20260729_110810.tar.gz` | v1.8.0 | 239,131,745 B | 上一份，v1.9.0 包的结构参考 |

v1.9.0 包的 sha256：`cb4f9fc12b43040a219b0b50b6d09b8b11251558adddf3097bdbe9fed8499ca6`

解压后是一个与包同名的目录，里面有一份 `MIGRATION_README.md`——**恢复时以包内那份为准**，
它带着这一份包自己的时间戳、commit、迁移 head 和文件名，本文档只讲通用规则。

## 包内结构

以 v1.9.0 包实测为例（`MANIFEST.txt` 里是完整的 `路径<TAB>字节数`）：

| 路径 | 内容 | 本包大小 |
| --- | --- | --- |
| `source/RiChangPIM_source_worktree.tar.gz` | 源码快照。打包时工作区干净，等同发布提交 | 140,113,200 B |
| `source/RiChangPIM_git.bundle` | `git bundle --all`，含 `main` 与全部 tag（含 `v1.9.0`） | 1,543,894 B |
| `source/git-head.txt` / `git-status.txt` | 打包时刻的 commit/branch/tag/remote 与 `status --porcelain` | 234 / 104 B |
| `data/db/ai_pim_<ts>.dump` | `pg_dump -Fc` custom 格式逻辑备份，**恢复首选** | 172,322 B |
| `data/db/ai_pim_<ts>.sql` | 同一份数据的 plain SQL，审计与兜底 | 386,984 B |
| `data/volumes/postgres_pg16_data_volume_<ts>.tar.gz` | Postgres 命名卷热归档，仅兜底 | 87,318,228 B |
| `data/volumes/minio_data_volume_<ts>.tar.gz` | MinIO 卷：产品图片 + `derived/thumb/**` 缩略图 | 16,034,035 B |
| `data/volumes/redis_data_volume_<ts>.tar.gz` | Redis 卷（缓存，可丢） | 223 B |
| `env/{root,backend,AI,embedding}.env` | 四个配置原件，**含真实口令与 AI Key** | 843 / 2058 / 51 / 73 B |
| `docker-inspect/` | `docker ps`、`docker volume ls`、容器 `inspect`、卷 `inspect` | 86,358 B |
| `scripts/restore_notes.sh` | 恢复要点速查，只打印不执行 | 1,489 B |
| `MANIFEST.txt` | 包内文件清单，含自身大小 | 702 B |
| `MIGRATION_README.md` | 这一份包的恢复手册 | 8,379 B |
| `checksums/sha256sums.txt` | 包内全部文件的 SHA-256（不含自身，可直接 `-c`） | — |

源码快照里**不含**：`.git`、`.env*`（在 `env/`）、`node_modules`、虚拟环境、
`__pycache__` / `.pytest_cache` / `.ruff_cache` / `.mypy_cache` / `.vite`、
`frontend/dist`、`portal/dist`、`coverage`、`playwright-report`、`test-results`、`backups/`、`*.log`。
## 怎么打一份新的

前提：**工作区干净、版本号已按 [CHANGELOG.md](CHANGELOG.md) 的表改完、tag 已打**——
包里的 `git-status.txt` 就是这件事的证据，脏工作区打出来的包没法说清"包内源码是哪个版本"。

全程**不停、不重启、不修改任何服务**。数据库走 `docker exec pg_dump`，卷是热归档。

```bash
cd /home/AI-PIM/RiChangPIM
export DOCKER_HOST=unix:///mnt/wsl/docker-desktop/shared-sockets/host-services/docker.proxy.sock
export DOCKER_CONTEXT=default
TS=$(date +%Y%m%d_%H%M%S)
STAGE=/home/AI-PIM/RiChangPIM_v<版本号>_${TS}
mkdir -p "$STAGE"/{env,scripts,docker-inspect,source,data/db,data/volumes,checksums}
```

```bash
# 1) env（四个文件原样拷）
cp .env "$STAGE/env/root.env"; cp backend/.env "$STAGE/env/backend.env"
cp AI.env "$STAGE/env/AI.env"; cp embedding.env "$STAGE/env/embedding.env"
```

```bash
# 2) source：bundle + HEAD 信息 + 工作区快照
git bundle create "$STAGE/source/RiChangPIM_git.bundle" --all
git rev-parse HEAD > "$STAGE/source/git-head.txt"   # 实际还写了 branch/tag/describe/remote
git status --porcelain > "$STAGE/source/git-status.txt"
tar -czf "$STAGE/source/RiChangPIM_source_worktree.tar.gz" -C . \
  --exclude=./.git --exclude=./.env --exclude=./backend/.env \
  --exclude=./AI.env --exclude=./embedding.env \
  --exclude='./**/node_modules' --exclude=./backend/venv --exclude=./backend/.venv \
  --exclude='./**/__pycache__' --exclude='./**/.pytest_cache' --exclude='./**/.ruff_cache' \
  --exclude='./**/.mypy_cache' --exclude='./**/.vite' \
  --exclude=./frontend/dist --exclude=./portal/dist \
  --exclude=./frontend/coverage --exclude=./portal/coverage \
  --exclude='./**/playwright-report' --exclude='./**/test-results' \
  --exclude=./backups --exclude='./**/*.log' .
```

```bash
# 3) 数据库：只能用这一种写法（见「已知限制」）
docker exec richangpim-postgres-1 pg_dump -U pim -d ai_pim -Fc -f /tmp/b.dump
docker cp richangpim-postgres-1:/tmp/b.dump "$STAGE/data/db/ai_pim_${TS}.dump"
docker exec richangpim-postgres-1 pg_dump -U pim -d ai_pim -f /tmp/b.sql
docker cp richangpim-postgres-1:/tmp/b.sql "$STAGE/data/db/ai_pim_${TS}.sql"
docker exec richangpim-postgres-1 rm -f /tmp/b.dump /tmp/b.sql
```
```bash
# 4) 卷：把 tar 流从容器里 cat 出来，不要 bind mount 宿主目录
#    （从 WSL 发行版里 -v /home/...:/backup 会被 Docker Desktop 当成 Windows 路径翻译）
for V in postgres_pg16 minio redis; do
  docker run --rm -v "richangpim_go_${V}_data_20260716:/volume:ro" alpine:3.20 \
    tar -czf - -C /volume . > "$STAGE/data/volumes/${V}_data_volume_${TS}.tar.gz"
done
```

```bash
# 5) docker-inspect
docker ps > "$STAGE/docker-inspect/docker-ps.txt"
docker volume ls > "$STAGE/docker-inspect/docker-volumes.txt"
docker inspect $(docker ps -q) > "$STAGE/docker-inspect/containers.json"
docker volume inspect richangpim_go_postgres_pg16_data_20260716 \
  richangpim_go_minio_data_20260716 richangpim_go_redis_data_20260716 \
  > "$STAGE/docker-inspect/volumes.json"
```

```bash
# 6) 手册 + 速查脚本：把上一份包里的 MIGRATION_README.md / restore_notes.sh 拿来改
#    时间戳、commit、tag、迁移 head、文件名都要换成这一份包的真值

# 7) MANIFEST.txt（含自身大小，迭代到稳定）+ sha256（不含自身）
cd "$STAGE"
: > MANIFEST.txt
for i in 1 2 3 4 5; do
  find . -type f -not -path './checksums/sha256sums.txt' -printf '%P\t%s\n' | sort -f > /tmp/m.new
  cmp -s /tmp/m.new MANIFEST.txt && break; cp /tmp/m.new MANIFEST.txt
done
find . -type f -not -path './checksums/sha256sums.txt' | sort -f | xargs sha256sum \
  > checksums/sha256sums.txt
sha256sum -c checksums/sha256sums.txt        # 必须全 OK

# 8) 打包 + 记 sha256
cd /home/AI-PIM && tar -czf "${STAGE##*/}.tar.gz" "${STAGE##*/}"
sha256sum "${STAGE##*/}.tar.gz" | tee "${STAGE##*/}.tar.gz.sha256"
```

打完在**另一个目录**解一次、`sha256sum -c` 过一遍、抽查源码包里的版本锚点
（`frontend/package.json`、`portal/package.json`、`backend/app/core/config.py`、`CHANGELOG.md` 顶部）
和 `git bundle list-heads` 里有没有这一版的 tag。v1.9.0 包是这么验过的。

从 Windows 侧 `wsl.exe -- sh -c '...'` 套进来跑时注意：`$(date +%Y%m%d…)` 里的 `%` 会被 interop 吃掉，
时间戳会变成空字符串。要么在发行版的 shell 里跑，要么把命令写进脚本文件再执行。
## 怎么恢复

细节以包内 `MIGRATION_README.md` 为准（那里有这一份包的真实文件名）。顺序不能换：

**解源码 → 放 env → 改密钥 → 起基础设施 → 灌库 → 灌 MinIO → 构建前端 → 起全栈 → 验收**

要点：

1. **先灌库，再起 backend。** backend 容器的 entrypoint 会跑
   `alembic upgrade head → 初始化管理员 → 种子数据`。库里已经是发布版 schema 时 alembic 直接 no-op；
   顺序颠倒会先建出一套空库再往上恢复，容易撞对象已存在。
2. **前端产物不在包里，必须在目标机器上构建。** `frontend/dist` / `portal/dist` 是
   `COPY` 进 nginx 镜像的，不是挂载。而且必须走 `bash scripts/build_frontends.sh`：
   它注入真实版本元数据，并设 `VITE_BASE_PATH=/admin/`；裸 `npm run build` 出来的后台
   `index.html` 引用 `/assets/...`，在 nginx 上会落到门户目录 → 后台白屏。
3. **构建 backend 前把版本值 export 出去**（`APP_VERSION` / `BUILD_ID` / `GIT_COMMIT` /
   `BUILD_TIME` / `APP_ENV=production`，值抄 `build_frontends.sh` 的输出）。
   compose 里这四个默认是 `dev` / `dev-local` / `unknown`，漏了后端会自报 `dev`，
   后台「版本」页显示「前后端版本不一致」。
4. **Postgres 用逻辑备份恢复**：`pg_restore -U pim -d ai_pim --no-owner --no-acl`。
   卷归档只在逻辑备份不可用时用，恢复卷前必须停对应服务。
5. **MinIO 必须恢复**，产品图片和 `derived/thumb/**` 缩略图都在里面；不恢复的话列表封面全空。
6. 验收看四个入口：`:888/`、`:888/admin/`、`:888/share/<token>`、`:888/api/v1/health`
   （`health` 的 `version` 必须是真版本号），再 `docker exec richangpim-backend-1 alembic current` 核迁移 head。
   curl 记得 `--noproxy '*'`。

## 怎么校验

```bash
tar -xzf RiChangPIM_v1.9.0_20260731_215300.tar.gz
cd RiChangPIM_v1.9.0_20260731_215300
sha256sum -c checksums/sha256sums.txt     # 20 个文件，必须全 OK
cat MANIFEST.txt                          # 路径<TAB>字节数，和实际逐个对得上
cat source/git-head.txt                   # commit / tag 是不是这一版
git bundle list-heads source/RiChangPIM_git.bundle | grep refs/tags
```

包本身的完整性用同目录的 `.sha256` 文件核对：

```bash
sha256sum -c RiChangPIM_v1.9.0_20260731_215300.tar.gz.sha256
```
## 保密要求

**这个包等于一把总钥匙**，按机密件对待：

- `env/` 四个文件是配置原件，含数据库口令、`JWT_SECRET`、MinIO 根凭据、管理员口令、AI API Key。
- `data/db/*` 含用户表（口令是 hash，但仍属敏感）、全部业务数据。
- 所以：**包不进 git、不进镜像、不进任何公开渠道**，`.gitignore` / `.dockerignore` 已排除 `backups/` 与 `.env*`，
  但包本身是放在仓库外的 `/home/AI-PIM/`，别把它挪进仓库目录。
- 传输走受控通道；落地后**立即轮换** `POSTGRES_PASSWORD`、`JWT_SECRET`、`ADMIN_PASSWORD`、
  `MINIO_ROOT_PASSWORD` / `MINIO_SECRET_KEY`、`AI_API_KEY`。
- 口令值不写进任何文档、聊天记录或截图——包括本文档。轮换清单只写变量名。
- 恢复完跑一次 `bash scripts/secret_scan.sh` 确认没有硬编码泄露。
- `ADMIN_PASSWORD` 的特殊行为：backend 每次启动都会用 `.env` 里的值重算 hash 覆盖库里的 admin 口令。
  在界面上改的密码会被下次重启盖回去，要改就改 `.env`。

## 已知限制

1. **卷归档是热的。** 打包时没有停 Postgres/MinIO，`data/volumes/postgres_pg16_*.tar.gz`
   在事务边界上不保证一致，只能兜底。**权威数据源是 `data/db/*.dump`。**
2. **卷名写死在包里**（`richangpim_go_*_data_20260716`，`docker-inspect/volumes.json` 有记录）。
   目标环境卷名不同要改 `docker-compose.yml`，否则恢复到了一个没人用的卷上。
3. **不要用 `scripts/db_backup.sh` 打这个包。** 它默认连 `localhost:5432/ai_pim`，
   而生产 Postgres 没发布端口；若本机恰好另有同名空库，它会**静默备份错的库并报成功**。
   只用 `docker exec richangpim-postgres-1 pg_dump`。
4. **包里没有镜像。** 恢复要重新 `docker compose build`，依赖能拉到 Docker Hub / npm / PyPI。
   完全离线的迁移需要另外 `docker save`（当前没做，包会再大几百 MB）。
5. **`node_modules` 不在包里**，恢复需要 `npm ci`（`package-lock.json` 在源码包里，版本锁得住）。
6. 包是 `tar.gz` 套 `tar.gz`：外层再压一次几乎不减体积，纯粹为了对齐上一份包的结构，别指望压缩率。

## 发版打包清单

按顺序勾：

- [ ] 版本号 7 处锚点已按 [CHANGELOG.md](CHANGELOG.md) 改完，`git status --porcelain` 为空
- [ ] annotated tag 已打并推送，`git ls-remote --tags origin` 能看到
- [ ] 生产栈是这一版（`:888/api/v1/health` 的 `version` / `build_id` 与 dist 一致）
- [ ] 磁盘余量 ≥ 5 GB（包 240 MB，中间产物峰值约 2 倍）
- [ ] 上面 8 步跑完，`sha256sum -c` 全 OK
- [ ] 换目录解一次、抽查源码包版本锚点、`git bundle list-heads` 有本版 tag
- [ ] 本文档「现有的包」表加一行（包名、版本、大小、sha256）
- [ ] 包留在 `/home/AI-PIM/`，不要移进仓库；旧包按保留策略处置（当前保留最近两份）
