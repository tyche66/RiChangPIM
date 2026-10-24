# Track C：方案空间、产品快照与客户展示 — 实施记录

> 本文记录 Track C 的改造内容、验收方式与遗留事项。

## 1. 数据模型（新增 `0025_project_spaces`）

| 表 / 列 | 说明 |
| --- | --- |
| `project_spaces`（新表） | `project_id`(CASCADE)、`parent_id`(自引用 CASCADE)、`space_type`(floor/room/zone/other)、`space_name`、`level`、`sort`、软删+审计 |
| `proposal_item.project_space_id` | FK → `project_spaces.id`（SET NULL），可空 |
| `proposal_item.floor_label` / `space_label` | 冗余展示标签，可空 |
| `proposal_item.material_desc` | 明细级材质说明，可空 |
| `proposal_item.product_snapshot` | JSONB 产品事实快照，可空 |
| `quotation_item` 同上五列 | 与方案明细同构，避免报价阶段丢失信息 |

索引：`ix_ps_project`、`ix_ps_parent`、`ix_pi_space`、`ix_qi_space`（均为部分索引）。
约束：`ck_ps_type`、`ck_ps_level`。

**全部新增列先 nullable**，旧方案/旧报价无需回填即可读取。

`Proposal.customer_id` / `Proposal.project_id` 原本已存在于模型与库中（0018 迁移），
本次把 API 接通：`ProposalCreate` / `ProposalUpdate` 接受这两个字段，
`_proposal_to_dict` 输出它们。

## 2. 服务端快照（`app/services/product_snapshot.py`）

```python
await build_product_snapshot(db, product_id)   # 从产品表读取，返回 dict 或 None
merge_snapshot(snapshot, product)               # 快照 > 当前产品 > 「资料未提供」
display_value(value)                            # 单字段兜底
```

快照字段：`product_no` / `product_name` / `category_name` / `material` / `colors` /
`material_description` / `specification` / `face_price`（`99999` 占位价转为 `None`）。

**服务端在创建/修改明细时生成快照，绝不信任前端传入的产品事实**——
`ProposalItemCreate` 只接受 `project_space_id` / `floor_label` / `space_label` /
`material_desc`，`product_snapshot` 不在请求 schema 中。

读取优先级（历史方案稳定展示的关键）：

1. `product_snapshot`（产品改名/改材质也不会漂移）；
2. 当前产品字段；
3. 空值 → 「资料未提供」。

## 3. 后端 API

### 3.1 项目空间（`app/api/v1/project_spaces.py`，前缀 `/api/v1/projects`）

| 方法 | 路径 | 权限 | 审计 |
| --- | --- | --- | --- |
| GET | `/{project_id}/spaces` | `project:view` | — |
| POST | `/{project_id}/spaces` | `project:edit` | `project_space_create` |
| PUT | `/{project_id}/spaces/{space_id}` | `project:edit` | `project_space_update` |
| DELETE | `/{project_id}/spaces/{space_id}` | `project:edit` | `project_space_delete` |

**空间必须属于项目**：创建/更新时校验 `parent_id` 属于同一 `project_id`，
跨项目引用返回 400；父空间不能是自己。删除为软删，并级联软删所有子孙。

### 3.2 方案（`app/api/v1/proposals.py`）

* `ProposalCreate` / `ProposalUpdate` 新增 `customer_id` / `project_id`；
* 明细新增 `project_space_id` / `floor_label` / `space_label` / `material_desc`；
* 创建与更新明细时调用 `build_product_snapshot` 写入 `product_snapshot`；
* `_enrich_item` 输出空间字段、快照，以及按「快照优先」合并的
  `category_name` / `material` / `colors` / `material_description` / `specification`；
* 已确认方案不可修改的状态规则未改动（`status == "confirmed"` → 422）。

### 3.3 分享载荷（`app/api/v1/share_token.py`）

proposal 与 quotation 的每个 item 新增：

```
project_space_id / floor_label / space_label / material_desc
material / colors / material_description / specification / category_name
product_snapshot
```

取值用模块级 `_snapshot_field(snapshot, product, key)` + `functools.partial`
（避免循环闭包捕获），语义为「快照优先、当前产品其次」。

**敏感字段过滤未改动**：`filter_sensitive_fields(raw_content, role_code="sales")`
继续剔除 `cost_price` / `supplier_id` / `supplier_name` / `margin` / `profit`；
分享载荷构造处不引用任何这些字段（有测试锁定）。

