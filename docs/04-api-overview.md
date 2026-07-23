# docs/04 — 接口总览（MVP 阶段①~③已实现）

> 本文档依据 `app/api/v1/*` 实际路由与 `app/main.py` 注册生成，并以
> `tests/test_contract.py::EXPECTED_NEW_ROUTES` + `app.main` 的 OpenAPI 路由表作为
> **机器可验证依据**（已运行 `pytest tests/test_contract.py -k "route"` 通过：14/14 命中）。
>
> 仅记录**已实现**接口。凡 method+path 未注册者一律不写为已实现；
> 特别地，**不存在 `DELETE /api/v1/quotations/{id}`（quotation:delete）**，请勿误记为已实现。
>
> 通用约定：
> - 统一响应包：`{"code": int, "data": ..., "msg": ...}`（`code=200` 成功）。
> - 鉴权：除 `GET /api/v1/share/{token}` 为公开接口外，其余均经 `PermissionChecker`
>   校验 JWT + `required_permission`；缺失 Token → 40101，过期 → 40102，无权限 → 40301。
> - 审计：被 `@audit_action` 装饰的接口在 `operation_log` 落库（动作见各接口「审计动作」）。
> - 软删除：列表/详情类查询均过滤 `is_deleted=false`。

---

## 一、路由集合（本文档覆盖）

| # | method | path | 公开 | required permission | 审计动作 | 章节 |
|---|---|---|---|---|---|---|
| 1 | POST | /api/v1/quotations | N | quotation:create | quotation_create | §2.1 |
| 2 | GET | /api/v1/quotations | N | quotation:view | quotation_list | §2.1 |
| 3 | GET | /api/v1/quotations/{quotation_id} | N | quotation:view | quotation_detail | §2.1 |
| 4 | PUT | /api/v1/quotations/{quotation_id} | N | quotation:edit | quotation_update | §2.1 |
| 5 | GET | /api/v1/quotations/{quotation_id}/pdf | N | quotation:view | quotation_pdf_export | §2.1 |
| 6 | POST | /api/v1/quotations/{quotation_id}/confirm | N | quotation:confirm | quotation_confirm | §2.1 |
| 7 | POST | /api/v1/files/upload | N | file:upload | file_upload | §3.1 |
| 7 | DELETE | /api/v1/files/{attachment_id} | N | file:delete | file_delete | §3.1 |
| 8 | GET | /api/v1/files/{attachment_id}/download | N | file:view | file_download | §3.1 |
| 9 | GET | /api/v1/files/{attachment_id}/preview | N | file:view | file_preview | §3.1 |
| 10 | GET | /api/v1/stats/shares | N | stats:view | stats_shares | §4.1 |
| 11 | GET | /api/v1/stats/products/hot | N | stats:view | stats_products_hot | §4.2 |
| 12 | POST | /api/v1/products/{product_id}/clone | N | product:clone | product_clone | §5.1 |
| 13 | POST | /api/v1/products/import | N | product:import | product_import | §5.2 |
| 14 | GET | /api/v1/products/export | N | product:export | （通用请求日志，无 §7.3 专属动作） | §5.3 |
| 15 | GET | /api/v1/share/{token} | **Y** | —（令牌鉴权） | share_access（失败 share_access_denied） | §6.1 |
| 16 | POST | /api/v1/users/{user_id}/disable | N | user:disable | user_disable | §7.1 |
| 17 | POST | /api/v1/proposals/{proposal_id}/confirm | N | proposal:confirm | proposal_confirm | §7.2 |
| 18 | GET | /api/v1/audit/operation-logs | N | audit:view | — | §7.3 |
| 19 | GET | /api/v1/version | N | stats:view | — | §8.1 |

---

## 二、Quotations（5 个接口）

### §2.1.1 POST /api/v1/quotations
- 公开：否 ｜ 权限：`quotation:create` ｜ 审计：`quotation_create`
- 请求体（JSON）：
  - `proposal_id` UUID（必填，关联方案须存在）
  - `tax_rate` float=0.13，`discount` float=1.0，`valid_until` datetime|null
  - `items` list[ `{product_id:UUID, quantity:int=1, unit_price:float, tax_rate:float=0.13}` ]（可空）
