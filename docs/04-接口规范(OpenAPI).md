# 04 - 接口规范（OpenAPI）

> 本文档定义 AI-PIM 当前 RESTful API 业务契约。实际路由以运行中的 FastAPI `/openapi.json` 为机器可读基准；本文补充认证、权限、错误处理、SSE 和存储约束。
> FastAPI 运行时会在 `/openapi.json` 自动生成机器可读的 OpenAPI 3.0 规范，本文档为人工契约定义，两者须保持一致。

---

## 一、通用规范

### 1.1 基础约定

| 项目 | 规范 |
| --- | --- |
| 协议 | 本机 Compose 验收为 HTTP `:888`；公网部署由上游 TLS 终止层提供 HTTPS |
| 风格 | RESTful |
| 版本 | URL 路径版本 `/api/v1/` |
| 数据格式 | JSON（`Content-Type: application/json`） |
| 字符编码 | UTF-8 |
| 时间格式 | ISO 8601（`2026-07-12T10:00:00+08:00`） |
| 鉴权 | JWT Bearer Token（`Authorization: Bearer <token>`） |
| 分享页鉴权 | ShareToken（无需 JWT，通过 token/密码校验） |

### 1.2 命名规范

- URL 路径：小写 + 连字符（kebab-case），资源名用复数
- 请求/响应字段：以当前 Pydantic schema 为准，业务字段主要使用 snake_case
- 枚举值：小写 + 下划线（snake_case）

### 1.3 HTTP 方法语义

| 方法 | 语义 | 示例 |
| --- | --- | --- |
| GET | 查询（列表/详情） | `GET /api/v1/products` |
| POST | 创建 | `POST /api/v1/products` |
| PUT | 全量更新 | `PUT /api/v1/products/{id}` |
| PATCH | 局部更新 | `PATCH /api/v1/products/{id}/status` |
| DELETE | 软删除 | `DELETE /api/v1/products/{id}` |

---

## 二、统一响应结构

### 2.1 标准响应

```json
{
  "code": 200,
  "msg": "success",
  "data": { ... }
}
```

### 2.2 分页响应

```json
{
  "code": 200,
  "msg": "success",
  "data": {
    "list": [ ... ],
    "total": 142,
    "page": 1,
    "size": 20
  }
}
```

### 2.3 分页参数约定

所有列表接口统一支持以下 Query 参数：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| page | int | 1 | 页码，从 1 开始 |
| size | int | 20 | 每页条数，最大 100 |
| keyword | string | - | 关键词模糊匹配 |
| sort | string | create_time | 排序字段 |
| order | string | desc | asc / desc |

### 2.4 错误响应

```json
{
  "code": 40002,
  "msg": "产品编号已存在",
  "data": null,
  "errors": [
    { "field": "product_no", "message": "编号 P001 已存在" }
  ]
}
```

---

## 三、标准错误码

| 错误码 | HTTP Status | 说明 |
| --- | --- | --- |
| 200 | 200 | 成功 |
| 40001 | 400 | 请求参数错误 |
| 40002 | 400 | 参数校验失败（含字段级详情） |
| 40101 | 401 | 未登录 / Token 无效 |
| 40102 | 401 | Token 已过期 |
| 40301 | 403 | 无权限访问该资源 |
| 40302 | 403 | 字段级权限拦截（如销售查看成本价） |
| 40303 | 403 | 分享访问次数已用完 |
| 40304 | 403 | 分享访问密码错误 |
| 40401 | 404 | 资源不存在 |
| 40901 | 409 | 资源冲突（如编号重复） |
| 42201 | 422 | 业务规则校验失败（如报价单已确认不可改） |
| 42901 | 429 | 请求限流（Redis 令牌桶触发） |
| 50001 | 500 | 服务端内部错误 |
| 50201 | 502 | 下游 AI 引擎不可用 |
| 50301 | 503 | 服务暂不可用（降级中） |

---

## 四、接口总览（运行时 OpenAPI 为准）

