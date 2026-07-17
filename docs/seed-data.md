# 初始化种子数据（docs/03 §十二）

> 本文档与 `alembic/versions/0004_seed_data.py` 及 `app/scripts/seed_data.py` 三处保持一致。
> 执行入口二选一：① `alembic upgrade head`（数据迁移，装后自动）；② `python -m app.scripts.seed_data`（脚本，可重复/可校验）。
> 二者均**幂等**：重复执行不会重复插入。

## 1. 角色 `role`（4 条）

| role_code | role_name | description |
| --- | --- | --- |
| `admin` | 系统管理员 | 拥有全部权限，含角色与权限管理 |
| `purchaser` | 采购员 | 负责产品与供应商的维护 |
| `sales` | 销售员 | 负责方案/报价/分享，查看产品信息 |
| `viewer` | 访客 | 只读查看产品与统计看板 |

```sql
INSERT INTO role (role_name, role_code, description) VALUES
  ('系统管理员', 'admin',     '拥有全部权限，含角色与权限管理'),
  ('采购员',     'purchaser', '负责产品与供应商的维护'),
  ('销售员',     'sales',     '负责方案/报价/分享，查看产品信息'),
  ('访客',       'viewer',    '只读查看产品与统计看板');
```

## 2. 权限 `permission`

字段：`perm_code`、`perm_name`、`resource`、`action`、`type`（`read`=查看类 / `write`=写入变更类）。

| perm_code | perm_name | resource | action | type |
| --- | --- | --- | --- | --- |
| `product:view` | 产品查看 | product | view | read |
| `product:create` | 产品新增 | product | create | write |
| `product:edit` | 产品编辑 | product | edit | write |
| `product:delete` | 产品删除 | product | delete | write |
| `product:import` | 产品导入 | product | import | write |
| `product:export` | 产品导出 | product | export | read |
| `product:status` | 产品上下架 | product | status | write |
| `product:clone` | 产品克隆 | product | clone | write |
| `category:view` | 品类查看 | category | view | read |
| `category:create` | 品类新增 | category | create | write |
| `category:edit` | 品类编辑 | category | edit | write |
| `category:delete` | 品类删除 | category | delete | write |
| `brand:view` | 品牌查看 | brand | view | read |
| `brand:create` | 品牌新增 | brand | create | write |
| `brand:edit` | 品牌编辑 | brand | edit | write |
| `brand:delete` | 品牌删除 | brand | delete | write |
| `tag:view` | 标签查看 | tag | view | read |
| `tag:create` | 标签新增 | tag | create | write |
| `tag:edit` | 标签编辑 | tag | edit | write |
| `tag:delete` | 标签删除 | tag | delete | write |
| `supplier:view` | 供应商查看 | supplier | view | read |
| `supplier:create` | 供应商新增 | supplier | create | write |
| `supplier:edit` | 供应商编辑 | supplier | edit | write |
| `supplier:delete` | 供应商删除 | supplier | delete | write |
| `user:view` | 用户查看 | user | view | read |
| `user:create` | 用户新增 | user | create | write |
| `user:edit` | 用户编辑 | user | edit | write |
| `user:disable` | 用户停用 | user | disable | write |
| `user:delete` | 用户删除 | user | delete | write |
| `role:view` | 角色查看 | role | view | read |
| `role:create` | 角色新增 | role | create | write |
| `role:edit` | 角色编辑 | role | edit | write |
| `role:delete` | 角色删除 | role | delete | write |
| `role:assign` | 角色授权 | role | assign | write |
| `proposal:view` | 方案查看 | proposal | view | read |
| `proposal:create` | 方案新增 | proposal | create | write |
| `proposal:edit` | 方案编辑 | proposal | edit | write |
| `proposal:confirm` | 方案确认 | proposal | confirm | write |
| `proposal:delete` | 方案删除 | proposal | delete | write |
| `quotation:view` | 报价查看 | quotation | view | read |
| `quotation:create` | 报价新增 | quotation | create | write |
| `quotation:edit` | 报价编辑 | quotation | edit | write |
| `quotation:confirm` | 报价确认 | quotation | confirm | write |
| `quotation:delete` | 报价删除 | quotation | delete | write |
| `share:view` | 分享查看 | share | view | read |
| `share:create` | 分享创建 | share | create | write |
| `share:delete` | 分享删除 | share | delete | write |
| `file:view` | 文件查看 | file | view | read |
| `file:upload` | 文件上传 | file | upload | write |
| `file:delete` | 文件删除 | file | delete | write |
| `stats:view` | 统计查看 | stats | view | read |
| `audit:view` | 审计日志查看 | audit | view | read |
| `ai:use` | AI 能力使用 | ai | use | write |

## 3. 角色-权限映射 `role_permission`

- `admin` → 全部权限（`*`）
- `purchaser` → `product:*` + `category:*` + `brand:*` + `tag:*` + `supplier:*` + `file:view` + `file:upload` + `stats:view`
- `sales` → `product:view` + `product:export` + `proposal:*` + `quotation:*` + `share:*` + `file:view` + `file:upload` + `stats:view` + `ai:use`
- `viewer` → `product:view` + `stats:view`

> 敏感字段（成本价/供应商等）的可见性由 `app/core/serializers.py` 的 `SENSITIVE_FIELDS_BY_ROLE` 控制，`sales`/`viewer` 默认被屏蔽，与权限点无关。

## 4. 执行顺序与回滚

1. 执行顺序：`role` → `permission` → `role_permission`（脚本与迁移均按此序）。
2. 回滚（`alembic downgrade -1` 或迁移 `downgrade()`）：
   - 先清 `role_permission` 关联（按种子 code 过滤）；
   - 再删 `permission` 种子；
   - 最后删 `role` 种子——**仅删除无 `user` 引用的角色**，避免外键冲突（如 `admin` 已被初始用户引用则保留）。
