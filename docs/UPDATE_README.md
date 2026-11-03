# RiChangPIM v2.0.0 更新包

本包用于已有生产环境升级到 `v2.0.0`，只包含源码、配置模板、迁移与构建脚本，不含业务数据、对象存储、`.env` 或任何凭据。

## 本版改动

- **门户视觉与登录**：门户浅色主题切换到 `#EDEBE6` 背景、`#F4F2ED` 弱填充与 `#1F3FB0` 强调色；页眉改为非吸顶 + 2px 深色装饰线；后台与门户登录页统一为视频分栏设计，登录后分别进入后台/门户。
- **分享页图片画廊**：新增通用 `ImageViewer`，商品主图与场景图统一全屏浏览、缩放、拖拽、键盘切换；修复全屏图片底部被文档流裁切的问题；过期图片有明确兜底。
- **方案创建/编辑统一页面**：新增 `/proposals/create`、`/proposals/:id/edit`，原弹窗入口改为跳转；商品明细支持 4/2/1 列响应式布局；编辑页提供只读平面图卡与 `#floor-plans` 跳转。
- **分享链接复用**：方案详情页新增「分享链接」卡片，展示最近一次分享的链接、二维码、有效期、访问次数与密码状态，支持复制、预览和下载二维码。新增 `GET /api/v1/shares/target/{share_type}/{target_id}`（`share:view`）。
- **全局设置**：新增单行表 `system_setting` 与管理员设置页，覆盖品牌文案、Logo、分享缺省值、报价默认税率、金额小数位与货币符号；门户公共品牌接口与 Logo 强缓存端点。
- **公告**：新增 `announcement` 表、管理页、匿名 `/active` 接口与后台/门户弹窗；支持受众、级别、启停、定时发布与过期，已读状态存浏览器；分享页不弹公告。
- **方案效果图（对外展示）**：新增 `proposal_effect_image` 绑定表与「方案效果图」管理板块，方案编辑/详情可直接上传并存媒体库；可绑定方案内某个产品或某个空间（可同时绑定，也可不绑定作为方案整体效果图）；分享页新增「效果图」板块并按 空间/产品/整体 分组；产品详情页新增只读「搭配案例」板块，连带展示绑定该产品的全部有效方案效果图；媒体库删除保护新增「方案效果图」引用提示。
- **方案内产品名称**：明细产品可填写「方案内名称」（`proposal_item.display_name`），仅服务当前方案，设置后替代产品库名称对外展示（分享页只显示方案内名称，后台与分享页附注原名）。
- **自定义产品（不入产品库）**：方案明细可添加「自定义产品」，名称/面价/图片/规格/材质/颜色/材质说明自由填写，仅在本方案对外展示；图片随方案随用随删；自定义产品不可进入报价单。
- **已保存方案可从产品列表选品**：方案编辑新增「从产品列表选择」，跳到产品列表按分类/品牌等筛选多选后点「完成」回编辑页追加（按 product_id 去重）。
- **明细按楼层/空间折叠**：方案编辑明细区按楼层/空间分组折叠展示，产品多时减少上下滑动。
- **后台菜单**：「分享管理」从系统管理移入销售板块，销售板块更名为「销售工作台」。
- **结果页**：桌面查询结果 ≥80vw；逐项比较使用双轴滚动、粘性表头/首列与常驻横向滚动条；引用来源默认折叠并在桌面端使用卡片网格；回答与比较面板去掉外边框。

## 本版索引与数据字段变更

