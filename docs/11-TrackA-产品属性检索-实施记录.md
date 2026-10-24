# Track A：通用产品属性检索 — 实施记录

> 本文记录 Track A（可扩展的冷门/刁钻/组合产品检索）的改造内容、验收方式与遗留事项。
> 目标不是给「弧形会议桌」加特例，而是建立数据驱动的属性检索基座。

## 1. 迁移链修复（前置阻塞项）

### 1.1 发现的问题

目标仓库 `backend/alembic/versions/` 中 **0018、0019 从未存在于 git 历史**，
而本地数据库的 `alembic_version` 停在 `0018_crm_core`：

| 证据 | 结论 |
| --- | --- |
| `git log --all --diff-filter=ADR -- "backend/alembic/versions/0018*"` 为空 | git 从未跟踪过 0018/0019 |
| `git rev-list --all --objects` 全量对象扫描无 `crm_detail` | 无 dangling blob 可恢复 |
| 本地库 `alembic_version = 0018_crm_core`，但仓库无该 revision 文件 | 「跑过但文件丢失」 |
| 运行中的 `richangpim-backend` 镜像 `/app/alembic/versions/` 含 `0018_crm_core.py`，但不含 `0019_crm_detail.py` | 镜像与源码不一致 |
| `docs/10-客户项目与新媒体(CRM-Lite).md:832-833` 描述 0018/0019 应建的表 | 表已在库中（由 `create_all` 建出），但无迁移记录 |

**后果**：全新库 `alembic upgrade head` 会在 `0020_crm_perms` 处报
`Can't locate revision identified by '0017_operation_log_username'` 之外的问题——
实际上 `0020` 的 `down_revision` 指向 `0017`，而库停在无人知晓的 `0018`，
`alembic upgrade head` 会失败，`downgrade` 亦不可用。

### 1.2 修复方案（已执行，本地库已同步）

| 文件 | 动作 |
| --- | --- |
| `0018_crm_core.py` | **从运行中镜像逐字节恢复**（`docker cp`），内容与库中已执行的一致 |
| `0019_crm_detail.py` | **新建幂等迁移**：把 `create_all` 已建出的 9 张 CRM 表纳入版本管理，并补 `proposal.customer_id/project_id` 外键 |
| `0020_crm_perms.py` | `down_revision` 由 `0017_operation_log_username` 改为 `0019_crm_detail`；同时修复 downgrade 删除顺序缺陷 |
| `0021_content_tables.py`、`0022_reminders.py` | 加 `IF NOT EXISTS` 幂等守卫，使链可在「已被 create_all 建过表」的既有库上前进 |

0019 的 DDL 全部幂等（`has_table` / `has_index` / `has_fk` 守卫），`downgrade` 只删
本迁移真正创建的对象，因此：

- **全新库**：`0001 → … → 0017 → 0018 → 0019 → 0020 → 0021 → 0022 → 0023` 全通；
- **既有库**（本地 ai_pim 与任何 `create_all` 建过的库）：0019/0021/0022 为 no-op 或安全补齐，
  `upgrade head` 不再报 DuplicateTable。

0020 downgrade 原实现只按 `ROLE_PERMISSION_MAP` 删 role_permission，
漏删其他角色写入的映射，导致 `DELETE FROM permission` 触发
`role_permission_permission_id_fkey` 违反。已改为先按权限码全量删映射再删权限。

### 1.3 验证（一次性容器 + 独立 scratch 库，未动 ai_pim 之外的数据）

```
全新库 ai_pim_mig:   upgrade head → 0023 (head)
                     downgrade 0017 → 0017
                     upgrade head  → 0023 (head)          ✅
既有路径 ai_pim_mig2: upgrade head → 0023 (head)
                     downgrade -2   → 0020
                     upgrade head  → 0023 (head)          ✅
本地 ai_pim:         upgrade head → 0023 (head)，FK 已补    ✅
```

`scripts/test_pg_up.sh` 的既有约定（`alembic upgrade head && downgrade -1 && upgrade head`）
已被上述流程覆盖。

## 2. 属性数据模型（新增）

`backend/app/models/catalog_attribute.py`：

