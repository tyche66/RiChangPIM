# RiChangPIM v1.9.5 更新包

本包用于已有生产环境从 v1.9.4 升级到 v1.9.5，只包含源码、配置模板、迁移与构建脚本，**不含业务数据、对象存储、`.env` 或任何凭据**。

## 本版改了什么

- **AI 配置中心**（`AI 功能 → AI 配置中心`，仅管理员）：选品检索与内容工坊两个域的 API 地址、API Key、对话模型 ID、可选模型列表、嵌入模型与超时改为后台可维护；数据库覆盖优先、留空回落环境变量，保存后约 15 秒生效，无需重启后端。
- **内容生成质量**：内容工坊两套 DNA 与独立选题提示词重写，写作规则前置、合规规则改为后台执行；产品事实从 3 个字段扩展到 12 个（含受治理属性），价格/库存/供应商等隐私字段一律不进外部提示词。
- 迁移 `0031_ai_provider_config`：新建 `ai_provider_config` 表并插入 `ai:config` 权限码（仅 admin）。

## 发布后修复（已并入本包）

- **迁移 0031 列名错误**：原版向 `permission` 插入 `ai:config` 时使用了不存在的 `code`/`name` 列，会导致 backend 容器启动即退出；已改为真实的 `perm_code`/`perm_name`。若在本包之前升级过并遇到 backend 反复重启，升级后即可恢复。
- **AI 配置中心页面空白**：前端响应多读了一层 envelope，页面只剩标题和刷新按钮；已修正。
- **发布后白屏（须刷新才好）**：nginx 原本不发送任何 `Cache-Control`，浏览器会 heuristic 缓存旧 `index.html`，代码更新后它引用的旧内容哈希 chunk 已不存在从而 404。本包起入口 HTML 一律 `no-cache`（每次重新校验），带内容哈希的 `/admin/assets/` 与 `/assets/` 为长缓存 `immutable`。升级后首次访问如遇白屏，强制刷新一次即可，之后不会再出现。

数据库迁移 head 从 `0030_content_dna_fields` 前进到 `0031_ai_provider_config`；生产库会沿单步幂等升级。

## 升级步骤

```bash
# 0. 校验外层 SHA-256
sha256sum -c RiChangPIM_update_v1.9.5_*.tar.gz.sha256

# 1. 备份（必须先做）
docker exec richangpim-postgres-1 pg_dump -U pim -Fc ai_pim > ai_pim_pre_1.9.5.dump
# MinIO 备份状态确认 ok

# 2. 解压并核对源码基线
tar -xzf RiChangPIM_update_v1.9.5_*.tar.gz
cat RiChangPIM/UPDATE_MANIFEST.txt

# 3. 构建前端（注入版本与构建元数据）
export PATH="/root/.nvm/versions/node/v24.18.0/bin:$PATH"
cd RiChangPIM
bash scripts/build_frontends.sh
#    记下输出的 APP_VERSION / BUILD_ID / GIT_COMMIT / BUILD_TIME

# 4. 构建并切换容器
export APP_VERSION=1.9.5 BUILD_ID=<上一步> GIT_COMMIT=<上一步> BUILD_TIME=<上一步> APP_ENV=production
docker compose build backend nginx
docker compose up -d --no-deps backend nginx

# 5. 验收
docker exec richangpim-backend-1 alembic current      # 0031_ai_provider_config (head)
docker exec richangpim-backend-1 python -m app.scripts.seed_data --check
```

## 升级后的配置说明

- AI 配置是**覆盖层**：升级后不填任何值，系统行为与 v1.9.4 完全一致（继续读环境变量）。
- 需要在后台维护时：管理员进入 `AI 功能 → AI 配置中心`，填写目标域并保存；密钥只在保存时写入，读取只显示掩码。
- 关闭某个域的「启用数据库配置」开关即可立即回落环境变量，数据库中的值保留。
- 若曾在「Skills 管理」里手动改过内置 Skill 提示词，`python -m app.scripts.seed_default_skills --refresh --check` 可查看将被代码模板刷新的字段，确认后再 `--refresh --apply`。
