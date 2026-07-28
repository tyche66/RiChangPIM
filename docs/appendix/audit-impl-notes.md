# 审计实现偏差说明（对照 §7.3 / §7.2）

> 本文件记录 `docs/07-开发规范.md` §7.3「审计动作清单」与当前实现之间的偏差原因。
> 凡无对应实现接口的清单项均在此处留 TODO，不伪造接口。

修订时间：2026-07-15。实现提交：审计中间件 + 装饰器设施补齐。

---

## 一、实现机制

依据 §7.3「审计日志记录通过 FastAPI 中间件 + 装饰器实现，业务层无需手动调用」与
§7.2「请求日志: method/path/user_id/ip/耗时/status_code」，采用 **中间件 + 装饰器**
职责分离设计：

| 设施 | 文件 | 职责 |
| --- | --- | --- |
| `AuditMiddleware` | `backend/app/middleware/audit.py` | 通用请求日志（§7.2 字段全部输出到 `app.audit` logger），**不写** `operation_log` 表，避免重复落库 |
| `audit_action(action, module, ...)` | 同上 | 按 §7.3 清单命中具体动作，自动写 `operation_log` 表；失败降级 ERROR，不阻塞业务 |

注册：`backend/app/main.py` 中 `app.add_middleware(AuditMiddleware)`。

自动捕获字段（§7.2）：

- `user_id`：优先 `request.state.user_id`（`PermissionChecker` 写入），回退解码
  `Authorization: Bearer` 的 JWT `sub`（兼容仅用 `get_current_user` 的端点）。
- `ip`：`X-Forwarded-For` 首段优先，回退 `request.client.host`。
- `method`/`path`：中间件输出。
- `耗时`：装饰器与中间件均用 `time.perf_counter()` 计算（ms）。
- `status_code`：装饰器取业务 envelope 的 `code`；业务抛 `HTTPException` 时取
  `exc.status_code`。

写库失败（DB 不可用 / 表缺失 / 连接异常）：**不抛出**，降级 `logger.error(...,
exc_info=True)`，保证业务响应不被审计影响，且运维可在日志中看到「审计写不下」告警。

---

## 二、§7.3 覆盖矩阵

> 行级 `file:line` 于 2026-07-15 复核，与 `backend/app` 当前源码一致。
> 「装饰器位置」列即实际实现位置；`product_export` 无独立 action（仅 middleware 兜底），不计入具名动作集合。
> `user_disable` / `role_perm_change` / `proposal_confirm` / `quotation_confirm` 为 TODO，未挂装饰器，见 §三。

### 2.1 已落地具名动作（共 29 个，与代码 `@audit_action` 一一对应）

