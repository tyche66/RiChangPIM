# Windows 开发与 WSL 构建

本文说明 2026-10-30 起本仓库的新工作区布局：**代码放在 Windows 盘，日常在 Windows 侧编辑，构建与运行在 WSL 发行版 `RiChangPIM` 内完成。**

## 一、当前布局

| 用途 | Windows | WSL（发行版 `RiChangPIM`） |
| --- | --- | --- |
| 仓库根（开发位置） | `E:\RiChangPIM` | `/mnt/e/RiChangPIM` |
| 构建 / 运行 / 测试 | — | `cd /mnt/e/RiChangPIM` 后执行 |
| 旧位置（仅回退参考） | `\\wsl$\RiChangPIM\home\AI-PIM\RiChangPIM` | `/home/AI-PIM/RiChangPIM` |
| 全量迁移包存放 | — | `/home/AI-PIM/*.tar.gz`（不进仓库，见 [MIGRATION_BUNDLE.md](../MIGRATION_BUNDLE.md)） |

`E:\RiChangPIM` 与 `/mnt/e/RiChangPIM` 是**同一份文件**的两个视图，不存在同步问题。

## 二、为什么不再把仓库放在 WSL 家目录

OpenCode / OpenChamber 在 Windows 侧把 `\\wsl$\...` 这类 UNC 路径当作项目目录时，会把 `\\wsl$\RiChangPIM\...` 规范化成 `/wsl$/RiChangPIM/...`，再按 Windows 路径解析成 `C:\wsl$\...`，于是报：

```
agent.list failed: Location not found: /wsl$/RiChangPIM/home/AI-PIM/RiChangPIM
```

把仓库放到 Windows 盘、用盘符路径打开项目即可绕开这个解析问题；WSL 通过 `/mnt/e` 正常访问和构建。

## 三、日常流程

1. **Windows 侧编辑**：用编辑器 / IDE 打开 `E:\RiChangPIM`，正常修改源码与文档。
2. **WSL 侧验证**：所有构建、测试、docker 命令都在 WSL 里执行。

```bash
wsl -d RiChangPIM
cd /mnt/e/RiChangPIM
bash scripts/where-am-i.sh        # 每次开工第一条：确认在和哪套环境说话
```

3. 构建前端产物：

```bash
cd /mnt/e/RiChangPIM
bash scripts/build_frontends.sh   # 注入版本 / BUILD_ID / GIT_COMMIT，并设 VITE_BASE_PATH=/admin/
```

4. 重建并启动生产栈：

```bash
cd /mnt/e/RiChangPIM
docker compose build && docker compose up -d
```

`dist` 是 `COPY` 进 nginx 镜像的，改完前端必须 `docker compose build nginx`；只在本机 build 不会改变 `:888` 上的内容。完整发版顺序见 [版本控制规范和Git.md](../版本控制规范和Git.md) 的「正确顺序」。

## 四、首次在新位置准备环境

依赖不随仓库迁移（`node_modules`、`venv`、`docker/volumes` 都在 `.gitignore` 里），需要在新位置重装一次。

```bash
# 后端开发环境
cd /mnt/e/RiChangPIM/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt

# 前端与门户
cd /mnt/e/RiChangPIM/frontend && npm ci
cd /mnt/e/RiChangPIM/portal   && npm ci
```

Node 版本按仓库脚本要求（`v24.18.0`，见 `e2e_round.sh` / `build_frontends.sh` 的 PATH 设置）。

运行数据（PostgreSQL / MinIO / Redis 的命名卷）由 Docker Desktop 管理，与仓库位置无关；只要卷名不变，换路径后数据仍在。

## 五、Git 与换行符

- 仓库根 `.gitattributes` 强制 `* text=auto eol=lf`，**checkout 到 Windows 与 WSL 都是 LF**，AOCI baseline 的字节比对不受平台影响。
- `core.filemode=false`，NTFS 上的权限位不会造成全仓库 `modified`。
- Windows git 与 WSL git 都能直接操作同一仓库；**任选一侧提交，不要两边同时改同一批文件**。
- 编辑器请按 LF 保存（VS Code 默认服从 `.gitattributes`）；不要手工把文件改成 CRLF 后提交。
- 换行符或权限导致异常时，先看 `git status` 与 `git diff --stat`，不要直接 `git checkout .` 覆盖未提交改动。

## 六、已知限制

1. **`/mnt/e` 的 I/O 比 WSL 原生 ext4 慢**，`npm ci`、`pip install`、`vite build` 首次会明显变慢，属正常现象。
2. **`docker/volumes` 不随仓库迁移**（650 MB 运行数据）。旧位置仍保留一份，需要时再决定是否搬。
3. **不要从 Windows 侧把 `\\wsl$\...` 或 `\\wsl.localhost\...` 当作项目根**，会重新触发 `Location not found`。项目根只用 `E:\RiChangPIM`。
4. **AOCI 认知索引**：`opencode.json` 中 aoci MCP 的 `--repo` 已改为 `/mnt/e/RiChangPIM`。迁移后若 AOCI 报告 baseline 路径漂移，按 AOCI 维护流程重新对齐，不要手工改 `.aoci` 内部文件。
5. **旧目录 `/home/AI-PIM/RiChangPIM` 暂不删除**，作为回退快照保留；确认新位置稳定后再按项目规则移入 `回收站/`。

## 七、常见问题

**Q：Windows 侧打开 `E:\RiChangPIM` 后，OpenCode 还报 `Location not found`？**
A：确认项目根是 `E:\RiChangPIM` 而不是 WSL UNC 路径；并在 OpenCode / OpenChamber 的项目列表里移除旧的 `\\wsl$\...` 项目。改完 `opencode.json` 后需要重启客户端让 MCP 配置生效。

**Q：WSL 里 `cd /mnt/e/RiChangPIM` 权限不够？**
A：WSL 默认以 root 挂载 `/mnt/e`（目录显示 `rwxrwxrwx`）。若用非 root 用户，确认 `/etc/wsl.conf` 未禁用 metadata，必要时 `sudo chown -R $USER:$USER /mnt/e/RiChangPIM`。

**Q：构建出来的版本页显示 `-dirty`？**
A：`build_frontends.sh` 用 `git status --porcelain` 判断工作区。先在 Windows 或 WSL 任一侧提交干净，再构建。
