# RiChangPIM v1.9.8 更新包

本包用于已有生产环境从 v1.9.7 升级到 v1.9.8，只包含源码、配置模板、迁移与构建脚本，不含业务数据、对象存储、`.env` 或任何凭据。

## 本版改动

- **产品列表三级筛选导航**：新增 `GET /api/v1/products/filter-options`，六个维度（系列 / 品牌 / 供应商 / 状态 / 库存 / 品类）的二级、三级选项与计数全部由产品数据实时聚合；「系列」三级取系列标签，「品类」三级取规格长度，两个维度数据源独立。产品列表与导出新增 `tag_type`、`spec_length_mm` 参数，分类筛选包含全部后代分类。
- **产品交货期**：新增 `product.delivery_period`，导入模板 / 导出列 / 列表 / 详情 / 编辑表单同步，打通「导出 → 改 → 导回」。
- **知识索引自动重建**：产品增改删、图片变更、批量导入、说明书上传 / 解析 / OCR / 删除均自动登记索引任务；产品卡片新增类目路径、交货期与外观标签。
- **产品图视觉标注（可选）**：新增多模态标注器与 `ai_provider_config.vision_model` 配置；不配置视觉模型时整条链路自动跳过，不影响索引。
- **详情页与门户**：产品详情页新增大图 hero + 灯箱；门户比较表新增主图列、MD 导出与 PDF 导出接口。

## 本版索引与数据字段变更

| 变更 | 承载文件 | 生效方式 | 验收方式 |
| --- | --- | --- | --- |
| `product.delivery_period`（新列） | `backend/alembic/versions/0036_product_delivery_period_vision_tags.py` | 随 backend 容器启动自动迁移 | `docker exec richangpim-backend-1 alembic current` 显示 `0036_... (head)` |
| `product_image.vision_tags`（新列，JSONB） | 同上 | 自动 | 同上；`information_schema.columns` 可查到 |
| `ai_provider_config.vision_model`（新列） | 同上 | 自动 | 同上 |
| `knowledge_chunk` 唯一索引改为仅约束未删除行 | `backend/alembic/versions/0035_knowledge_chunk_partial_unique.py` | 自动 | `pg_indexes` 中 `idx_knowledge_chunk_document_index` 含 `is_deleted = false` |
| `user.token_version`（0034，前次遗留） | `backend/alembic/versions/0034_user_token_version.py` | 自动 | 迁移 head 为 0036 即包含 |
| 既有产品的索引卡片刷新（含新字段与视觉标签） | `backend/app/scripts/knowledge_indexer.py` | **手动、可选** | 见下方第 6 步 |

本版**没有必须执行的数据回填**：视觉标签在卡片重建时按需生成，未配置 `vision_model` 时自动跳过。
若希望存量产品也带上新字段与外观标签，可在升级后手动跑一次卡片重建（会消耗 embedding / 视觉调用额度）：

```bash
docker exec richangpim-backend-1 python -m app.scripts.knowledge_indexer --once
```

## 升级步骤

1. 运行 `scripts/where-am-i.sh`，确认目标是生产 Compose 栈。
2. 升级前备份 PostgreSQL 和 MinIO，并确认两份备份成功。生产 PostgreSQL 使用容器内 `pg_dump`，不要使用连接宿主机 `localhost:5432` 的备份脚本默认配置。
3. 发布源码包含迁移 `0034_user_token_version`、`0035_knowledge_chunk_partial_unique`、`0036_product_delivery_period_vision_tags`。backend entrypoint 会在容器启动时自动升级数据库。
4. 使用 `PATH="$HOME/.nvm/versions/node/v24.18.0/bin:$PATH" bash scripts/build_frontends.sh` 构建两个前端，并记录其输出的 `APP_VERSION`、`BUILD_ID`、`GIT_COMMIT`、`BUILD_TIME`。
5. 将同一组构建元数据导出给 Compose，设置 `APP_VERSION=1.9.8`、`APP_ENV=production`，然后执行 `docker compose build backend nginx` 和 `docker compose up -d --no-deps backend nginx`。不要重启 worker、knowledge-indexer、数据库或对象存储。
6. （可选）如需刷新存量产品的知识卡片：`docker exec richangpim-backend-1 python -m app.scripts.knowledge_indexer --once`；它只处理「卡片缺失或已过期」的产品，不会逐条重刷全部 4000+ 产品。
7. 执行 `docker exec richangpim-backend-1 alembic current`，确认 `0036_product_delivery_period_vision_tags (head)`；执行 `docker exec richangpim-backend-1 python -m app.scripts.seed_data --check`。
8. 运行健康检查，登录后台验证「系统管理 → 版本」中的前后端版本、构建 ID、Git commit、北京时间构建时间均有值且一致；再验证产品列表三级筛选（系列 / 品类三级数据不同源）、交货期展示与导入模板、门户比较表的 MD / PDF 导出。

## 配置与回滚说明

- 若启用产品图视觉标注：在「AI 配置中心 → 知识库域」填「视觉标注模型 ID」，或设置环境变量 `AI_VISION_MODEL`；必须是支持图片输入的多模态模型，纯文本模型会让索引任务失败。留空即关闭。
- 保留旧 backend 和 nginx 镜像，直到生产验收完成。迁移回滚会删除本版新增的三列与部分唯一索引；`knowledge_chunk` 索引回滚在存在同位软删除历史行时会失败并整体回滚，属预期保护。
- 已知问题（本版未修）：`backend/app/knowledge/tools/product.py` 的规格数值表达式使用 `func.instr`，PostgreSQL 无此函数，AI 选品按「长度 / 宽 / 高」排序或过滤时会报错。后台产品筛选已绕开该表达式，如需修复请单独安排。