| 模块 | 当前覆盖范围 | 核心路径 |
| --- | --- | --- |
| 健康检查 | health、live、ready | `/api/v1/health`、`/health/live`、`/health/ready` |
| 鉴权 | 5 | `/api/v1/auth/*` |
| 用户管理 | 5 | `/api/v1/users` |
| 角色权限 | 4 | `/api/v1/roles`, `/api/v1/permissions` |
| 产品管理 | 9 | `/api/v1/products` |
| 分类管理 | 4 | `/api/v1/categories` |
| 品牌管理 | 4 | `/api/v1/brands` |
| 供应商管理 | 4 | `/api/v1/suppliers` |
| 标签管理 | 4 | `/api/v1/tags` |
| 方案管理 | 6 | `/api/v1/proposals` |
| 报价管理 | 5 | `/api/v1/quotations` |
| 分享管理 | 4 | `/api/v1/shares`, `/api/v1/share/{token}` |
| 文件管理 | 5 | `/api/v1/files` |
| AI 与待确认动作 | `/ai/*`、`/ai/actions/*` | `/api/v1/ai/*` |
| Knowledge Gateway | 查询与来源 | `/api/v1/knowledge/*` |
| 文件、说明书、场景图 | 媒体、解析、缩略图 | `/api/v1/files/*`、`/manuals/*`、`/scene-images/*` |
| 审计、观测、版本 | 日志、指标、运行状态 | `/api/v1/audit/*`、`/metrics`、`/ops/status`、`/version` |

接口数量不在人工文档中固定维护，发布验收必须同时检查 `/openapi.json` 与本文新增业务说明。

---

## 五、健康检查与鉴权模块

### 5.0 健康检查

```
GET /api/v1/health
```

> 无需鉴权。用于部署验证、容器健康探针、负载均衡健康检查。

**Response:**

```json
{
  "code": 200,
  "data": {
    "status": "healthy",
    "version": "1.0.0",
    "components": {
      "database": "up",
      "redis": "up",
      "minio": "up"
    }
  }
}
```

### 5.1 登录

```
POST /api/v1/auth/login
```

**Request Body:**

```json
{
  "username": "admin",
  "password": "admin123"
}
```

**Response:**

```json
{
  "code": 200,
  "data": {
    "token": "eyJhbGciOiJIUzI1NiIs...",
    "refresh_token": "rf_8f3b2e1c...",
    "expires_in": 7200,
    "user": {
      "user_id": "0192_7c8a...",
      "username": "admin",
      "role_code": "admin",
      "role_name": "系统管理员"
    }
  }
}
```

### 5.2 刷新 Token

```
POST /api/v1/auth/refresh
```

**Request Body:**

```json
{ "refresh_token": "rf_8f3b2e1c..." }
```

**Response:** 同 5.1，返回新的 token 与 refresh_token。

### 5.3 登出

```
POST /api/v1/auth/logout
```

> 将当前 token 加入 Redis 黑名单，立即失效。无需 Request Body。

### 5.4 获取当前用户信息

```
GET /api/v1/auth/me
```

**Response:**

```json
{
  "code": 200,
  "data": {
    "user_id": "0192_7c8a...",
    "username": "admin",
    "email": "admin@example.com",
    "phone": "13800000000",
    "role_code": "admin",
    "permissions": ["product:read", "product:write", "cost_price:read"]
  }
}
```

### 5.5 修改密码

```
POST /api/v1/auth/change-password
```

**Request Body:**

```json
{
  "old_password": "admin123",
  "new_password": "newPass456"
}
```

---

## 六、用户管理

### 6.1 用户列表

```
GET /api/v1/users
```

| Query 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| role_id | UUID | 否 | 按角色筛选 |
| status | string | 否 | active / disabled |
| page / size | int | 否 | 分页 |

### 6.2 用户详情

```
GET /api/v1/users/{id}
```

### 6.3 创建用户

```
POST /api/v1/users
```

**Request Body:**

```json
{
  "username": "sales01",
  "password": "init123456",
  "email": "sales01@example.com",
  "phone": "13800000001",
  "role_id": "0192_role_sales..."
}
```

### 6.4 更新用户

```
PUT /api/v1/users/{id}
```

**Request Body:**（除 username 外均可改）

```json
{
  "email": "new@example.com",
  "phone": "13900000001",
  "role_id": "0192_role_purchaser...",
  "status": "active"
}
```

### 6.5 删除用户（软删除）

```
DELETE /api/v1/users/{id}
```

---

## 七、角色权限

### 7.1 角色列表

```
GET /api/v1/roles
```

**Response:**

```json
{
  "code": 200,
  "data": {
    "list": [
      {
        "role_id": "0192...",
        "role_name": "销售",
        "role_code": "sales",
        "description": "可查看产品、生成方案报价",
        "permission_count": 28
      }
    ]
  }
}
```

### 7.2 创建角色

```
POST /api/v1/roles
```

**Request Body:**

```json
{
  "role_name": "区域销售",
  "role_code": "regional_sales",
  "description": "区域销售负责人",
  "permission_ids": ["0192_perm_1...", "0192_perm_2..."]
}
```

### 7.3 更新角色权限

```
PUT /api/v1/roles/{id}
```