| 表 | 关键列 |
| --- | --- |
| `catalog_attribute_definition` | `code`(唯一，部分索引)、`data_type`(option/text/number/range)、`multi_value`、`searchable`、`hard_filterable`、`enabled`、`sort_order`、软删+审计 |
| `catalog_attribute_option` | `attribute_id`、`code`、`label`、`enabled`、`sort_order`，`(attribute_id, code)` 唯一 |
| `catalog_attribute_alias` | `option_id`、`alias`、`normalized_alias`、`source`、`enabled`，`(option_id, normalized_alias)` 唯一 |
| `product_attribute_value` | `product_id`、`attribute_id`、`option_id`(可空)、`value_text`、`value_num`、`unit`、`source`、`verified`、`confidence`、`note` |

索引：`ix_pav_product` / `ix_pav_attribute` / `ix_pav_option` / `ix_pav_number`，
以及 `uq_pav_product_option`、`uq_pav_product_text` 两个部分唯一约束。

`category` 仍复用现有 Category 树，未新建产品分类表。
`Product.material_description` 为新增 nullable Text（材质说明独立于 description）。

`0023_catalog_attributes.py` 另外启用 `pg_trgm` 并在 `product_name/product_no/material`
上建 `gin_trgm_ops` 索引用于中文模糊文本召回（不引入 ES / 独立向量库）。

## 3. 查询理解契约（新增 `app/knowledge/attributes.py`）

替代原先写死的 `category`/`shape` 两维词表：

```python
class ProductQuery(BaseModel):
    hard_facets: list[HardFacet]      # attribute_code / values / required / match_mode / source / confidence
    numeric_filters: list[NumericFilter]  # attribute_code / min_value / max_value / unit
    exclude_values: list[HardFacet]   # 「不要黑色」「排除圆形」
    soft_terms: list[str]
    unknown_terms: list[str]          # 未识别但不静默丢弃
    sort / sort_order / clarification_needed
```

语义保证（单测覆盖）：

- 不同属性之间 **AND**；
- 同一属性已确认同义词 **OR**（`match_mode=any`）；
- `match_mode=all` 用 `GROUP BY … HAVING count(distinct option) >= n` 实现；
- 明确的 shape/material/color 只匹配各自属性；
- **属性缺失不算命中**（`IN` 语义天然排除）；
- 不用 description/material 自由文本或 style 标签替代 shape；
- 不因为没有结果而静默移除硬条件。

词典来自数据库（`catalog_attribute_*`），带 `normalize_text`（NFKC + 去空白 + casefold），
最长词匹配，支持中文无空格。规则解析出的硬条件优先级高于模型条件；
模型输出必须通过属性字典校验（未知 `attribute_code`/`option` 一律丢弃）。

## 4. 业务确认数据回填

| 文件 | 说明 |
| --- | --- |
| `backend/app/scripts/seed_attribute_dictionary.py` | 幂等种子：11 个属性定义、24 个选项、231 条中文同义词、158 个来自 Category 树的 category 选项 |
| `backend/app/scripts/data/product_attribute_mapping.json` | 独立 mapping 文件，**不含任何 SKU 硬编码在解析器里** |
| `backend/app/scripts/backfill_product_attributes.py` | `--check` 只读预览 / `--apply` 写库；幂等；绝不从 material/description/specification 推断 shape |
| `backend/app/scripts/fix_category_option_codes.py` | 一次性维护：把早期误写成 UUID 的 category 选项 code 修正为类目名 |

三个业务确认产品已写入本地库 `product_attribute_value`（`shape=arc`，`source=business_confirmed`，`verified=true`）：

| 业务 SKU | product_no | product_name |
| --- | --- | --- |
| EN74-2.320162 | P-104300001 | EN74-2.320162会议桌 |
| EN74-2.420200 | P-104300002 | EN74-2.420200会议桌 |
| EN74-2.540250 | P-104300003 | EN74-2.540250会议桌 |

> 注：本地库的 `product_no` 是 `P-1043000xx`，`EN74-2.x` 是 `product_name` 前缀（系列号）。
> mapping 文件按真实 `product_no` 编写，并在 `_comment` 中注明对应关系。

## 5. 检索三层（`app/knowledge/tools/product.py`）

1. **结构化精确过滤**：`_attribute_predicate`（option/text/number）+ `_category_predicate`
   （递归 CTE 取子孙类目）+ `_numeric_predicate`。硬条件全部满足才进 primary products。