| 模块 | action 值 | 对应 endpoint | 装饰器位置（file:line / 函数） |
| --- | --- | --- | --- |
| 鉴权 | `login`（成功） | `POST /api/v1/auth/login` | `app/api/v1/auth.py:45`（`login`） |
| 鉴权 | `login_failed`（失败） | 同上（业务抛 401 时记） | `app/api/v1/auth.py:45`（`failed_action="login_failed"`） |
| 鉴权 | `logout` | `POST /api/v1/auth/logout` | `app/api/v1/auth.py:115`（`logout`） |
| 鉴权 | `change_password` | `POST /api/v1/auth/change-password` | `app/api/v1/auth.py:134`（`change_password`） |
| 用户 | `user_create` | `POST /api/v1/users` | `app/api/v1/users.py:60`（`create_user`） |
| 用户 | `user_delete` | `DELETE /api/v1/users/{user_id}` | `app/api/v1/users.py:96`（`delete_user`） |
| 产品 | `product_create` | `POST /api/v1/products` | `app/api/v1/products.py:160`（`create_product`） |
| 产品 | `product_delete` | `DELETE /api/v1/products/{product_id}` | `app/api/v1/products.py:196`（`delete_product`） |
| 产品 | `product_status` | `PATCH /api/v1/products/{product_id}/status` | `app/api/v1/products.py:209`（`update_product_status`） |
| 产品 | `product_clone` | `POST /api/v1/products/{product_id}/clone` | `app/api/v1/products.py:227`（`clone_product`） |
| 产品 | `product_import` | `POST /api/v1/products/import` | `app/api/v1/products.py:266`（`import_products`） |
| 文件 | `file_upload` | `POST /api/v1/files/upload` | `app/api/v1/files.py:53`（`upload_file`） |
| 文件 | `file_delete` | `DELETE /api/v1/files/{attachment_id}` | `app/api/v1/files.py:117`（`delete_file`） |
| 文件 | `file_download` | `GET /api/v1/files/{attachment_id}/download` | `app/api/v1/files.py:151`（`download_file`） |
| 文件 | `file_preview` | `GET /api/v1/files/{attachment_id}/preview` | `app/api/v1/files.py:178`（`preview_file`） |
| AI | `polish` | `POST /api/v1/ai/proposal/{proposal_id}/polish` | `app/api/v1/ai.py:113`（`polish_proposal`） |
| AI | `recommend` | `POST /api/v1/ai/recommend` | `app/api/v1/ai.py:129`（`recommend`） |
| 方案 | `proposal_delete` | `DELETE /api/v1/proposals/{proposal_id}` | `app/api/v1/proposals.py:74`（`delete_proposal`） |
| 报价 | `quotation_list` | `GET /api/v1/quotations` | `app/api/v1/quotations.py:44`（`list_quotations`） |
| 报价 | `quotation_detail` | `GET /api/v1/quotations/{id}` | `app/api/v1/quotations.py:109`（`get_quotation`） |
| 报价 | `quotation_create` | `POST /api/v1/quotations` | `app/api/v1/quotations.py:121`（`create_quotation`） |
| 报价 | `quotation_update` | `PUT /api/v1/quotations/{id}` | `app/api/v1/quotations.py:174`（`update_quotation`） |
| 报价 | `quotation_pdf_export` | `GET /api/v1/quotations/{id}/pdf` | `app/api/v1/quotations.py:81`（`export_quotation_pdf`） |
| 分享 | `share_create` | `POST /api/v1/shares` | `app/api/v1/shares.py:15`（`create_share`） |
| 分享 | `share_revoke` | `DELETE /api/v1/shares/{share_id}` | `app/api/v1/shares.py:60`（`revoke_share`） |
| 分享 | `share_access`（成功） | `GET /api/v1/share/{token}` | `app/api/v1/share_token.py:165`（`get_share_content`，`@audit_action`） |
| 分享 | `share_access_denied`（失败） | 同上（业务抛 403/404 时记） | 同上（`failed_action="share_access_denied"`） |
| 统计 | `stats_shares` | `GET /api/v1/stats/shares` | `app/api/v1/stats.py:30`（`stats_shares`） |
| 统计 | `stats_products_hot` | `GET /api/v1/stats/products/hot` | `app/api/v1/stats.py:108`（`stats_products_hot`） |

### 2.2 非具名（middleware 兜底，不落 `operation_log` 具名动作）

| 模块 | 说明 | 位置 |
| --- | --- | --- |
| 产品 | `product_export`：已实现 `GET /api/v1/products/export`，但**不引入独立 action**，仅由 `AuditMiddleware` 通用请求日志兜底 | `app/api/v1/products.py:92`（`export_products`） |

> 注：§7.3 要求登录「成功/失败」分别记录 `login` / `login_failed`。当前 `login`
> endpoint 在凭证错误时抛 `HTTPException(401)`；装饰器 `failed_action="login_failed"`
> 捕获该异常路径并记失败动作，随后**原样抛出**，保证 401 响应行为不变。成功路径写 `login`，
> 并已在 endpoint 内补 `request.state.user_id = str(user.id)`，使审计能正确归属用户。

### 额外说明（验收保留项，现已纳入 §7.3.1 / §二.1）

| action | endpoint | 装饰器位置 | 说明 |
| --- | --- | --- | --- |
| `polish` | `POST /api/v1/ai/proposal/{proposal_id}/polish` | `app/api/v1/ai.py:113` | 早期 §7.3 未列，但验收要求 polish 调用产生 `operation_log`；原 `app/services/polish.py` 手写块已移除。本轮已登记进 §7.3.1 / §二.1，保持三方一致 |
| `recommend` | `POST /api/v1/ai/recommend` | `app/api/v1/ai.py:129` | 同上，移除 `app/services/recommend.py` 手写块；已登记进 §7.3.1 / §二.1 |

---

## 三、实际实现位置与未覆盖项

§7.3.1 已落地的 29 个具名动作，其实际实现位置（`@audit_action` 装饰器所在 `file:line` + 函数名）
见 §二.1，与 `backend/app` 当前源码**完全一致**。本节仅记录「尚未落地具名动作」的缺口与原因，
以及一处非具名兜底（`product_export`）。所有未落地项均**不登记**具名 `operation_log` 动作，
遵守「文档不得登记代码中不存在的动作」约束。

### 3.1 仍 TODO（无对应接口，未挂 `@audit_action`）

