# RiChangPIM v1.9.4 更新包

本包用于已有生产环境从 v1.9.3 升级到 v1.9.4，只包含源码、配置模板、迁移与构建脚本，**不含业务数据、对象存储、`.env` 或任何凭据**。

## 本版改了什么

- 产品属性检索：受治理属性词典 + `product.search` 硬过滤（桌形只匹配桌形，不靠描述文本冒充）。
- 内容 Skills 与独立选题：Skills 管理中心（仅 admin）、两套 DNA 派生 4 个 operational Skill、模型白名单。
- 方案与客户展示：楼层/空间自由输入与快照、报价 PDF 新增列、分享页按空间展示材质/颜色。
- 界面修复：内容工坊「DNA 来源」改为「创作 Skills」；「新增方案」弹窗重排（920px、顶部标签、两列栅格、明细字段网格）；分享页商品列表改为摘要 + 点击查看详情弹窗（规格/材质/颜色/材质说明/场景图）。

数据库迁移 head 从 `0024_attachment_biz_domain_compat` 前进到 `0030_content_dna_fields`；生产库（现 `0024`）会沿 `0025 → … → 0030` 连续幂等升级。

## 升级步骤

```bash
# 0. 校验外层 SHA-256
sha256sum -c RiChangPIM_update_v1.9.4_*.tar.gz.sha256

# 1. 备份（必须先做）
docker exec richangpim-postgres-1 pg_dump -U pim -Fc ai_pim > ai_pim_pre_1.9.4.dump
# MinIO 备份状态确认 ok

# 2. 解压并核对源码基线
tar -xzf RiChangPIM_update_v1.9.4_*.tar.gz
cat RiChangPIM/UPDATE_MANIFEST.txt

# 3. 构建前端（注入版本与构建元数据）
export PATH="/root/.nvm/versions/node/v24.18.0/bin:$PATH"
cd RiChangPIM
bash scripts/build_frontends.sh
#    记下输出的 APP_VERSION / BUILD_ID / GIT_COMMIT / BUILD_TIME

# 4. 构建并切换容器
export APP_VERSION=1.9.4 BUILD_ID=<上一步> GIT_COMMIT=<上一步> BUILD_TIME=<上一步> APP_ENV=production
docker compose build backend nginx
docker compose up -d --no-deps backend nginx

# 5. 验收
docker exec richangpim-backend-1 alembic current      # 0030_content_dna_fields (head)
HEALTH_URL=http://127.0.0.1:888/api/v1/health ./scripts/healthcheck.sh
```

后台「系统管理 → 版本」页应显示前/后台四项元数据且「一致性检查」为「一致」。

## 回滚

本版有数据库迁移，回滚应用前先评估数据兼容性；保留旧镜像并用 `docker compose up -d --no-deps backend nginx` 回切，必要时按 `docs/云端更新包.md` 的迁移回滚章节处理。