**Request Body:**

```json
{
  "role_name": "区域销售",
  "permission_ids": ["0192_perm_1...", "0192_perm_3..."]
}
```

### 7.4 权限列表

```
GET /api/v1/permissions
```

| Query 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| resource | string | 否 | 按资源筛选（如 product） |
| type | string | 否 | menu / button / api / field |

---

## 八、产品管理

### 8.1 产品多维检索

```
GET /api/v1/products
```

| Query 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| category_id | UUID | 否 | 分类 ID |
| tag_ids | string | 否 | 标签 ID 逗号分隔（如 `id1,id2`） |
| keyword | string | 否 | 关键词（产品名/编号模糊匹配） |
| brand_id | UUID | 否 | 品牌 ID |
| supplier_id | UUID | 否 | 供应商 ID |
| status | string | 否 | active / inactive / draft |
| stock_status | string | 否 | in_stock / out_of_stock / preorder |
| min_price | number | 否 | 最低面价 |
| max_price | number | 否 | 最高面价 |
| page / size | int | 否 | 分页 |

**Response:**

```json
{
  "code": 200,
  "data": {
    "list": [
      {
        "product_id": "0192_p99823",
        "product_no": "P-X1-001",
        "product_name": "智能全自动会议终端 X1",
        "brand_name": "科技前沿",
        "category_name": "会议终端",
        "face_price": 8800.00,
        "cost_price": 6200.00,
        "stock_status": "in_stock",
        "status": "active",
        "tags": ["现代简约", "中型会议室"]
      }
    ],
    "total": 142,
    "page": 1,
    "size": 20
  }
}
```

> 注：销售角色请求时，`cost_price` 字段由响应序列化层自动过滤（返回 null 或不返回该字段）。

### 8.2 产品详情

```
GET /api/v1/products/{id}
```

**Response:** 包含完整产品信息 + 图片列表 + 说明书列表 + 标签列表。

### 8.3 创建产品

```
POST /api/v1/products
```

**Request Body:**

```json
{
  "product_no": "P-X1-001",
  "product_name": "智能全自动会议终端 X1",
  "brand_id": "0192_brand_1...",
  "supplier_id": "0192_supp_1...",
  "category_id": "0192_cat_1...",
  "face_price": 8800.00,
  "cost_price": 6200.00,
  "material": "铝合金",
  "stock_status": "in_stock",
  "status": "draft",
  "tag_ids": ["0192_tag_1...", "0192_tag_2..."]
}
```

### 8.4 更新产品

```
PUT /api/v1/products/{id}
```

### 8.5 删除产品（软删除）

```
DELETE /api/v1/products/{id}
```

### 8.6 产品上下架

```
PATCH /api/v1/products/{id}/status
```

**Request Body:**

```json
{ "status": "active" }
```

### 8.7 产品克隆

```
POST /api/v1/products/{id}/clone
```

> 复制产品基础信息（不含编号、附件、向量），生成 draft 状态副本，返回新产品 ID。

### 8.8 批量导入产品（含产品图 / 场景图）

```
POST /api/v1/products/import?skipIfExists=false
```

> `multipart/form-data`，字段 `file`；需 `product:import` 权限。上传形态二选一：
>
> - **`.xlsx` / `.xlsm`**：表格里贴着的图片也会被识别 —— WPS 的「嵌入单元格」（`DISPIMG`）、Excel 365 的「置于单元格内」（richValue）、压在某一行上的浮动图片，按图片落在哪一列决定归属；
> - **`.zip`**：一个表格 + 一批图片文件。格里写图片文件名即可，或者干脆不写 —— 文件名以产品编号开头的图（`SUNON-001.jpg`、`SUNON-001_2.jpg`）自动归到该行，名字里带「场景 / scene / 效果图 / 实景」的进场景图。
>
> 图片列为 `主图`（第一张设为封面）、`产品图`、`场景图`。第三种给法「格里写 `http(s)` 直链」默认关闭（服务端替用户抓任意地址即 SSRF），要开由管理员置 `PRODUCT_IMPORT_ALLOW_URL_FETCH=true`，开启后每一跳都校验解析出的 IP 必须是公网地址。
>
> 同一张图（按 sha256）全批只上传一次、只建一条 `attachment`；同一张场景图被多行引用时只建一条 `scene_image`，由多个产品共享。
>
> 品牌 / 供应商 / 分类必须填系统里**已存在**的名称，导入不会替用户新建（三者在库里都是 NOT NULL 外键），三列有一列对不上这行就失败。
>
> 每行一个 SAVEPOINT：一行撞约束只回滚那一行，其余行照常入库。
>
> 默认上限：单文件 512MB、单次 5000 行、单张图片 20MB、每行 10 张产品图 / 30 张场景图（`PRODUCT_IMPORT_*` 配置项）。zip 成员按需解压，图片不会整包读进内存；文件上限与 nginx 的 `client_max_body_size` 必须一起改，否则用户只会看到网关那张 413 页面。