- 成功响应：201，返回 `QuotationResponse`（含 `subtotal`、`total_amount`、嵌套 `items`），
  其中 `subtotal`/`total_amount` 由后端 `_compute_totals` 计算。
- 主要错误码：40401（关联方案不存在）、40101/40102/40301。

### §2.1.2 GET /api/v1/quotations
- 公开：否 ｜ 权限：`quotation:view` ｜ 审计：`quotation_list`
- 请求参数（query）：`proposal_id`(UUID)、`status`(alias=`status`)、`page`(≥1,=1)、
  `size`(1~100,=20)。
- 成功响应：200，`{list, total, page, size}`。
- 主要错误码：40101/40102/40301。

### §2.1.3 GET /api/v1/quotations/{quotation_id}
- 公开：否 ｜ 权限：`quotation:view` ｜ 审计：`quotation_detail`
- 路径参数：`quotation_id` UUID。
- 成功响应：200，`QuotationResponse`。
- 主要错误码：40401（报价单不存在）、40101/40102/40301。

### §2.1.4 PUT /api/v1/quotations/{quotation_id}
- 公开：否 ｜ 权限：`quotation:edit` ｜ 审计：`quotation_update`
- 路径参数：`quotation_id` UUID。
- 请求体（JSON，全可选）：`tax_rate`、`discount`、`valid_until`、`status`、`items`。
- 成功响应：200，`QuotationResponse`（重算 subtotal/total_amount）。
- 主要错误码：40401、`42201`（状态为 confirmed 不可修改）、40101/40102/40301。

### §2.1.5 GET /api/v1/quotations/{quotation_id}/pdf
- 公开：否 ｜ 权限：`quotation:view` ｜ 审计：`quotation_pdf_export`
- 路径参数：`quotation_id` UUID。
- 成功响应：200，`application/pdf`。
- 说明：当前实现调用 Gotenberg `/forms/chromium/convert/html` 将后端 HTML 模板渲染为 PDF；Gotenberg 未配置返回 503，生成失败返回 502。
- 主要错误码：40401、40101/40102/40301。

### §2.1.6 POST /api/v1/quotations/{quotation_id}/confirm
- 公开：否 ｜ 权限：`quotation:confirm` ｜ 审计：`quotation_confirm`
- 语义：将报价单状态置为 `confirmed`；重复确认幂等；确认后 `PUT /quotations/{id}` 返回 42201。
- 成功响应：200，`QuotationResponse`。

---

## 七、V1.1 工作流与审计补充

### §7.1 POST /api/v1/users/{user_id}/disable
- 公开：否 ｜ 权限：`user:disable` ｜ 审计：`user_disable`
- 语义：将用户状态置为 `disabled`；重复停用幂等。
- 成功响应：200，`UserResponse`。

### §7.2 POST /api/v1/proposals/{proposal_id}/confirm
- 公开：否 ｜ 权限：`proposal:confirm` ｜ 审计：`proposal_confirm`
- 语义：将方案状态置为 `confirmed`；重复确认幂等；确认后 `PUT /proposals/{id}` 返回 42201。
- 成功响应：200，`ProposalResponse`。

### §7.3 GET /api/v1/audit/operation-logs
- 公开：否 ｜ 权限：`audit:view`。
- 查询参数：`action`、`module`、`user_id`、`response_code`、`start_time`、`end_time`、`page`、`size`。
- 成功响应：200，`{list,total,page,size}`。
- 安全约束：响应不返回 `request_body`，避免密码、JWT、AI prompt 或敏感请求体在审计页面展示。

---

## 三、Files（4 个接口）

> `file_type` canonical = `image`/`video`/`pdf`/`doc`/`other`（见 docs/03 §2.2.1）。
> MIME 白名单与大小上限：
> image/jpeg|png|webp(≤10MB)→image；video/mp4(≤100MB)→video；
> application/pdf(≤50MB)→pdf；msword / openxml word(≤50MB)→doc。

