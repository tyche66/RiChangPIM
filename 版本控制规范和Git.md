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
3. 完成后端专项及完整测试、前端测试、类型检查、构建和关键 E2E。
4. 合并发布提交到 `main`。
5. 创建 annotated tag：`git tag -a vX.Y.Z -m "Release vX.Y.Z"`。
6. 推送分支和标签：`git push origin main && git push origin vX.Y.Z`。
7. 在 GitHub Release 中记录功能、修复、API 变化、迁移要求和已知风险。

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