**Query:**

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `skipIfExists` | bool | `false` | 编号已存在时的失败原因写「编号已存在，已跳过」；`false` 时写「产品编号已存在」。两种情况都只进失败明细，不会覆盖已有产品 |

**Response:**

```json
{
  "code": 200,
  "data": {
    "total": 100,
    "success_count": 95,
    "fail_count": 5,
    "failures": [
      { "row": 12, "product_no": "P-X1-001", "reason": "产品编号已存在" }
    ],
    "notes": ["第 8 行：面价为空，已按待核价（99999）导入并标记为待补充"],
    "image_count": 143,
    "scene_image_count": 20,
    "uploaded_count": 96,
    "image_sources": ["dispimg", "zip"],
    "image_warnings": ["第 30 行主图列有多张图，第一张作封面，其余按产品图导入"],
    "header_row": 1,
    "unknown_headers": ["内部备注"],
    "blank_rows": 2
  }
}
```

| 字段 | 说明 |
| --- | --- |
| `total` | 表里的数据行数（不含表头和空行） |
| `success_count` / `fail_count` | 入库成功 / 失败的行数 |
| `failures[]` | `row` 是 Excel 里的真实行号，`product_no` 可能为空（编号本身没填时），`reason` 多条原因用 `；` 连接 |
| `notes` | 数据层面的提示（占位面价、字段截断、标签不存在等），不影响入库 |
| `image_count` / `scene_image_count` | 实际绑定的产品图（含封面）/ 场景图条数，按行累计 |
| `uploaded_count` | 真正写进对象存储的文件数；去重后通常小于 `image_count + scene_image_count` |
| `image_sources` | 这批图是怎么取到的：`anchor`（浮动图片）、`dispimg`（WPS 嵌入单元格）、`richvalue`（Excel 置于单元格内）、`zip`（压缩包内文件名）、`convention`（压缩包内按编号前缀匹配）、`url`（外链抓取） |
| `image_warnings` | 图片层面的提示（超限、格式不支持、直链未开启、单张传失败等），不影响该行入库 |
| `header_row` | 识别到的表头所在行（表头不必是第一行，向下扫 16 行） |
| `unknown_headers` | 没认出来、已忽略的列名 |
| `blank_rows` | 跳过的空行数 |

> 失败原因是给业务人员看的中文，例如「品牌「索菲亚」系统里没有，请先建好再导入」「表里有重复的产品编号，只导入第一次出现的那行」「面价无法识别：'面议价'」。

### 8.9 下载导入模板

```
GET /api/v1/products/import-template
```

> 返回 xlsx 文件流（`Content-Disposition: attachment; filename="products_import_template.xlsx"`），需 `product:import` 权限。两张工作表：`产品`（列名即导入识别的表头，必填列带 `*`）与 `填写说明`（三种给图方式、主数据必须先建、面价占位值等规则）。列名与 8.10 导出产品保持一致，因此「导出 → 改 → 导回」这条路可用。

### 8.10 导出产品

```
GET /api/v1/products/export
```

> 按当前筛选条件导出 Excel，返回文件流（`Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`）。需 `product:export` 权限。

---

## 九、分类管理

### 9.1 分类树

```
GET /api/v1/categories
```

> 返回三级树形结构，无需分页。

**Response:**

```json
{
  "code": 200,
  "data": [
    {
      "category_id": "0192...",
      "category_name": "音视频设备",
      "level": 1,
      "children": [
        {
          "category_id": "0192...",
          "category_name": "会议终端",
          "level": 2,
          "children": []
        }
      ]
    }
  ]
}
```

### 9.2 创建分类

```
POST /api/v1/categories
```

**Request Body:**

```json
{
  "parent_id": "0192_cat_root...",
  "category_name": "会议终端",
  "sort": 1
}
```

> level 由后端根据 parent_id 自动计算。

### 9.3 更新分类

```
PUT /api/v1/categories/{id}
```

### 9.4 删除分类

```
DELETE /api/v1/categories/{id}
```

> 若分类下存在产品，返回 42201 错误，禁止删除。

---

## 十、品牌 / 供应商 / 标签管理

三者均为标准 CRUD，结构一致，合并说明。