### §3.1.1 POST /api/v1/files/upload
- 公开：否 ｜ 权限：`file:upload` ｜ 审计：`file_upload`
- 请求：multipart `file`（UploadFile）。
- 成功响应：201，`{attachment_id, file_name, file_url, file_type, file_size}`。
- 主要错误码：42202（MIME 不在白名单）、42203（超大小上限）、40101/40102/40301。

### §3.1.2 DELETE /api/v1/files/{attachment_id}
- 公开：否 ｜ 权限：`file:delete` ｜ 审计：`file_delete`
- 路径参数：`attachment_id` UUID。
- 成功响应：200，`{code:200, msg:"success"}`（软删除）。
- 主要错误码：40401（附件不存在）、`42201`（被 product_image/product_manual 引用，
  需先解绑）、40101/40102/40301。

### §3.1.3 GET /api/v1/files/{attachment_id}/download
- 公开：否 ｜ 权限：`file:view` ｜ 审计：`file_download`
- 路径参数：`attachment_id` UUID。
- 成功响应：307 Redirect 到 MinIO 预签名 URL（有效期 5 分钟）。
- 主要错误码：40401、40101/40102/40301。

### §3.1.4 GET /api/v1/files/{attachment_id}/preview
- 公开：否 ｜ 权限：`file:view` ｜ 审计：`file_preview`
- 路径参数：`attachment_id` UUID。
- 成功响应：200，`{preview_url, expire_in:900}`（预签名 URL，有效期 900s）。
- 主要错误码：40401、40101/40102/40301。

---

## 四、Stats（2 个接口）

### §4.1 GET /api/v1/stats/shares
- 公开：否 ｜ 权限：`stats:view` ｜ 审计：`stats_shares`
- 请求参数（query）：`start_date`、`end_date`（date，可选，按 `Share.create_time` /
  `ShareLog.access_time` 过滤）。
- 成功响应：200，`{total_shares, total_access, active_shares, top_accessed:[{share_id,
  proposal_name, access_count}]}`（top_accessed 取访问次数 Top10）。
- 主要错误码：40101/40102/40301。

### §4.2 GET /api/v1/stats/products/hot
- 公开：否 ｜ 权限：`stats:view` ｜ 审计：`stats_products_hot`
- 请求参数（query）：`limit`(1~100,=10)。
- 成功响应：200，`{items:[{product_id, product_name, ref_count}]}`
  （按 `proposal_item` 引用次数降序）。
- 主要错误码：40101/40102/40301。

---

## 五、Products 扩展（克隆 / 导入 / 导出）

### §5.1 POST /api/v1/products/{product_id}/clone
- 公开：否 ｜ 权限：`product:clone` ｜ 审计：`product_clone`
- 路径参数：`product_id` UUID。
- 成功响应：200，`ProductCloneResponse`（= ProductResponse）：
  `product_no="{原号}-COPY"`、`product_name="{原名} (副本)"`、复制 brand/supplier/
  category/material/价格/标签，`status="draft"`。
- 说明：不复制附件与向量；不触发 Embedding。
- 主要错误码：40401（产品不存在）、40101/40102/40301。

### §5.2 POST /api/v1/products/import
- 公开：否 ｜ 权限：`product:import` ｜ 审计：`product_import`
- 请求：multipart `file`（Excel，`engine=openpyxl`）；query `skipIfExists`(bool,=false)。
- 必填列：`product_no`、`product_name`、`face_price`；可选列：`brand_name`、
  `supplier_name`、`category_name`、`cost_price`、`material`、`stock_status`、`status`、
  `tag_names`(逗号分隔)。品牌/供应商/分类须已存在，否则该行失败。
- 成功响应：200，`{total, success_count, fail_count, failures:[{row, product_no, reason}]}`。
- 主要错误码：40001（文件解析失败）、40002（缺必填列）、40101/40102/40301。

### §5.3 GET /api/v1/products/export
- 公开：否 ｜ 权限：`product:export` ｜ 审计：通用请求日志（无 §7.3 专属动作名）
- 请求参数（query）：与 `GET /products` 同（category_id/tag_ids/keyword/brand_id/
  supplier_id/status/stock_status/min_price/max_price）。
