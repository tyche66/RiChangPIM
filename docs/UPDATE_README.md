# RiChangPIM v2.0.1 更新包

本包用于已有生产环境从 `v2.0.0` 升级到 `v2.0.1`，只包含源码、配置模板、迁移与构建脚本，不含业务数据、对象存储、`.env` 或任何凭据。

## 本版改动

- **方案效果图（对外展示）**：新增 `proposal_effect_image` 绑定表与「方案效果图」管理板块，方案编辑/详情可直接上传并存媒体库；可绑定方案内某个产品或某个空间（可同时绑定，也可不绑定作为方案整体效果图）；分享页新增「效果图」板块并按 空间/产品/整体 分组；产品详情页新增只读「搭配案例」板块，连带展示绑定该产品的全部有效方案效果图；媒体库删除保护新增「方案效果图」引用提示。
- **方案内产品名称**：明细产品可填写「方案内名称」（`proposal_item.display_name`），仅服务当前方案，设置后替代产品库名称对外展示（后台与分享页附注原名）。
- **自定义产品（不入产品库）**：方案明细可添加「自定义产品」，名称/面价/图片/规格/材质/颜色/材质说明自由填写，仅在本方案对外展示；图片随方案随用随删；**自定义产品不可进入报价单**（生成报价预填时剔除并提示，接口层返回 422）。
- **已保存方案可从产品列表选品**：方案编辑新增「从产品列表选择」，跳到产品列表按分类/品牌等筛选多选后点「完成」回编辑页追加（按 `product_id` 去重）。
- **明细按楼层/空间折叠**：方案编辑明细区按楼层/空间分组折叠展示，默认全部展开，产品多时减少上下滑动。
- **修复：方案明细楼层/空间名称无法输入**：原实现连续两次更新明细数组，第二次读到异步刷新前的旧 props 把刚输入的值覆盖回空；已改为一次原子更新。
- **修复：含超大平面图的方案打开时 `Out of memory`**：平面图/效果图/产品缩略图统一走后端缩略图参数（`w=192/240/480`），实测 16.99 MB 原图 → 41.5 KB（约 1/409）并限制解码像素；全屏查看器仍用原图。
- **分享页文案**：商品行与详情弹窗不再显示「自定义产品 · 仅本方案展示」副标题（该位置留空，保留「自定义」标签）。

## 本版索引与数据字段变更

| 变更 | 承载文件 | 生效方式 | 验收方式 |
| --- | --- | --- | --- |
| `proposal_item.display_name`（方案内名称） | `backend/alembic/versions/0041_proposal_item_display_name.py` | backend 容器启动自动迁移 | `docker exec richangpim-backend-1 alembic current` 显示 `0043_proposal_item_custom_product (head)` |
| `proposal_effect_image` 表（方案效果图，含产品/空间/项目索引与活动唯一约束） | `backend/alembic/versions/0042_proposal_effect_images.py` | 自动 | 方案编辑上传并绑定产品/空间后，分享页与产品详情「搭配案例」可见 |
| `proposal_item.is_custom` + `custom_product` JSONB，`product_id` 放开非空 | `backend/alembic/versions/0043_proposal_item_custom_product.py` | 自动 | 方案明细可新增自定义产品并在分享页展示 |

本版**没有必须手动执行的数据回填**，也无新增权限码。存量部署升级后由容器入口自动执行 `alembic upgrade head`、`init_admin`、`seed_data`、`seed_default_skills --apply`、`seed_attribute_dictionary --apply`。

## 行为变化（需告知使用方）

- 方案明细可维护「方案内名称」「自定义产品」，对外分享以方案内名称为准。
- 自定义产品只在方案内展示，**不会进入报价单**；含自定义产品的报价预填会跳过并提示。
- 平面图/效果图/产品缩略图改为请求后端缩略图（`w` 参数），全屏查看仍为原图；分享页效果图/平面图缩略图同样使用缩略图。

## 升级步骤

1. 运行 `bash scripts/where-am-i.sh`，确认目标是生产 Compose 栈。
2. 升级前备份 PostgreSQL 与 MinIO，并确认备份成功；不要用连接宿主机 `localhost:5432` 的默认脚本替代生产容器备份。
3. 本包包含迁移 `0041_proposal_item_display_name`、`0042_proposal_effect_images`、`0043_proposal_item_custom_product`，backend entrypoint 会在启动时自动执行。
4. 构建前端：
   ```bash
   export PATH="$HOME/.nvm/versions/node/v24.18.0/bin:$PATH"
   bash scripts/build_frontends.sh
   ```
   记录输出的 `APP_VERSION`、`BUILD_ID`、`GIT_COMMIT`、`BUILD_TIME`。
5. 导出同一组构建元数据，设置 `APP_VERSION=2.0.1`、`APP_ENV=production`，执行：
   ```bash
   docker compose build backend nginx
   docker compose up -d --no-deps backend nginx
   ```
6. 校验迁移与版本：
   ```bash
   docker exec richangpim-backend-1 alembic current
   curl -s --noproxy '*' http://127.0.0.1:888/api/v1/health
   ```
7. 登录后台「系统管理 → 版本」页，确认前后端版本 / 构建 ID / Git commit / 北京时间四项齐全且一致；再验收：方案编辑上传效果图并绑定产品/空间、分享页效果图分组、产品详情「搭配案例」、方案内名称、自定义产品、从产品列表选品、明细折叠。

## 配置与回滚

- 本版不新增环境变量。
- 回滚代码前保留旧 backend/nginx 镜像；迁移回滚会删除 `proposal_effect_image` 表并移除 `display_name` / `is_custom` / `custom_product` 字段，请先确认不再需要效果图与自定义产品数据。
- 缩略图依赖 MinIO 中的 `derived/thumb/**` 生成结果，首次访问会按需生成；回滚到旧前端不影响原图地址。

## 已知问题

- 新增的效果图与自定义产品为方案级展示物料，不参与报价与成本计算。
- AI 查询依赖外部模型服务；若上游超时，门户会停留在处理中，与本版代码无关。
- 门户登录页视频来自外部 CDN；网络不可达时左侧回落深蓝背景，登录功能不受影响。
