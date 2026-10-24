# RiChangPIM v1.9.5 更新包

本包用于已有生产环境从 v1.9.4 升级到 v1.9.5，只包含源码、配置模板、迁移与构建脚本，**不含业务数据、对象存储、`.env` 或任何凭据**。

## 本版改了什么

- 内容工坊生成表单：「DNA 来源」改为「创作 Skills」，选项显示 Skill 名称并浅色标注 DNA。
- 方案管理「新增方案」弹窗重排：920px 宽、顶部标签、两列栅格，明细字段改为两列网格，不再横向滚动。
- 分享页：商品列表只保留摘要列，点击行或「查看详情」弹出详情弹窗（规格/材质/颜色/材质说明/场景图）。

数据库迁移 head **不变**，仍为 `0030_content_dna_fields`；本版没有新增迁移，`alembic upgrade head` 是无操作的。

## 升级步骤

```bash
# 0. 校验外层 SHA-256
sha256sum -c RiChangPIM_update_v1.9.5_*.tar.gz.sha256

# 1. 备份（必须先做）
docker exec richangpim-postgres-1 pg_dump -U pim -Fc ai_pim > ai_pim_pre_1.9.5.dump
# MinIO 备份状态确认为 ok

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
docker exec richangpim-backend-1 alembic current      # 0030_content_dna_fields (head)
HEALTH_URL=http://127.0.0.1:888/api/v1/health ./scripts/healthcheck.sh
```

后台「系统管理 → 版本」页应显示前/后台四项元数据且「一致性检查」为「一致」。

## 回滚

保留旧镜像（`richangpim-backend:1.9.4` / `richangpim-nginx:1.9.4`）并用 `docker compose up -d --no-deps backend nginx` 回切；本版没有数据库变更，无需回滚迁移。