- 成功响应：`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
  流（`products_export.xlsx`），响应头 `X-Total-Count`。字段含 product_id/product_no/
  product_name/brand_name/supplier_name/category_name/face_price/cost_price/material/
  specification/colors/data_source/completeness_status/stock_status/status/description/
  create_time/update_time/tags。待核价占位值导出为“待核价”；sales/viewer 导出不包含
  `cost_price` 和 `supplier_name` 列。
- 主要错误码：40101/40102/40301。

---

## 六、Share（公开接口）

### §6.1 GET /api/v1/share/{token}
- 公开：**是**（C 端访客无后台账号，豁免 JWT/RBAC；鉴权由分享令牌承担）
- required permission：— ｜ 审计：`share_access`（失败 `share_access_denied`）
- 路径参数：`token` str；query：`password`(可选)。
- 鉴权/校验顺序（每次访问无论成败均写 `share_log`）：
  1. token 不存在 → 40401；
  2. `status='disabled'` → 40301；`status='expired'` 或 `expire_time` 过期 → 40302（过期会原子置 expired）；
  3. `max_access_count` 达上限（原子自增失败）→ 40303；
  4. 设了 `password` 且不符 → 40304（并回退计数）；
  5. 关联 `share` 不存在 → 40401；
  6. 成功 → 解析 visitor（openid 优先，指纹次之），组装 `content`（proposal/quotation 明细），
     经 `filter_sensitive_fields(role_code="sales")` 脱敏后返回。
- 成功响应：200，`{share_type, target_id, access_count, content}`。
- 主要错误码：40401、40301、40302、40303、40304。

---

## 八、版本信息

### §8.1 GET /api/v1/version

- 公开：否 ｜ 权限：`stats:view` ｜ 审计：通用请求日志。
- 语义：返回当前后端运行实例的版本与构建元数据，不查询产品、媒体或其他业务表。
- 成功响应：

```json
{
  "code": 200,
  "data": {
    "app_name": "AI-PIM",
    "backend_version": "1.2.0",
    "frontend_version": "1.2.0",
    "build_id": "1.2.0-abc1234",
    "git_commit": "abc1234",
    "build_time": "2026-07-22T12:00:00Z",
    "environment": "production",
    "api_version": "v1"
  }
}
```

- 缺省语义：未注入构建信息时 `build_id=dev-local`，`git_commit/build_time=unknown`，
  接口仍返回 200。
- 安全约束：不返回数据库连接、JWT secret、MinIO 凭据、AI Key 或内部服务地址。
- 主要错误码：40101/40102/40301。

---

## 九、docs/04 路由集合 vs EXPECTED_NEW_ROUTES（机器验证）

`tests/test_contract.py::EXPECTED_NEW_ROUTES`（14 条）：
```
post /api/v1/quotations
get  /api/v1/quotations
get  /api/v1/quotations/{quotation_id}
put  /api/v1/quotations/{quotation_id}
get  /api/v1/quotations/{quotation_id}/pdf
post /api/v1/files/upload
delete /api/v1/files/{attachment_id}
get  /api/v1/files/{attachment_id}/download
get  /api/v1/files/{attachment_id}/preview
get  /api/v1/stats/shares
get  /api/v1/stats/products/hot
post /api/v1/products/{product_id}/clone
post /api/v1/products/import
get  /api/v1/products/export
```
- 上述 14 条 **全部** 在 `app.main` 的 OpenAPI 路由表中命中（`pytest ... -k route` 通过）。
- docs/04 另覆盖 `GET /api/v1/share/{token}`（公开，不在 EXPECTED_NEW_ROUTES 内，但任务要求标记已实现）。
- **无重复 method+path**；**未将 `quotation:delete` 写为已实现接口**（不存在 `DELETE /api/v1/quotations/{id}`）。

---

## 十、无法确认 / 需交付确认项
1. `GET /products/export` 在 `app/core/permission.PermissionChecker` 未声明 §7.3 专属
   审计动作名（仅通用 `AuditMiddleware` 请求日志），如需专属 `audit_action` 需补。
2. 报价 PDF 已接入 Gotenberg；仍需生产环境真实 PDF 端到端回归。
3. 产品导入 Excel 模板的「列名中英文 / 缺列容错」以代码 `required_cols` 与字段映射为准，
   未单独成文规范。