- **`user_disable`**【状态：仍 TODO】：`app/api/v1/users.py` 仅有 `PUT /users/{user_id}`
   （`UserUpdate.status` 可设为 disabled）与 `DELETE`。无独立的「停用」语义 endpoint。`PUT`
   同时承担邮箱/电话/角色变更，强行记 `user_disable` 会污染审计语义。→ 待新增
   `POST /users/{user_id}/disable`（或类似）后挂 `audit_action("user_disable", module="users", ...)`。

- **`role_perm_change`**【状态：仍 TODO】：`app/api/v1/roles.py` 的 `PUT /roles/{role_id}` 仅
   更新 role 元数据（role_name/role_code/description），`RoleCreate.permission_ids` schema 字段
   存在但路由内**未实际持久化**角色-权限关联（无 `RolePermission` 写入逻辑）。故未挂装饰器。
   → 待新增显式权限变更接口（如 `PUT /roles/{role_id}/permissions`）后挂
   `audit_action("role_perm_change", module="roles", ...)`。

- **`proposal_confirm`**【状态：仍 TODO】：`app/api/v1/proposals.py` 无确认 endpoint（`PUT`
   仅改名/客户，`update_proposal` 内拒绝对 `confirmed` 方案修改，但无把方案置为 `confirmed`
   的入口）。→ 待新增 `POST /api/v1/proposals/{proposal_id}/confirm` 后挂
   `audit_action("proposal_confirm", module="proposals")`。

- **`quotation_confirm`**【状态：仍 TODO】：`app/api/v1/quotations.py` 已有列表/详情/创建/更新/PDF
   共 5 接口，但**尚无把报价单置为 `confirmed` 的 `/confirm` endpoint**（PUT 对已 confirmed 报价单
   返回 42201 仅作保护），故 `quotation_confirm` 动作**仍留 TODO**。→ 待新增
   `POST /api/v1/quotations/{id}/confirm` 后挂 `audit_action("quotation_confirm", module="quotations")`。

### 3.2 非具名兜底（接口已实现，但不落具名 `operation_log` 动作）

- **`product_export`**（产品导出）：`app/api/v1/products.py:92`（`export_products`）已实现
   `GET /api/v1/products/export`，复用 `list_products` 同款 Query 过滤，由独立 service
   `app/services/products_export.py` 生成 Excel 二进制流。按角色边界：`role_code != 'sales'` 保留
   cost_price 列；`sales` 角色该列置零（抹零，不泄露成本价）。**不引入** `product:export` 权限点，
   也**不引入**独立 audit action——由 `AuditMiddleware` 通用请求日志兜底，不落具名 `operation_log`。

> 说明：`product_clone` / `product_import` / `file_upload` / `file_delete` / `file_download` /
> `file_preview` / `share_access` / `share_access_denied` 已于本轮交付并在 §二.1 登记，不再列入缺口。
> 当前 §7.3 具名动作集合 = §二.1 的 29 项；缺口仅剩 §3.1 的 4 项 TODO，均不登记具名动作。

---

## 四、移除的「哑审计」

按 §7.3「业务层无需手动调用」，移除两处违反规范的手写 `OperationLog` 块（原均包在
`try/except Exception: pass` 中——审计失败无感知，且 `ip="127.0.0.1"` 丢失真实 IP，
违反 §7.2）：

- `app/services/polish.py:117-130`（原）→ 已删，改由 `ai.py:113` 装饰器记录。
- `app/services/recommend.py:103-116`（原）→ 已删，改由 `ai.py:129` 装饰器记录。

两个 service 文件净行数下降（删手写块 > 加装饰器行），无 `try/except Exception: pass`
形态残留。

---

## 五、测试

`backend/tests/test_audit.py`（8 用例，全部 mock，不依赖真 DB）覆盖：

1. 成功路径：action/module/user_id/ip/response_code/target_id 正确落库。
2. `X-Forwarded-For` 优先于 `client.host`。
3. 业务抛 `HTTPException`：`failed_action` 生效，`response_code` 取 `exc.status_code`，原异常仍抛出。
4. 无 `failed_action` 时失败回落到原 `action` + 错误 status。
5. 写库失败：`AsyncSessionLocal` 构造异常 → 业务响应不受影响，降级 ERROR 日志。
6. 业务 envelope `code` 非 200 时 `response_code` 跟随。
7. `request.state` 无 user_id 时回退解码 Bearer JWT `sub`。
8. 模块顶层 import 不再触碰 `app.core.database`（纯装饰器逻辑可单元化）。