### 10.1 品牌管理 `/api/v1/brands`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/brands` | 品牌列表（支持 keyword） |
| POST | `/api/v1/brands` | 创建品牌：`{ brand_name, logo_url, description }` |
| PUT | `/api/v1/brands/{id}` | 更新品牌 |
| DELETE | `/api/v1/brands/{id}` | 删除品牌（有产品引用时返回 42201） |

### 10.2 供应商管理 `/api/v1/suppliers`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/suppliers` | 供应商列表（支持 keyword、cooperation_status） |
| POST | `/api/v1/suppliers` | 创建：`{ supplier_name, contact, phone, cooperation_status }` |
| PUT | `/api/v1/suppliers/{id}` | 更新 |
| DELETE | `/api/v1/suppliers/{id}` | 删除（有产品引用时返回 42201） |

### 10.3 标签管理 `/api/v1/tags`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/tags` | 标签列表（支持 tag_type 筛选） |
| POST | `/api/v1/tags` | 创建：`{ tag_name, tag_type }` |
| PUT | `/api/v1/tags/{id}` | 更新 |
| DELETE | `/api/v1/tags/{id}` | 删除（自动清理 product_tag 关联） |

---

## 十一、方案管理

### 11.1 方案列表

```
GET /api/v1/proposals
```

| Query 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| status | string | 否 | draft / confirmed / archived |
| creator_id | UUID | 否 | 按创建人筛选 |
| customer_name | string | 否 | 客户名称模糊匹配 |
| page / size | int | 否 | 分页 |

### 11.2 方案详情

```
GET /api/v1/proposals/{id}
```

**Response:** 包含方案基础信息 + 明细列表（含产品快照信息）。

```json
{
  "code": 200,
  "data": {
    "proposal_id": "0192_prop_88123",
    "proposal_no": "PR-2026-0001",
    "proposal_name": "XX公司会议室设备方案",
    "customer_name": "XX科技有限公司",
    "status": "draft",
    "ai_polished": false,
    "creator_name": "sales01",
    "create_time": "2026-07-12T10:00:00+08:00",
    "items": [
      {
        "item_id": "0192_pitem_1",
        "product_id": "0192_p99823",
        "product_name": "智能全自动会议终端 X1",
        "product_no": "P-X1-001",
        "face_price": 8800.00,
        "quantity": 2,
        "sort": 1,
        "remark": "主会议室用"
      }
    ]
  }
}
```

### 11.3 创建方案

```
POST /api/v1/proposals
```

**Request Body:**

```json
{
  "proposal_name": "XX公司会议室设备方案",
  "customer_name": "XX科技有限公司",
  "items": [
    { "product_id": "0192_p99823", "quantity": 2, "remark": "主会议室" },
    { "product_id": "0192_p99824", "quantity": 1 }
  ],
  "ai_polish": false
}
```

> `proposal_no` 由后端按 `PR-yyyy-序号` 自动生成。

### 11.4 更新方案

```
PUT /api/v1/proposals/{id}
```

> 支持修改方案名、客户名、明细（增删改 items）。status 为 confirmed 后禁止修改，返回 42201。

### 11.5 AI 方案润色

```
POST /api/v1/proposals/{id}/ai-polish
```

> 调用 AI 能力中心，对方案明细进行亮点提炼与话术修饰，生成推荐理由。返回润色后的内容，并标记 `ai_polished = true`。

**Response:**

```json
{
  "code": 200,
  "data": {
    "polished_summary": "本方案精选 3 款设备，主打现代简约风格...",
    "items": [
      {
        "item_id": "0192_pitem_1",
        "recommend_reason": "X1 终端支持 4K 显示与智能追踪，适合 30 人中型会议室..."
      }
    ]
  }
}
```

### 11.6 删除方案（软删除）

```
DELETE /api/v1/proposals/{id}
```

> 级联软删除方案明细。若已生成报价单或分享，返回 42201 禁止删除。

---

## 十二、报价管理

### 12.1 报价单列表

```
GET /api/v1/quotations
```

| Query 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| proposal_id | UUID | 否 | 按方案筛选 |
| status | string | 否 | draft / confirmed / expired |
| page / size | int | 否 | 分页 |

### 12.2 报价单详情

```
GET /api/v1/quotations/{id}
```

**Response:** 包含报价单信息 + 明细（含单价快照、税率、小计）。

### 12.3 创建报价单

```
POST /api/v1/quotations
```

**Request Body:**