2. **文本召回**：`_text_recall` 用 `_search_term` 的 OR 组 + pg_trgm 相关排序，
   仅补充软词命中，**不冒充属性精确命中**。
3. **向量召回**：仍由 `HybridRetriever` 承担，只在 `retrieval.enabled` 时进入，
   无法突破结构化硬条件。

排序：`_apply_ordering` 在 SQL 内完成（含 `split_part` 派生的规格长度），
**先排序后 limit**，修复了原「specification_length 排序在 Python 层、仅前 20 行内比较」的缺陷。

产品响应新增可选字段（旧字段全部保留）：
`match_tier` / `matched_facets` / `match_reason` / `relaxed_conditions` / `unknown_terms` /
`relaxed_candidates` / `text_candidates` / `attributes` / `material_description`。

无精确结果时不再把普通会议桌展示成弧形会议桌：`relaxed_candidates` 与
`text_candidates` 单独返回并标注放宽了哪个条件、是文本命中还是同品类近似，
绝不混入 primary products。

## 6. 验收

### 6.1 本地库真实查询（只读验证）

| 查询 | 硬条件 | 结果 |
| --- | --- | --- |
| 弧形会议桌 | `shape=arc` + `category=会议桌` | **3 个确认 SKU** ✅ |
| 弧型会议台 | `shape=arc` | 3 个确认 SKU ✅（同义归一到 arc） |
| 圆弧形会议桌 | `shape=arc` + `category=会议桌` | 3 个确认 SKU ✅ |
| 弧形洽谈桌 | `shape=arc` + `category=洽谈桌` | 0（不串品类）✅ |
| 新中式弧形会议桌 | `style=new_chinese` + `shape=arc` | 0（style 缺失不算命中）✅ |
| 适合 12 人的弧形会议桌 | `shape=arc` + `category=会议桌` | 3 个确认 SKU ✅ |
| 预算 5000 元以内的弧形会议桌 | 同上 | 3 个确认 SKU ✅ |
| 不要黑色的弧形会议桌 | + `!color=black` | 3 个确认 SKU ✅ |

material 含「弧型」但无 `shape=arc` 的产品（P-104300004~007 水滴型等、普通会议桌）**均未命中**。

### 6.2 自动化测试

```
backend/tests/unit/test_product_attribute_search.py          10 passed
backend/tests/unit/test_attribute_retrieval_eval.py         118 passed
backend/tests/unit/test_model_planner.py                     10 passed
backend/tests/unit（全量）                                  351 passed / 2 skipped
ruff check app/                                            All checks passed
```

118 条评测覆盖：同义词 / 语序变化 / 无空格 / 品类+形状 / 品类+材质+颜色 /
价格+尺寸+人数 / 型号混合自然语言 / 否定条件 / 未知冷门术语 / 无结果 / 近似 / 多轮追问。
验收指标用例：`test_attribute_retrieval_eval_acceptance`（所有弧形变体归一到 `shape=arc`）、
`test_constraint_satisfaction_rate_is_one_hundred_percent`（硬约束满足率 100%）、
`test_eval_suite_size`（≥100 条）。

`test_version_payload.py` 的 2 个失败为**既有问题**（测试需要仓库根的 `frontend/`
与 `portal/` 目录，一次性容器未拷贝），与本次改造无关；改造前基线同样失败。

## 7. 未完成 / 待业务确认

1. **未实现**：对「不要黑色」「排除圆形」只完成了查询理解层与 SQL 层，尚未进入
   第二阶段「否定条件」的完整评测与排序回归。
2. **未回填**：除三个确认 SKU 外，其余 4000+ 产品均无 `shape` 等属性值。
   业务确认后按同格式追加 mapping 即可，脚本幂等。
3. **待业务确认**：`specification_length_mm` / `specification_width_mm` /
   `specification_height_mm` / `seat_count` 目前由 `product.specification` 文本
   （`split_part(specification, '*', n)`）派生，单位为 mm。若规格文本格式变化需重新核对。
4. **待业务确认**：`style`、`series` 的选项集目前是种子文件里的保守集合，
   需业务方补充真实系列号（`EN74`、`EMD70` 已作为示例写入）。
5. **生产数据操作**：见文末清单。**本任务未对生产执行任何命令。**
