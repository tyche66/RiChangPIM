# RiChangPIM 版本控制规范和 Git 使用指南

## 1. 版本基线

- 本仓库从 `v1.0.1` 开始执行本规范。
- 版本号遵循语义化版本 `MAJOR.MINOR.PATCH`。
- `MAJOR`：不兼容的业务或 API 变更。
- `MINOR`：向后兼容的新功能。
- `PATCH`：向后兼容的问题修复和小幅优化。
- 前端版本以 `frontend/package.json` 为代码内基准；发布构建通过 `APP_VERSION` 和 `VITE_APP_VERSION` 注入同一版本。
- 每个正式版本必须有 annotated tag，例如 `v1.0.1`。

## 1.1 版本号的单一事实来源

规范只说了「锚点是 `frontend/package.json`」，没说版本号一共散落在几处，结果 `v1.8.0` → `v1.8.5` 之间有 7 个文件停在旧值（`README.md` 报 v1.8.0、后端兜底报 0.1.0、门户 `package.json` 报 0.1.0）。补一条硬规则：

- **当前版本号的现值只认 `CHANGELOG.md` 顶部。** 任何文档要写「当前版本」，要么引用 `CHANGELOG.md`，要么就不写。
- **手改的位置只有 `CHANGELOG.md`「改版本号要动哪几处」列出的那几处**（前端 `package.json`、门户 `package.json`、`backend/app/core/config.py` 的 `VERSION`、`CHANGELOG.md`、`README.md`、`AI-Docs/README.md`、annotated tag）。发版时按那张表逐项打勾。
- **派生值不许手写**：`frontend/src/config/version.ts`、`/api/v1/version`、`/health`、OpenAPI 的 `version` 都从上面几处推出来；CI 的 `APP_VERSION` 从 tag 或 `frontend/package.json` 读，不许在脚本里写死版本号。
- **兜底值也必须是真话**：`settings.VERSION` 这类「没注入时用什么」的默认值要跟着发版一起改，否则忘传构建参数的部署会对外报一个不存在的版本。
- **版本信息校对页面必须显示真话**：后台「系统管理 → 版本」页（`frontend/src/views/Version.vue`，接口 `GET /api/v1/version`）是唯一让使用者肉眼确认「浏览器里的前端构建」和「正在跑的后台实例」是否同版的地方。发完一个版本，那一页的「前端构建」和「后台运行实例」两块的**版本 / 构建 ID / Git commit / 构建时间四项都不能是 `—`**，且顶部「一致性检查」必须是「一致」。出现 `—` 或「缺少构建信息，无法确认」即视为未发布完成，不等同于版本号改完。
- **构建时间一律用北京时间（UTC+8），不用 UTC**：`BUILD_TIME` / `VITE_BUILD_TIME` 生成时必须写 `TZ=Asia/Shanghai date +%Y-%m-%dT%H:%M:%S%z`，显式指定时区，不依赖机器设置（GitHub runner 默认 UTC）。版本页的构建时间是给人对照 `git log`、`docker` 事件和报障描述看的，那些都按本地时间记；输出 UTC 会让页面比真实操作慢 8 小时，对不上任何一边。`%z` 必须带上真实偏移，不许写死 `+08:00` 或省略。`BUILD_ID` 里嵌的时间戳同理（`scripts/build_frontends.sh`）。备份类脚本（`backup.sh` / `db_backup.sh` / `minio_backup.sh` 的 `TS_UTC` / `created_utc`）是跨时区审计记录，**继续用 UTC，不要跟着改**。
- **`docker-compose.yml` 的 `${APP_VERSION:-dev}` 会压掉第 3 处的兜底值**：`config.py` 的 `VERSION` 只在 `APP_VERSION` 完全没设时兜底，而 compose 给 `build args` 和运行时 `environment` 都写了 `APP_VERSION: ${APP_VERSION:-dev}`。于是「忘了传参」时后端对外报的是 `dev`、`BUILD_ID=dev-local`、`GIT_COMMIT=unknown`、`BUILD_TIME=unknown`，`Version.vue` 把这四个值一律渲染成 `—`，`compareBuilds()` 也判 `unknown`。**改 `config.py` 的兜底值不够，必须连 compose 的构建参数一起传**，否则版本页永远说不清。（这条 2026-09-29 在 v1.9.2 上实测复现：`docker inspect` 显示容器内 `APP_VERSION=dev`。）
- **后端不替前端报版本**：前后端各自独立构建，一致性由 `compareBuilds()` 比对得出，不能由某一端凭空补全另一端的版本号。
- **历史记录不跟版本走**：`BUILD_LOG.md`、`PROJECT_MANAGEMENT.md`、`TODO.md` 的已发布条目、`docs/08-开发路线图.md` 的里程碑行记的是当时的事实，发新版时不要改写；`RELEASE_GATE.md` 定义的是每次发布都要过的门禁，保持版本无关。

