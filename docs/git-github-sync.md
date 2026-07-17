# Git 与 GitHub 同步记录

日期：2026-07-17

## 目标

- 为 AI-PIM 项目建立本地 Git 版本控制。
- 后续同步到 GitHub 私有仓库，用于云端备份、协作、PR 审查和 CI。
- 不提交真实密钥、运行时 `.env`、Docker volume、备份文件、测试报告生成物或依赖目录。

## 已完成的本地操作

| 时间 | 操作 | 结果 |
| --- | --- | --- |
| 2026-07-17 | 在 `/home/AI-PIM/RiChangPIM` 执行 `git init` | 已创建本地 Git 仓库 |
| 2026-07-17 | 将默认分支重命名为 `main` | 已完成 |
| 2026-07-17 | 检查 `.gitignore` | `.env`、`backend/.env`、`venv/`、`node_modules/`、`dist/`、`docker/volumes/`、`logs/`、`backups/` 已忽略 |
| 2026-07-17 | 补充 `.gitignore` | 增加 `playwright-report/`、`test-results/`、`backend/out.txt`、`backend/err.txt` |

## 不允许提交的内容

- `.env`、`.env.local`、`backend/.env`。
- 真实外部 AI Key、GitHub Token、JWT secret、数据库密码、MinIO 密码。
- Docker volume：`docker/volumes/` 和任何 PostgreSQL/Redis/MinIO 数据目录。
- 备份文件：`backups/`、数据库 dump、MinIO tar 包。
- 依赖与构建产物：`backend/venv/`、`frontend/node_modules/`、`frontend/dist/`。
- 测试报告生成物：`frontend/playwright-report/`、`frontend/test-results/`。
- 日志和临时输出：`logs/`、`*.log`、`backend/out.txt`、`backend/err.txt`。

## GitHub 远程同步准备项

需要用户准备，且不要写入源码或文档：

1. GitHub 私有仓库地址，例如 `https://github.com/<owner>/<repo>.git` 或 `git@github.com:<owner>/<repo>.git`。
2. 推荐使用 SSH deploy key 或用户 SSH key；如果使用 HTTPS，则使用 fine-grained Personal Access Token。
3. Token 只需要仓库 Contents 读写权限；不要授予组织管理、Actions secrets 管理等无关权限。
4. 仓库建议设为 Private。
5. GitHub 上不要上传 `.env`，生产秘密应使用 GitHub Actions Secrets、Docker secrets、外部 secret manager 或受控服务器 `.env`。

## 后续推荐流程

1. 本地执行秘密扫描，确认无真实凭据。
2. 执行 `git status --short --ignored`，确认忽略规则生效。
3. 首次提交只包含源码、配置模板、脚本、文档和测试。
4. 添加远程 `origin`。
5. 推送 `main` 到 GitHub。
6. 后续 V1.1 改动建议通过分支和 Pull Request 管理，例如 `v1.1-pilot-readiness`。

## 当前状态

- 本地 Git 仓库已初始化。
- 远程 GitHub 尚未配置，等待用户提供仓库地址和认证方式。
- 本地首次 commit 已创建；远程配置完成后推送 `main`。

## 凭据事件

| 日期 | 事件 | 处理状态 |
| --- | --- | --- |
| 2026-07-17 | GitHub PAT 曾在交互会话中明文暴露；文档不记录其值 | 该凭据禁止继续使用，等待在 GitHub 撤销并通过 `gh auth login` 重新登录 |

安全处理要求：

- 在 GitHub `Settings -> Developer settings -> Personal access tokens` 中立即撤销已暴露 Token。
- 执行 `gh auth logout --hostname github.com` 清除本机旧登录。
- 推荐重新执行 `gh auth login --hostname github.com --web --git-protocol https`，通过浏览器设备授权登录，避免在聊天或命令参数中传递新 Token。
- 新凭据不得写入本项目文件、Git 提交、测试报告或操作记录。