```json
{
  "proposal_id": "0192_prop_88123",
  "tax_rate": 0.13,
  "discount": 0.95,
  "items": [
    {
      "product_id": "0192_p99823",
      "quantity": 2,
      "unit_price": 8800.00,
      "tax_rate": 0.13
    }
  ]
}
```

> `total_amount` 与各 `subtotal` 由后端计算。`unit_price` 为快照值，锁定下单时价格。`quotation_no` 按 `QT-yyyy-序号` 自动生成。

### 12.4 更新报价单

```
PUT /api/v1/quotations/{id}
```

> status 为 confirmed 后禁止修改，返回 42201。

### 12.5 导出报价单 PDF

```
GET /api/v1/quotations/{id}/pdf
```

> 通过 Gotenberg 将 HTML 模板渲染为 PDF，返回文件流（`Content-Type: application/pdf`）。响应头含 `Content-Disposition: attachment; filename="QT-2026-0001.pdf"`。

---

## 十三、分享管理

### 13.1 创建分享链接

```
POST /api/v1/shares
```

**Request Body:**

```json
{
  "share_type": "proposal",
  "target_id": "0192_prop_88123",
  "password": "1234",
  "expire_hours": 72,
  "max_access_count": 10
}
```

**Response:**

```json
{
  "code": 200,
  "data": {
    "share_id": "0192_share_1...",
    "share_url": "https://pim.example.com/share/tk_a8f3b2e1",
    "qr_code_url": "https://pim.example.com/qr/tk_a8f3b2e1.png",
    "token": "tk_a8f3b2e1",
    "expire_time": "2026-07-15T10:00:00+08:00",
    "max_access_count": 10
  }
}
```

### 13.2 我的分享列表

```
GET /api/v1/shares
```

| Query 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| share_type | string | 否 | proposal / quotation |
| status | string | 否 | active / disabled |
| page / size | int | 否 | 分页 |

**Response:** 每条含分享信息 + 当前访问次数 + 最近访问时间。

### 13.3 分享页访问（无需 JWT）

```
GET /api/v1/share/{token}
```

| Query 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| password | string | 否 | 若设置了密码则必填 |

> 前端通过请求头 `X-Device-Fingerprint` 传递设备指纹；若已接入微信登录，通过 `X-Openid` 传递 openid，用于访客身份识别。

**校验逻辑：** token 存在 → 状态有效 → 未过期 → 未超次 → 密码正确 → 识别/创建访客(visitor) → 计数+1 → 写入 share_log（含 visitor_id/IP/指纹/openid）→ 返回内容。

**Response:**（返回方案或报价单的只读视图，过滤敏感字段如成本价）

```json
{
  "code": 200,
  "data": {
    "share_type": "proposal",
    "proposal_name": "XX公司会议室设备方案",
    "customer_name": "XX科技有限公司",
    "items": [ ... ],
    "creator_name": "销售部"
  }
}
```

### 13.4 撤销分享

```
DELETE /api/v1/shares/{id}
```

> 将 share.status 置为 disabled，所有关联 token 立即失效。软删除，不物理删除。

---

## 十四、文件管理

### 14.1 文件上传

```
POST /api/v1/files/upload
```

> `multipart/form-data`，字段 `file`。上传至 MinIO，返回 attachment 记录。

| 限制 | 规范 |
| --- | --- |
| 允许类型 | image/jpeg, image/png, image/webp, video/mp4, application/pdf, application/msword, application/vnd.openxmlformats-officedocument.wordprocessingml.document |
| 最大大小 | 图片 10MB，视频 100MB，文档 50MB |

**Response:**

```json
{
  "code": 200,
  "data": {
    "attachment_id": "0192_att_1...",
    "file_name": "产品图_X1.jpg",
    "file_url": "https://pim.example.com/files/0192_att_1...",
    "file_type": "image",
    "file_size": 245678
  }
}
```

### 14.2 删除文件

```
DELETE /api/v1/files/{attachment_id}
```

> 软删除 attachment 记录。若被产品图片/说明书引用，需先解除关联。

### 14.3 文件下载

```
GET /api/v1/files/{attachment_id}/download
```

> 鉴权：需登录。返回文件流，Content-Type 为文件实际 MIME 类型。通过 MinIO 预签名 URL 下载。

**Response:** 文件流（`Content-Disposition: attachment; filename="原始文件名"`）

### 14.4 文件预览

```
GET /api/v1/files/{attachment_id}/preview
```

> 鉴权：需登录。返回预签名 URL，前端可直接用于 img/video 标签或 PDF 预览。有效期 15 分钟。

**Response:**

```json
{
  "code": 200,
  "data": {
    "preview_url": "https://minio.example.com/bucket/xxx?X-Amz-Signature=...",
    "expire_in": 900
  }
}
```