## 2. 分支策略

- `main`：唯一长期分支，始终保持可构建、可部署。
- `feature/<主题>`：新功能，例如 `feature/product-proposal-selection`。
- `fix/<主题>`：常规缺陷修复，例如 `fix/proposal-detail-loading`。
- `hotfix/<主题>`：生产紧急修复。
- `release/vX.Y.Z`：可选的发布稳定分支，只允许修复发布阻塞问题。
- 功能分支通过 Pull Request 合并到 `main`；禁止在 `main` 上长期开发。

## 3. 提交规范

提交信息采用 Conventional Commits：

- `feat:` 新功能。
- `fix:` 缺陷修复。
- `test:` 测试新增或修正。
- `docs:` 文档变更。
- `refactor:` 不改变行为的重构。
- `perf:` 性能优化。
- `build:` 构建或依赖变更。
- `ci:` 持续集成变更。
- `chore:` 其他维护工作。

提交要求：

- 一个提交只表达一个可说明的目的。
- 不提交 `.env`、令牌、密码、私钥、数据库文件、日志、构建产物或依赖目录。
- **脚本里出现的口令必须和生产的不是同一组**：可以为本机栈写默认值（如 `scripts/start_local_stack.sh`），但那组值必须与 `.env` 里的生产凭据不同，且提交前跑一遍 `scripts/secret_scan.sh`。把生产凭据写进脚本会让它随 Git 永久公开，改密码也改不回去。
- `package-lock.json` 必须随 `package.json` 的依赖变化提交。
- 提交前必须检查 `git status`、`git diff` 和待提交文件，避免包含无关文件。
- 禁止通过 `--no-verify` 绕过检查，禁止对共享分支 force push。

## 4. 日常工作流

```bash
git switch main
git pull --ff-only origin main
git switch -c feature/example

# 开发并验证
git status
git diff
git add <明确的文件>
git commit -m "feat: describe the change"
git push -u origin feature/example
```

随后在 GitHub 创建 Pull Request，等待 CI 和代码审查通过后合并。

## 5. 合并与同步

- 拉取 `main` 使用 `git pull --ff-only`，避免无意产生 merge commit。
- 功能分支需要同步主线时优先 rebase：`git fetch origin && git rebase origin/main`。
- 已推送且多人使用的分支不做破坏性 rebase。
- 解决冲突后必须重新运行受影响测试。
- GitHub 是共享历史的权威来源，本地仓库必须配置 `origin` 指向 `tyche66/RiChangPIM`。

## 6. 发布流程

1. 确认工作区干净并同步 `origin/main`。
2. 按 `CHANGELOG.md`「改版本号要动哪几处」逐项更新版本号、发布说明和必要文档（§1.1）。
3. 完成后端专项及完整测试、前端测试、类型检查、构建和关键 E2E。**这一步的构建只用来验证「能构建」，不是上生产的产物**——它跑在版本号改完但尚未提交的工作区上，产物带的 Git commit 会打 `-dirty`。
4. **合并发布提交到 `main`**（放在构建之前，见 §6.1 第三点）。
5. **按 §6.1 构建并上生产**：先跑 `scripts/build_frontends.sh` 拿到四项元数据，再用**同样的** `APP_VERSION` / `BUILD_ID` / `GIT_COMMIT` / `BUILD_TIME` 重建后端，最后 `docker compose build nginx` 上门户与后台。三项都不能省：
   - `build_frontends.sh`：注入真实版本元数据，并让后台按 `base /admin/` 构建。
   - `docker compose build backend`（带 `export` 的四个值）：漏了后台那半块版本页全是 `—`，而接口本身 200，从状态码上看不出来。
   - `docker compose build nginx`：`dist` 是 `COPY` 进 nginx 镜像的，只在宿主机 build 不会改变 `:888` 上的任何东西。
6. 创建 annotated tag：`git tag -a vX.Y.Z -m "Release vX.Y.Z"`。
7. 推送分支和标签：`git push origin main && git push origin vX.Y.Z`。
8. 在 GitHub Release 中记录功能、修复、API 变化、迁移要求和已知风险。

### 6.1 版本信息校对页面验收（第 5 步的配套，必做）

登录后台「系统管理 → 版本」页，逐项确认：

| 位置 | 要求 |
| --- | --- |
| 前端构建 → 版本 | 等于本次发布的版本号（由 `scripts/build_frontends.sh` 注入 `VITE_APP_VERSION`） |
| 前端构建 → 构建 ID | 不是 `—`，且与 `build_frontends.sh` 输出的 `BUILD_ID` 逐字相同 |
| 前端构建 → Git commit | 不是 `—`；工作区干净时应为不带 `-dirty` 的短 hash（见 `build_frontends.sh` 的 dirty 标记逻辑） |
| 前端构建 → 构建时间 | 不是 `—`，且是**北京时间**（形如 `2026-09-29T14:10:39+0800`，不是 `...Z`） |
| 后台运行实例 → 版本 / 构建 ID / Git commit / 构建时间 | 四项都不是 `—`；`BUILD_ID` 与前端那块**相同** |
| 环境 / API | `production` / `v1` |
| 一致性检查 | 「一致」，不是「缺少构建信息，无法确认」，也不是「不一致」 |