| 变更 | 承载文件 | 生效方式 | 验收方式 |
| --- | --- | --- | --- |
| `system_setting` 单行表 + 默认值 | `backend/alembic/versions/0039_system_setting.py` | backend 容器启动自动迁移 | `docker exec richangpim-backend-1 alembic current` 显示 `0043_proposal_item_custom_product (head)` |
| `announcement` 表 | `backend/alembic/versions/0040_announcement.py` | 自动 | 后台「系统管理 → 公告管理」可新建并下发 |
| `proposal_item.display_name`（方案内名称） | `0041_proposal_item_display_name.py` | 自动 | 明细填方案内名称后分享页显示新名并附原名 |
| `proposal_effect_image` 表（方案效果图） | `0042_proposal_effect_images.py` | 自动 | 方案编辑上传并绑定产品/空间，分享页/产品详情可见 |
| `proposal_item.is_custom` + `custom_product`（自定义产品） | `0043_proposal_item_custom_product.py` | 自动 | 方案明细新增自定义产品，分享页可见 |
| `setting:view` / `setting:edit` / `announcement:view` / `announcement:manage` | `backend/app/scripts/seed_data.py` | backend entrypoint 自动执行 `seed_data` | 管理员登录后令牌含四个权限；非管理员不可访问 |
| 方案详情分享查询接口 | `backend/app/api/v1/shares.py` | 代码随包发布 | 方案详情页显示已有链接/二维码 |

本版**没有必须手动执行的数据回填**。存量部署升级后由容器入口自动执行 `alembic upgrade head`、`init_admin`、`seed_data`、`seed_default_skills --apply`、`seed_attribute_dictionary --apply`。

## 行为变化（需告知使用方）

- **分享默认有效期统一为 24 小时**：直接调用 `POST /api/v1/shares` 且不传 `expire_hours` 时，默认值由 7 天变为 24 小时。
- 新建报价单未显式传 `tax_rate` 时读取全局设置 `quotation_default_tax_rate`。
- 门户与后台登录页改为同一视觉，登录后的落点分别保持门户 `/chat` 与后台 `/products`。

## 升级步骤

1. 运行 `bash scripts/where-am-i.sh`，确认目标是生产 Compose 栈。
2. 升级前备份 PostgreSQL 与 MinIO，并确认备份成功；不要用连接宿主机 `localhost:5432` 的默认脚本替代生产容器备份。
3. 本包包含迁移 `0039_system_setting`、`0040_announcement`，backend entrypoint 会在启动时自动执行。
4. 构建前端：
   ```bash
   export PATH="$HOME/.nvm/versions/node/v24.18.0/bin:$PATH"
   bash scripts/build_frontends.sh
   ```
   记录输出的 `APP_VERSION`、`BUILD_ID`、`GIT_COMMIT`、`BUILD_TIME`。
5. 导出同一组构建元数据，设置 `APP_VERSION=2.0.0`、`APP_ENV=production`，执行：
   ```bash
   docker compose build backend nginx
   docker compose up -d --no-deps backend nginx
   ```
6. 校验迁移与权限：
   ```bash
   docker exec richangpim-backend-1 alembic current
   docker exec richangpim-backend-1 python -m app.scripts.seed_data --check
   ```
7. 健康检查与验收：
   ```bash
   curl -s --noproxy '*' http://127.0.0.1:888/api/v1/health
   ```
   登录后台检查「版本」页前后端版本/构建 ID/Git commit/北京时间一致；再验收设置读写、Logo 更新、公告受众与弹窗、分享链接复用、分享页画廊、方案新建/编辑。

## 配置与回滚

- 新增设置项保存在数据库 `system_setting`，无需新增环境变量。
- 回滚代码前保留旧 backend/nginx 镜像；迁移回滚会删除 `announcement` 与 `system_setting`，请先确认不再需要公告/设置数据。
- 深色主题本期保持原有配色与吸顶页眉，不应用 `#1F3FB0`。
- 公共设置接口只返回品牌字段；门户分享页金额展示在未下发业务字段时回落 `¥`/2 位。

## 已知问题

- AI 查询依赖外部模型服务；若上游超时，门户会停留在处理中，与本版代码无关。
- 门户登录页视频来自外部 CDN；网络不可达时左侧回落深蓝渐变背景，登录功能不受影响。