### 14.5 媒体库文件列表

```
GET /api/v1/files
```

> 鉴权：`media:view`。媒体库页面（后台 `/media`）的数据源，分页返回未删除的 attachment。

| Query 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| keyword | string | 否 | 文件名模糊匹配 |
| file_type | string | 否 | image / video / pdf / doc / other，其余值返回 422（42201） |
| referenced | bool | 否 | true 只看被产品图/场景图/说明书引用的，false 只看未引用的 |
| sort | string | 否 | newest（默认，按上传时间倒序）/ nameAsc / nameDesc / size（按大小倒序），其余值返回 422（42206） |
| page | int | 否 | 页码，默认 1 |
| size | int | 否 | 每页条数，默认 20，最大 100 |

> **排序必须是全序**：`sort` 的每种取值在服务端都会追加 `id` 作为末位比较键。
> 带图导入会把成千个附件写成同一个 `create_time`，只按 `create_time` 排序时
> `OFFSET/LIMIT` 的行序不确定，翻页会重复吐同一个文件、同时让另一些文件一页都进不去
> （线上实测 3104 个文件里有 476 个翻不到）。新增排序字段时同样要带上 `id`。

**Response:**

```json
{
  "code": 200,
  "data": {
    "list": [
      {
        "id": "0192_att_1...",
        "file_name": "产品图_X1.jpg",
        "file_url": "https://pim.example.com/files/0192_att_1...",
        "preview_url": "/api/v1/files/0192_att_1.../content?token=...",
        "file_type": "image",
        "file_size": 245678,
        "storage_type": "minio",
        "oss_key": "media/2026/08/xxx.jpg",
        "create_time": "2026-08-01T10:00:00+00:00",
        "update_time": "2026-08-01T10:00:00+00:00",
        "ref_count": 2
      }
    ],
    "total": 3104,
    "page": 1,
    "size": 20
  }
}
```

---

## 十五、AI 对话模块

### 15.1 AI 智能对话（非流式）

```
POST /api/v1/ai/chat
```

**Request Body:**

```json
{
  "conversation_id": "conv_7721",
  "question": "帮我挑几款适合30人中型会议室、现代简约风格的投影设备，预算控制在3万以内",
  "stream": false
}
```

**Response（含 Tool Calls）:**

```json
{
  "code": 200,
  "data": {
    "answer": "已为您筛选出符合现代简约风格、适合中型会议室且总预算在3万以内的3款设备...",
    "sources": ["产品说明书_X1.pdf", "会议室设备选型指南.docx"],
    "tool_calls": {
      "target_api": "/api/v1/products",
      "parsed_arguments": {
        "style": "modern",
        "scene": "meeting_room",
        "max_price": 30000
      }
    }
  }
}
```

### 15.2 AI 智能对话（流式）

```
POST /api/v1/ai/chat
Content-Type: application/json
Accept: text/event-stream
```

**Request Body:**

```json
{
  "conversation_id": "conv_7721",
  "question": "推荐适合会议室的投影设备",
  "stream": true
}
```

> 流式规范见第十七章 SSE。

### 15.3 对话历史

```
GET /api/v1/ai/conversations/{conversation_id}/history
```

**Response:**

```json
{
  "code": 200,
  "data": {
    "conversation_id": "conv_7721",
    "messages": [
      { "role": "user", "content": "推荐会议室投影", "create_time": "..." },
      { "role": "assistant", "content": "已为您筛选...", "create_time": "..." }
    ]
  }
}
```

### 15.4 会话管理

```
POST   /api/v1/ai/conversations          # 创建新会话，返回 conversation_id
GET    /api/v1/ai/conversations           # 当前用户会话列表
DELETE /api/v1/ai/conversations/{id}      # 删除会话及其历史
```

---

## 十六、数据统计

### 16.1 分享访问统计

```
GET /api/v1/stats/shares
```

| Query 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| start_date | date | 否 | 起始日期 |
| end_date | date | 否 | 结束日期 |

**Response:**

```json
{
  "code": 200,
  "data": {
    "total_shares": 56,
    "total_access": 312,
    "active_shares": 18,
    "top_accessed": [
      { "share_id": "0192...", "proposal_name": "XX方案", "access_count": 48 }
    ]
  }
}
```

### 16.2 产品热度统计

```
GET /api/v1/stats/products/hot
```

> 统计被方案引用次数最多的产品 Top N。

| Query 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| limit | int | 10 | Top N |

---

## 十七、流式交互规范（SSE）

