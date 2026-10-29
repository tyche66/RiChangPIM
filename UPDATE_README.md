# RiChangPIM v1.9.7 更新包

本包用于已有生产环境从 v1.9.6 升级到 v1.9.7，只包含源码、配置模板、迁移与构建脚本，不含业务数据、对象存储、`.env` 或任何凭据。

## 本版改动

- **方案平面图**：新增 `proposal_floor_plan` 表及迁移 `0032_proposal_floor_plans`，图片本体仍由媒体库和 MinIO 管理；增加方案平面图 API、后台维护界面、媒体引用保护和分享页缩放查看器。
- **销售角色媒体权限**：迁移 `0033_sales_media_permissions` 为 `sales` 增加 `media:view` 和 `media:upload`，不授予删除或替换权限。
- **产品包重传**：新增零写入预检和单次消费的提交流程，支持覆盖、追加、跳过；覆盖会保存可恢复的 JSON 快照。
- **导入合并规则**：覆盖时未填写的单元格保留现值，追加只填充空值；图片替换与追加分开处理，标签可按单元格类型或预检默认类型创建。

## 升级步骤

1. 运行 `scripts/where-am-i.sh`，确认目标是生产 Compose 栈。
2. 升级前备份 PostgreSQL 和 MinIO，并确认两份备份成功。生产 PostgreSQL 使用容器内 `pg_dump`，不要使用连接宿主机 `localhost:5432` 的备份脚本默认配置。
3. 发布源码包含迁移 `backend/alembic/versions/0032_proposal_floor_plans.py` 和 `0033_sales_media_permissions.py`。backend entrypoint 会在容器启动时自动升级数据库；本版没有需要手动执行的数据回填。
4. 使用 `PATH="$HOME/.nvm/versions/node/v24.18.0/bin:$PATH" bash scripts/build_frontends.sh` 构建两个前端，并记录其输出的 `APP_VERSION`、`BUILD_ID`、`GIT_COMMIT`、`BUILD_TIME`。
5. 将同一组构建元数据导出给 Compose，设置 `APP_VERSION=1.9.7`、`APP_ENV=production`，然后执行 `docker compose build backend nginx` 和 `docker compose up -d --no-deps backend nginx`。不要重启 worker、knowledge-indexer、数据库或对象存储。
6. 执行 `docker exec richangpim-backend-1 alembic current`，确认 `0033_sales_media_permissions (head)`；执行 `docker exec richangpim-backend-1 python -m app.scripts.seed_data --check`。
7. 运行健康检查，登录后台验证「系统管理 → 版本」中的前后端版本、构建 ID、Git commit、北京时间构建时间均有值且一致；验证产品包预检与提交、方案平面图权限及分享页展示。

## 配置与回滚说明

- 导入预检暂存目录默认是 `/tmp/pim_import_staging`，有效期默认 7200 秒；预检 token 只能提交一次。
- 保留旧 backend 和 nginx 镜像，直到生产验收完成。迁移回滚会删除平面图关系记录；评估数据保留要求后再回滚。删除平面图绑定不会删除 MinIO 图片对象。