## 4. 前端

| 文件 | 改动 |
| --- | --- |
| `src/types/sales.ts` | 新增 `ProjectSpace` / `ProductSnapshot`；`ProposalItem` / `Proposal` / `ProposalItemRequest` / `ProposalCreateRequest` / `ProposalUpdateRequest` / `ShareProductItem` 增加空间与快照字段 |
| `src/api/index.ts` | 新增 `projectSpaceApi`（list/create/update/delete） |
| `src/components/ProposalItemEditor.vue` | 新增 `spaces` prop；有空间时渲染「楼层/空间」级联选择（`el-cascader`，`checkStrictly`）与「材质说明」文本框；选择空间时自动回填 `floor_label`（向上找 floor 祖先）与 `space_label` |
| `src/views/Proposals.vue` | 创建对话框新增「关联客户」「关联项目」；项目变更时加载空间树；提交时带上 `customer_id` / `project_id` 与明细空间/材质说明 |

未选项目时 `spaces` 为空数组，编辑器不渲染空间选择——**没有选择项目时前端不能选择项目空间**。

## 5. 门户分享页（`portal/src/views/SharePage.vue`）

* 新增 `spaceGroups` 计算属性：按 `floor_label + space_label` 分组；
* 每个分组一个 `<section class="space-group">`，标题为「楼层 · 空间」，
  缺失时显示「未指定位置」；
* 商品表新增列：分类 / 材质 / 颜色 / 材质说明 / 规格；
* 材质、颜色、材质说明、规格均按「快照优先、当前产品其次、缺失显示资料未提供」取值；
* 门户 `ShareProductItem` 类型同步扩展（含 `ProductSnapshot`）。

分享端继续使用 token 鉴权，不带 Authorization；敏感字段过滤不变。

## 6. 验收

```
backend/tests/unit/test_project_spaces_and_snapshot.py    15 passed
  ├─ 空间树结构（2 个楼层、房间归属）                        2 cases
  ├─ 空间必须属于项目（跨项目父空间被拒）                    2 cases
  ├─ 快照优先于当前产品（改名/改材质不漂移）                 1 case
  ├─ 无快照时回落当前产品                                    1 case
  ├─ 缺失字段显示「资料未提供」                              1 case
  ├─ 99999 占位价不作为真实价格                              1 case
  ├─ 分享载荷不含敏感字段                                    1 case
  ├─ 分享载荷包含空间与材质字段                              2 cases
  └─ 迁移/模型/schema 契约                                   4 cases
backend tests/unit（全量）                                387 passed
frontend vitest（全量）                                   194 passed
frontend build / portal build                             均通过
vue-tsc（frontend + portal）                              无错误
ruff check app/                                            All checks passed
```

迁移验证（一次性容器 + 独立 scratch 库）：

```
全新库 ai_pim_mig:  upgrade head → 0025_project_spaces (head)
                    downgrade 0017 → 0017
                    upgrade head  → 0025 (head)                       ✅
本地 ai_pim:       upgrade head → 0025 (head)
                    project_spaces 表已建
                    proposal_item / quotation_item 五列已建           ✅
```

## 7. 未完成 / 待业务确认

1. **报价链路的前端联调**：后端 `quotation_item` 已具备空间字段与快照列，
   但 `Quotations.vue` 的「从方案预填」逻辑尚未把 `project_space_id` /
   `floor_label` / `space_label` / `material_desc` / `product_snapshot`
   一起复制过来（当前只复制 `product_id/quantity/unit_price/tax_rate`）。
   属展示联调，不影响数据模型与安全边界。
2. **报价 PDF**：`GET /api/v1/quotations/{id}/pdf` 的 HTML 模板尚未加入
   楼层/空间、材质、颜色列。Gotenberg 链路本身未改动。
3. **ProposalDetail.vue**：详情页尚未展示空间列与材质说明（数据已由
   `_enrich_item` 返回，属纯展示补充）。
4. **待业务确认**：`floor_label` / `space_label` 目前由前端在选空间时回填
   （`floor_label` 取最近的 floor 祖先名）。若业务希望用「1F」「一层」这类
   固定写法，需要在空间树上加展示名字段。
5. **生产数据操作**：见文末清单。**本任务未对生产执行任何命令。**