AI 对话接口支持流式输出，采用 Server-Sent Events（SSE）协议。

### 17.1 请求

```
POST /api/v1/ai/chat
Content-Type: application/json
Accept: text/event-stream
```

### 17.2 响应（SSE 数据帧）

```
data: {"type": "token", "content": "已为您"}

data: {"type": "token", "content": "筛选出"}

data: {"type": "tool_call", "target_api": "/api/v1/products", "parsed_arguments": {"scene": "meeting_room"}}

data: {"type": "sources", "sources": ["产品说明书_X1.pdf"]}

data: {"type": "done", "answer": "已为您筛选出..."}
```

### 17.3 数据帧类型

| type | 说明 |
| --- | --- |
| `token` | 流式文本片段 |
| `tool_call` | AI 发起的工具调用（标准化参数） |
| `sources` | 引用来源 |
| `done` | 流结束，包含完整 answer |
| `error` | 流式错误，含 code 与 message |

```
data: {"type": "error", "code": 50201, "message": "AI 引擎暂时不可用，请稍后重试"}
```

### 17.4 Nginx 流式配置

```nginx
location /api/v1/ai/chat {
    proxy_pass http://backend:8000;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_buffering off;          # 关键：关闭缓冲支持流式
    proxy_read_timeout 300s;
}
```

---

## 十八、AI Service Adapter 接口契约

业务层通过 `AIServiceAdapter` 抽象基类调用 AI 能力，统一抹平 FastGPT/Dify/RagFlow 的 API 差异。

> 详细接口定义与实现规范见 [02-系统架构与设计(HLD)](./02-系统架构与设计(HLD).md) 第三章。核心方法签名：

| 方法 | 说明 |
| --- | --- |
| `chat(session_id, message, history, stream)` | 统一对话接口（非流式） |
| `chat_stream(session_id, message, history)` | 统一流式对话接口，返回 AsyncGenerator |
| `parse_tool_calls(raw_response)` | 统一解析 Tool Call 格式 |
| `manage_session(action, session_id)` | 会话生命周期管理（创建/拉取/删除） |

新增 AI 引擎适配器步骤见 [07-开发规范](./07-开发规范.md) 第五章。

---

## 十九、OpenAPI YAML 生成说明

FastAPI 应用启动后自动在以下路径提供机器可读的 OpenAPI 3.0 规范：

| 路径 | 说明 |
| --- | --- |
| `/openapi.json` | OpenAPI 3.0 JSON 规范 |
| `/docs` | Swagger UI 交互文档 |
| `/redoc` | ReDoc 文档 |

### 19.1 前后端联调流程

1. 后端按本文档契约实现接口，FastAPI 自动生成 `/openapi.json`
2. 前端通过 `openapi-typescript-codegen` 或 `openapi-generator` 生成 TS 类型和请求客户端
3. 前后端以 `/openapi.json` 为唯一契约源，避免手动维护

### 19.2 核心 Model 定义示例

```python
# backend/app/schemas/product.py
from pydantic import BaseModel
from typing import Optional
from uuid import UUID

class ProductCreate(BaseModel):
    product_no: str
    product_name: str
    brand_id: UUID
    supplier_id: UUID
    category_id: UUID
    face_price: float
    cost_price: Optional[float] = None     # 字段级权限：sales 角色响应时过滤
    material: Optional[str] = None
    stock_status: str = "in_stock"
    status: str = "draft"
    tag_ids: list[UUID] = []
```

---

## 二十、安全规范

| 维度 | 规范 |
| --- | --- |
| 传输 | 全站 HTTPS |
| 鉴权 | JWT Bearer Token，过期时间 2h，refresh_token 刷新 |
| 限流 | 关键接口 Redis 令牌桶限流（AI 对话 10 次/分钟/用户，登录 5 次/分钟/IP） |
| 防注入 | ORM 严格参数化查询，杜绝 SQL 注入与 XSS |
| 文件上传 | 扩展名强白名单 + 文件大小限制 + 流式病毒检测（预留） |
| 字段权限 | 响应序列化层统一过滤敏感字段（cost_price / supplier_id 等） |
| 分享访问 | ShareToken 校验 + 密码 + 过期 + 次数限制 + 审计日志 |
| 越权检查 | 每个接口校验"当前用户是否有权操作该资源" |

---

*本文档随接口迭代持续更新。当前阶段：完整契约（已覆盖 15 模块 65 接口）。*

---

## 修订记录

| 日期 | 修订内容 | 修订人 |
| --- | --- | --- |
| 2026-07-12 | 按总经理审查报告 P0/P1/P2 项修订 | Agent-B |