三个容易漏的点：

- **前端版本号来自构建期，不是运行期**。改完 `frontend/package.json` 之后必须重跑 `scripts/build_frontends.sh` 并 `docker compose build nginx`，否则版本页上半块停在旧版本——`dist` 是 `COPY` 进 nginx 镜像的，只改 `package.json` 不动镜像没有任何效果。顺序上先发包再构建会得到旧版本号，v1.9.2 就踩过这一次。
- **裸 `npm run build` 不行**。它不注入 `VITE_APP_VERSION` / `VITE_BUILD_ID` / `VITE_GIT_COMMIT` / `VITE_BUILD_TIME`，会退化成 `package.json` 的值 + `dev-local` + `unknown`，版本页照样显示 `—`。
- **先提交、再构建，页面上的 commit 才是真话**。`build_frontends.sh` 用 `git status --porcelain` 判断工作区是否干净，不干净就给 `GIT_COMMIT` 打 `-dirty`。带着未提交改动构建，版本页会显示一个对不上任何提交的 hash。

### 正确顺序（可照抄）

```bash
cd /home/AI-PIM/RiChangPIM
export PATH="$HOME/.nvm/versions/node/v24.18.0/bin:$PATH"
export DOCKER_HOST=unix:///mnt/wsl/docker-desktop/shared-sockets/host-services/docker.proxy.sock
export DOCKER_CONTEXT=default

# 1) 改版本号、写说明（§6 第 2 步）→ 跑测试（第 3 步）
# 2) 提交（第 4 步）——必须在构建之前
git add -A && git commit -m "feat: release vX.Y.Z ..."

# 3) 构建前端，拿到四项元数据（第 5 步）
bash scripts/build_frontends.sh
#    ==> APP_VERSION=x.y.z BUILD_ID=local-YYYYMMDDTHHMMSS+0800 GIT_COMMIT=<hash> BUILD_TIME=...+0800

# 4) 用同一组值重建后端；BUILD_ID 必须和上一步的完全一致
export APP_VERSION=x.y.z BUILD_ID=local-YYYYMMDDTHHMMSS+0800 \
       GIT_COMMIT=<hash> BUILD_TIME=<第 3 步输出的那个值> APP_ENV=production
docker compose build backend && docker compose up -d --no-deps backend

# 5) 上前端（dist 是 COPY 进 nginx 镜像的）
docker compose build nginx && docker compose up -d --no-deps nginx

# 6) 打 tag 并推送（第 6、7 步）
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin main && git push origin vX.Y.Z
```

上面第 3、4 步里的四个值（`APP_VERSION` / `BUILD_ID` / `GIT_COMMIT` / `BUILD_TIME`）一律抄第 3 步构建的真实输出，不要手写、不要从别的版本复制——手写的值对不上产物，版本页就成了「看起来一致、实际查无此构建」。

## 7. 发布门禁

正式发布至少通过：

```bash
# 后端
cd backend
python -m pytest

# 前端
cd frontend
npm test
npx vue-tsc --noEmit
npm run build
npx playwright test
```

若测试依赖 PostgreSQL、MinIO、浏览器或外部服务而无法运行，发布说明必须记录阻塞原因和已完成的替代验证。不得把失败测试静默标记为通过。

除上面的命令之外，还有一条**必须用浏览器走一遍**的门禁：

- 后台「系统管理 → 版本」页：前端构建与后台运行实例的四项元数据都不是 `—`，一致性检查为「一致」（判定标准见 §6.1）。

命令级的测试全绿但版本页显示 `—`，同样不算过门禁——那种情况下「哪个版本在跑」这件事对使用者是不可知的。

## 8. 标签与回滚

- tag 一经推送不得移动或复用。
- 回滚已发布代码使用 `git revert <commit>`，不使用 `git reset --hard` 改写共享历史。
- 紧急回滚后创建新的 PATCH 版本，不覆盖旧版本标签。
- 数据库迁移回滚必须先验证数据安全，不能只回滚应用代码。

## 9. GitHub 管理

- `main` 建议开启分支保护、必须通过 CI、至少一次审查、禁止 force push。
- 密钥只保存在 GitHub Actions Secrets 或部署环境中。
- Issue 用于记录可复现问题；Pull Request 必须关联问题并说明验证结果。
- 大文件和运行时数据不进入 Git，确有需要时使用对象存储或 Git LFS。

## 10. 常用检查命令

```bash
git status --short
git diff --check
git diff --stat
git log --oneline -10
git remote -v
git tag --list --sort=-version:refname
```
