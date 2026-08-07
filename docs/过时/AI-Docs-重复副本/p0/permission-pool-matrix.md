# P0 权限池分流矩阵设计

> 版本：P0（草案）
> 状态：待老板确认
> 对齐文档：ADR-010、04-doc §6、05-doc §2/§3/§5、02-doc §2.4

---

## 1. 背景与目标

### 1.1 当前问题

当前系统仅有一个 `ai:use` 权限码（`seed_data.py:97`），仅 admin 和 sales 拥有，purchaser 和 viewer 无此权限。这种单点权限模型存在以下问题：

- **权限粒度过粗**：无法区分「能调用 AI」和「能看到什么数据」两个维度
- **字段投影依赖角色码硬编码**：`serializers.py` 中 `SENSITIVE_FIELDS_BY_ROLE` 仅区分 sales/viewer，未覆盖 purchaser
- **AI 工具调用无权限控制**：所有持有 `ai:use` 的用户都能调用相同的 AI 工具集，无法限制敏感工具（如查成本价、查供应商）
- **无法支撑老板新要求**：「通过用户登录账号的权限分组进行分流权限池，最高权限池可访问成本价、库存、供应商等信息，销售级别不能」

### 1.2 权限池（Permission Pool）概念

引入「权限池」作为**用户角色与 AI 能力之间的中间层**：

```
用户登录 → 读取 role_code → 映射到权限池 → 权限池决定:
  1. 可调用的 AI 工具集（Tool Allowlist）
  2. 字段投影策略（Field Projection Policy）
  3. 可访问的数据范围（Data Scope）
  4. 可执行的写动作（Write Action Policy）
```

权限池不是新的数据库表，而是**代码层定义的命名策略集合**，通过 `role_code` 查找，在 Policy 层、Serializer 层、Tool Registry 层同时生效。

### 1.3 P0 目标

- 设计方案：定义 5 个命名权限池，明确每个池的工具集、字段投影、数据范围
- 产出种子迁移脚本草案：更新 `seed_data.py` 的 PERMISSIONS 和 ROLE_PERMISSIONS
- 不新建数据库表，不改动现有迁移，仅代码层策略化
- 可被 Phase 1 直接落地为 alembic `0013_ai_permission_pools` 迁移

---

## 2. 参考的互联网成熟矩阵方案

### 2.1 主参考：AWS IAM 的 Resource × Action × Effect 矩阵

| AWS IAM 概念 | RiChangPIM 映射 |
|---|---|
| Principal（用户/角色） | `role_code`（admin/purchaser/sales/viewer） |
| Resource（资源 ARN） | 数据字段层级（L1-L4）+ 工具名（product.search/supplier.compare 等） |
| Action（操作） | AI 权限码（ai:access/ai:product/ai:knowledge 等）+ 底层 CRUD 权限 |
| Effect（Allow/Deny） | 权限池判定结果（允许/拒绝 + 原因） |
| Condition（条件） | 动作风险等级（pending_action 需人审） |

**采用原因**：AWS IAM 矩阵模型清晰分离了「谁（Principal）→ 对什么（Resource）→ 做什么（Action）→ 结果（Effect）」，与 RiChangPIM 的五重授权模型（门户能力 AND 底层业务资源 AND 字段策略 AND 文档 ACL AND 动作风险）天然契合。

### 2.2 辅参考：Kubernetes RBAC 的 Role Binding

Kubernetes 通过 `Role`（命名空间级权限）和 `ClusterRole`（集群级权限）的 Binding 将用户/组映射到权限集。RiChangPIM 借鉴其**绑定**思想：

- `role_code` → 权限池（类似 `RoleBinding`）
- 权限池 → 工具白名单 + 字段投影策略（类似 `Role` 的 `rules`）

**不采用 GitHub fine-grained token 方案的原因**：GitHub 的权限模型过于细粒度（每个 repo 每个 action 单独授权），对于 PIM 内部角色分流场景过于复杂，运维成本高。

---

## 3. 权限池定义

基于 04-doc §6 的 7 项 AI 权限码（`ai:access`/`ai:product`/`ai:knowledge`/`ai:quality`/`ai:procurement`/`knowledge:manage`/`knowledge:debug`），结合底层资源权限和字段策略，定义 5 个命名权限池：

### 3.1 权限池总览

| 权限池名称 | 对应角色 | AI 权限码 | 底层权限 | 可见字段层 | 可调工具 | 可执行动作 |
|---|---|---|---|---|---|---|
| `pool_admin` | admin | 全部 7 项 | 全部 | L1-L4 全可见 | 全部工具 | 全部动作（写工具需 pending_action） |
| `pool_purchaser` | purchaser | ai:product, ai:knowledge, ai:procurement, ai:quality | product:\*, supplier:\*, category:\*, brand:\* | L1-L3（可见成本/供应商/采购条件；不可见客户名/报价明细） | product.search/get_many/compare, supplier.compare, quality.summary/list_issues | 读 + 写产品/供应商（写需 pending_action） |
| `pool_sales` | sales | ai:access, ai:product, ai:knowledge | product:view, proposal:\*, quotation:\*, share:\* | L1-L2（不可见成本价/供应商/采购条件；可见产品公开字段、库存状态） | product.search/get_many, proposal.get, share.create | 读 + 写方案/报价/分享（写需 pending_action） |
| `pool_knowledge` | viewer | ai:knowledge | product:view, stats:view | L1（仅文档问答 + 产品搜索；不可见任何 L3 字段） | product.search（仅公开字段投影） | 仅读 |
| `pool_governance` | admin（叠加） | knowledge:manage, knowledge:debug | audit:view | L1-L4 + 元数据 | 全部 + 治理工具（reindex/feedback） | 可见检索分数、工具轨迹 |

### 3.2 权限池详细定义

#### pool_admin（高权限池）

- **角色**：admin
- **AI 权限码**：`ai:access`, `ai:product`, `ai:knowledge`, `ai:quality`, `ai:procurement`, `knowledge:manage`, `knowledge:debug`
- **可见字段层**：L1（产品名/编号/面价/状态）+ L2（材质/规格/颜色/描述）+ L3（成本价/库存/供应商/客户名）+ L4（草稿产品/方案成本/报价明细）
- **可调工具**：全部（product.search, product.get_many, product.compare, quality.summary, quality.list_issues, supplier.compare, proposal.get, share.create, knowledge.reindex, knowledge.feedback）
- **写动作**：全部允许，但 `proposal.create_draft`/`proposal.update_draft`/`quotation.create`/`quotation.edit` 需走 `pending_action` 人审流程（对齐 ADR-011）

#### pool_purchaser（采购级权限池）

- **角色**：purchaser
- **AI 权限码**：`ai:product`, `ai:knowledge`, `ai:procurement`, `ai:quality`
- **可见字段层**：L1 + L2 + L3（成本价/供应商/采购条件可见）；L3 中的客户名不可见；L4 不可见
- **可调工具**：product.search, product.get_many, product.compare, supplier.compare, quality.summary, quality.list_issues
- **不可调工具**：proposal.get（无 proposal:view 权限）, share.create, knowledge.reindex, knowledge.feedback
- **写动作**：product.create/product.edit/supplier.create/supplier.edit 允许，需 pending_action 人审

#### pool_sales（销售级权限池）

- **角色**：sales
- **AI 权限码**：`ai:access`, `ai:product`, `ai:knowledge`
- **可见字段层**：L1 + L2（成本价/供应商/采购条件不可见；库存状态可见但 unknown 显式显示为「待确认」）
- **可调工具**：product.search（字段投影过滤 L3）, product.get_many（同上）, proposal.get, share.create
- **不可调工具**：supplier.compare, quality.list_issues（含供应商信息）, knowledge.reindex
- **写动作**：proposal.create_draft/proposal.edit/quotation.create/quotation.edit/share.create 允许，需 pending_action 人审

#### pool_knowledge（知识查询池）

- **角色**：viewer
- **AI 权限码**：`ai:knowledge`
- **可见字段层**：仅 L1（产品名/编号/面价/状态/品牌/分类）
- **可调工具**：product.search（仅 L1 字段投影）
- **不可调工具**：全部写工具、supplier.compare、quality.\*、proposal.\*、share.create
- **写动作**：无

#### pool_governance（治理调试池）

- **角色**：admin（需同时拥有 `knowledge:manage` + `knowledge:debug` 权限码）
- **可见字段层**：L1-L4 + 检索分数、工具轨迹、embedding 元数据
- **可调工具**：全部 + knowledge.reindex, knowledge.feedback, ai.embeddings, ai.rag_index
- **写动作**：全部允许

---

## 4. 字段分层投影矩阵

对齐 05-doc §2 的 L1~L4 数据分级，将 PIM 实际字段逐项标注：

### 4.1 字段分层定义

| 层级 | 定义 | PIM 字段示例 |
|---|---|---|
| L1（公开） | 所有登录用户可见 | product_no, product_name, face_price, status, brand_name, category_name, description, tags |
| L2（内部） | 除 viewer 外可见 | material, specification, colors, data_source, completeness_status, stock_status, product images |
| L3（敏感） | 仅 admin/purchaser 可见 | cost_price, supplier_id, supplier_name, margin, profit, quotation items（含单价/成本） |
| L4（机密） | 仅 admin 可见 | 草稿产品（status=draft）、方案成本明细、报价确认前明细、AI 检索分数、工具轨迹 |

### 4.2 字段×权限池可见性矩阵

| 字段 | L层 | pool_admin | pool_purchaser | pool_sales | pool_knowledge | pool_governance |
|---|---|---|---|---|---|---|
| product_no | L1 | 可见 | 可见 | 可见 | 可见 | 可见 |
| product_name | L1 | 可见 | 可见 | 可见 | 可见 | 可见 |
| face_price | L1 | 可见 | 可见 | 可见 | 可见 | 可见 |
| status | L1 | 可见 | 可见 | 可见 | 可见 | 可见 |
| brand_name | L1 | 可见 | 可见 | 可见 | 可见 | 可见 |
| category_name | L1 | 可见 | 可见 | 可见 | 可见 | 可见 |
| description | L1 | 可见 | 可见 | 可见 | 可见 | 可见 |
| material | L2 | 可见 | 可见 | 可见 | 不可见 | 可见 |
| specification | L2 | 可见 | 可见 | 可见 | 不可见 | 可见 |
| colors | L2 | 可见 | 可见 | 可见 | 不可见 | 可见 |
| data_source | L2 | 可见 | 可见 | 可见 | 不可见 | 可见 |
| completeness_status | L2 | 可见 | 可见 | 可见 | 不可见 | 可见 |
| stock_status | L2 | 可见 | 可见 | 可见（unknown→「待确认」） | 不可见 | 可见 |
| cost_price | L3 | 可见 | 可见 | **不可见** | 不可见 | 可见 |
| supplier_id | L3 | 可见 | 可见 | **不可见** | 不可见 | 可见 |
| supplier_name | L3 | 可见 | 可见 | **不可见** | 不可见 | 可见 |
| margin/profit | L3 | 可见 | 可见 | **不可见** | 不可见 | 可见 |
| quotation items（单价） | L3 | 可见 | 不可见 | 可见（自己创建的） | 不可见 | 可见 |
| proposal cost details | L4 | 可见 | 不可见 | 不可见 | 不可见 | 可见 |
| draft products | L4 | 可见 | 可见 | 不可见 | 不可见 | 可见 |
| AI retrieval scores | L4 | 可见 | 不可见 | 不可见 | 不可见 | 可见 |
| tool traces | L4 | 可见 | 不可见 | 不可见 | 不可见 | 可见 |

### 4.3 字段投影实现要点

- **Serializer 层**：扩展 `filter_sensitive_fields()` 支持权限池参数，不再仅依赖 `role_code`
- **SQL 层**：`list_products` 等查询接口在 JOIN 时即按权限池过滤敏感字段，而非查出后过滤
- **AI 工具层**：`product.search` 工具在构建上下文时，按权限池过滤召回结果中的敏感字段，禁止将 L3/L4 字段写入 prompt

### 4.4 可插拔原则（Pluggability）

权限池判定遵循 ADR-010/ADR-014，决策器、字段投影规则、池定义均设计为可替换、配置驱动，确保后续接入新业务或调整内部分级时无需改 Gateway 主流程：

| 可插拔维度 | 设计约束 | P0 退出标准 |
| --- | --- | --- |
| 池判定器可替换 | `PermissionPoolResolver` 定义为 `typing.Protocol`，默认实现 `RoleBasedPoolResolver`；后续可加 `AttributeBasedPoolResolver`（基于用户属性而非纯角色），通过 `AI_PERMISSION_POOL_RESOLVER` 注入 | 调用方依赖 Protocol，不 import 具体实现 |
| 池定义配置驱动 | 权限池的内容（哪些 AI 权限码/底层权限/字段层/工具）写在 `seed_data.py` 的 `PERMISSION_POOLS` 常量 + `ai_permission_pool_rule` 表，而非硬编码在 Policy 类里；可由配置文件覆盖 | 改池内容不必改 py 文件 |
| 字段投影策略可替换 | `FieldProjectionStrategy` 抽象 Protocol，默认 `LevelProjectionStrategy` 按 L1-L4 投影；后续可加 `TenantProjectionStrategy`/`OrgUnitProjectionStrategy`（对齐 07-doc §7 文档级 ACL 与组织数据范围） | serializers.py 调用 strategy 而非写 if-else |
| 字段分级可配置化 | L1-L4 字段映射写在 `backend/app/core/field_classifications.py` 配置表，新增字段只改配置不改逻辑 | 新增"客户名"敏感字段只动配置 |
| 工具×池矩阵可替换 | 工具授权矩阵以 `TOOL_PERMISSION_MATRIX` 常量形式存放，新增工具只追加行不动既有判定逻辑 | 新增 supplier.bid_query 工具不改 Policy 主流程 |
| 兼容期软开关 | `AI_PERMISSION_POOL_MODE=compat|strict`：compat 期沿用旧 `ai:use` 单点判定，strict 期启用池判定；切换不重启 | 二者并存且可一行配置切换 |
| fail-closed | 池判定器/投影策略不可用时按 fail-closed 返回最小可见集（仅 L1），不返回更宽结果，对齐 05-doc §1 | 后端异常不导致权限放宽 |

实施要点草图：

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class PermissionPoolResolver(Protocol):
    def resolve(self, user_roles: list[str]) -> PermissionPool: ...

@runtime_checkable
class FieldProjectionStrategy(Protocol):
    def project(self, fields: dict, pool: PermissionPool) -> dict: ...

@runtime_checkable
class ToolAuthorizationPolicy(Protocol):
    def authorize(self, tool_name: str, pool: PermissionPool) -> AuthzResult: ...
```

切流路径：compat 期（`AI_PERMISSION_POOL_MODE=compat`，沿用 `ai:use`）→ strict 期（同一接口切 `RoleBasedPoolResolver`）→ 未来按属性/组织/租户判断只换 Resolver 实现，Gateway/Tool Registry 主流程不动。

---

## 5. 工具×权限池调用授权矩阵

基于 02-doc §2.4 的工具表：

| 工具名 | pool_admin | pool_purchaser | pool_sales | pool_knowledge | pool_governance | 说明 |
|---|---|---|---|---|---|---|
| product.search | 允许 | 允许 | 允许（L1-L2 投影） | 允许（仅 L1） | 允许 | 基础搜索，按池投影 |
| product.get_many | 允许 | 允许 | 允许（L1-L2 投影） | 拒绝 | 允许 | 批量产品详情 |
| product.compare | 允许 | 允许 | 拒绝 | 拒绝 | 允许 | 多产品对比（含敏感字段） |
| quality.summary | 允许 | 允许 | 拒绝 | 拒绝 | 允许 | 数据质量汇总（含供应商信息） |
| quality.list_issues | 允许 | 允许 | 拒绝 | 拒绝 | 允许 | 待补充清单（含供应商/成本字段） |
| supplier.compare | 允许 | 允许 | 拒绝 | 拒绝 | 允许 | 供应商对比（L3 字段） |
| proposal.get | 允许 | 拒绝 | 允许 | 拒绝 | 允许 | 方案详情（sales 仅可见自己的） |
| proposal.create_draft | pending_action | 拒绝 | pending_action | 拒绝 | 允许 | 写工具需人审 |
| proposal.update_draft | pending_action | 拒绝 | pending_action | 拒绝 | 允许 | 写工具需人审 |
| share.create | 允许 | 拒绝 | 允许 | 拒绝 | 允许 | 分享创建 |
| knowledge.reindex | 允许 | 拒绝 | 拒绝 | 拒绝 | 允许 | 仅治理池可用 |
| knowledge.feedback | 允许 | 拒绝 | 拒绝 | 拒绝 | 允许 | 仅治理池可用 |
| ai.embeddings | 允许 | 拒绝 | 拒绝 | 拒绝 | 允许 | 仅 admin/governance |
| ai.rag_index | 允许 | 拒绝 | 拒绝 | 拒绝 | 允许 | 仅 admin/governance |

**拒绝原因标注**：
- sales 拒绝 supplier.compare：含 L3 供应商敏感字段
- sales 拒绝 quality.\*：含成本/供应商字段
- purchaser 拒绝 proposal.\*：无 proposal:view 底层权限
- viewer 拒绝全部写工具：无写权限
- 写工具一律 pending_action：对齐 ADR-011 写动作风险管控

---

## 6. 角色→权限池映射

| 角色（role_code） | 映射权限池 | 兼容期 ai:use 处理 | 多池叠加规则 |
|---|---|---|---|
| admin | pool_admin + pool_governance | ai:use 继续有效，作为降级兜底 | 取并集（全部工具 + 全部字段） |
| purchaser | pool_purchaser | 当前无 ai:use，P0 后新增 ai:product/ai:knowledge/ai:procurement | 单池 |
| sales | pool_sales | ai:use 继续有效，但工具调用受 pool_sales 约束 | 单池 |
| viewer | pool_knowledge | 当前无 ai:use，P0 后新增 ai:knowledge | 单池 |

### 6.1 兼容期过渡策略

- **已有 sales 用户**：保留 `ai:use` 权限码，但工具调用时额外检查权限池规则（`pool_sales` 的工具白名单）
- **已有 admin 用户**：无变化，`ai:use` + admin role_code → pool_admin
- **purchaser/viewer 新增 AI 权限码**：通过 `0013_ai_permission_pools` 迁移新增权限码并映射到角色

### 6.2 多池叠加（未来扩展）

若用户同时拥有多个角色（如 admin + sales），权限池取**并集**（最大权限），但字段投影取**交集**（最严格过滤）。P0 阶段不实现多角色，预留接口。

---

## 7. 服务端五重授权实现要点

对齐 05-doc §3 的五重授权模型，将权限池判定写入各层：

### 7.1 门户能力层（AI 权限码）

- 在 `PermissionChecker` 中增加权限池查找逻辑：根据 `role_code` 查找对应池的 AI 权限码白名单
- 示例：`purchaser` 请求 `/chat` 时，检查是否拥有 `ai:product` 或 `ai:knowledge` 或 `ai:procurement`

### 7.2 底层业务资源层（CRUD 权限）

- 复用现有 `product:view`、`supplier:view` 等权限码
- 工具调用前检查底层权限：如 `supplier.compare` 工具要求 `supplier:view` 权限

### 7.3 字段策略层（字段投影）

- 扩展 `serializers.py` 的 `filter_sensitive_fields()`：
  ```python
  def filter_by_pool(payload: Any, pool: str) -> Any:
      hidden = POOL_FIELD_POLICIES.get(pool, set())
      # 递归过滤 payload 中的 hidden 字段
  ```
- 在 `products.py` 的 `_product_response()` 和 `_product_list_response()` 中调用

### 7.4 文档 ACL 层（RAG 文档访问控制）

- `product_manual_chunk` 查询时增加 `product_id` 过滤（已有实现）
- 未来扩展：文档级 ACL（如某些说明书仅 purchaser 可见）

### 7.5 动作风险层（pending_action）

- 写工具（proposal.create_draft、quotation.create 等）在权限池判定为「允许」后，额外检查是否需要 pending_action
- pending_action 记录写入 `operation_log`，由管理员审批后生效

### 7.6 禁止只靠提示词

**关键原则**：权限判定必须在 Tool Registry 层和 Serializer 层完成，禁止将敏感字段写入 LLM prompt 后指望模型不输出。

```python
# 错误做法（禁止）：
context = "成本价是 100 元"  # 写入 prompt
# 指望模型不输出成本价

# 正确做法（必须）：
if pool not in POOLS_WITH_COST_ACCESS:
    context = "成本价：无权访问"  # 工具层即过滤
```

---

## 8. Alembic 迁移草案

迁移名：`0013_ai_permission_pools`

### 8.1 新增权限码（更新 PERMISSIONS）

```python
# 在 seed_data.py 的 PERMISSIONS 列表中新增：
("ai:access", "AI 助手访问", "ai", "access", "write"),
("ai:product", "AI 产品查询", "ai", "product", "write"),
("ai:knowledge", "AI 知识问答", "ai", "knowledge", "write"),
("ai:quality", "AI 质量查询", "ai", "quality", "write"),
("ai:procurement", "AI 采购查询", "ai", "procurement", "write"),
("knowledge:manage", "知识索引管理", "knowledge", "manage", "write"),
("knowledge:debug", "知识调试", "knowledge", "debug", "write"),
```

### 8.2 更新角色-权限映射（更新 ROLE_PERMISSIONS）

```python
# purchaser 新增 AI 权限码：
"purchaser": [
    # ... 现有权限 ...
    "ai:product",
    "ai:knowledge",
    "ai:procurement",
    "ai:quality",
],

# viewer 新增 AI 权限码：
"viewer": [
    # ... 现有权限 ...
    "ai:knowledge",
],

# sales 保留 ai:use（兼容期），同时建议逐步迁移到 ai:access/ai:product/ai:knowledge：
"sales": [
    # ... 现有权限 ...
    "ai:use",           # 兼容期保留
    # "ai:access",      # 未来迁移
    # "ai:product",
    # "ai:knowledge",
],
```

### 8.3 不新建权限池表

权限池定义在 `seed_data.py` 代码中（作为 Python 常量），投影规则在 `serializers.py` 配置化。原因：
- 权限池是策略概念，不是业务实体
- 池与角色的映射是 1:1（P0 阶段），无需独立表
- 避免过早抽象，后续如需多角色多池叠加再考虑建表

### 8.4 迁移脚本结构

```python
"""0013_ai_permission_pools

Revision ID: 0013_ai_permission_pools
Revises: 0012_product_scene_image_partial_unique
Create Date: 2026-07-XX

新增 AI 权限池相关权限码，并映射到 purchaser/viewer 角色。
"""

from alembic import op
import sqlalchemy as sa

# 不新建表，仅通过 seed_data 插入权限码和映射
# 实际插入逻辑在 seed_data.py 的 _ensure_permissions 和 _ensure_role_permissions 中
```

---

## 9. 验收用例矩阵

对齐 07-doc §10.3 安全测试矩阵：

| # | 测试场景 | 角色 | 操作 | 期望结果 | 验证点 |
|---|---|---|---|---|---|
| 1 | 销售越权查成本价 | sales | 调用 AI 问「A100 成本价多少」 | AI 回答「无权访问成本价信息」 | 成本价字段未出现在 prompt 中 |
| 2 | 销售越权查供应商 | sales | 调用 AI 问「A100 的供应商是谁」 | AI 回答「无权访问供应商信息」 | supplier_name 被 serializer 过滤 |
| 3 | 采购越权查报价明细 | purchaser | 调用 AI 问「QT-2026-0001 的报价明细」 | AI 回答「无权访问报价信息」 | proposal.get 工具拒绝调用 |
| 4 | viewer 调 ai:product | viewer | 调用 AI 问「推荐一款户外摄像头」 | AI 回答「无权使用产品推荐功能」 | ai:product 权限码检查拒绝 |
| 5 | viewer 仅文档问答 | viewer | 调用 AI 问「A100 怎么安装」 | AI 正常回答（基于说明书 RAG） | 仅 ai:knowledge 权限码生效 |
| 6 | admin 全可见 | admin | 调用 AI 问「A100 成本价和供应商」 | AI 正常回答含成本价和供应商 | 全部字段可见 |
| 7 | 权限 SSE 降级 | 任意 | AI 服务不可用时 | 返回 503，不泄露字段信息 | 错误消息不含敏感数据 |
| 8 | 写工具 pending_action | sales | 创建方案草稿 | 方案状态为 pending，需审批 | operation_log 记录 pending_action |
| 9 | 导出脱敏 | sales | 导出产品 Excel | 不含 cost_price/supplier_name 列 | build_excel_bytes 按 role_code 过滤 |
| 10 | 权限判定不依赖模型 | 任意 | 越权请求 | 403 拒绝，非模型决定 | PermissionChecker 层拦截 |

---

## 10. 老板待确认项清单

对齐 07-doc §13 第 2 条：

| # | 待确认项 | 建议方案 | 风险 | 确认人 |
|---|---|---|---|---|
| 1 | purchaser 可用哪些 AI 助手 | pool_purchaser（ai:product/ai:knowledge/ai:procurement/ai:quality） | 采购可查产品质量问题，可能暴露供应商短板 | 老板 |
| 2 | viewer 可用哪些 AI 助手 | pool_knowledge（仅 ai:knowledge，仅文档问答） | 访客可能通过问答套取产品信息 | 老板 |
| 3 | 采购敏感字段最终矩阵 | cost_price/supplier_name 对 purchaser 可见；quotation items 对 purchaser 不可见 | 采购看到报价明细可能影响销售策略 | 老板 |
| 4 | sales 的 ai:use 兼容期时长 | 建议 3 个月，之后强制迁移到 ai:access/ai:product/ai:knowledge | 迁移期间权限码冗余 | 老板 |
| 5 | 多角色用户（如 admin + sales）的权限池叠加规则 | P0 暂不支持，预留接口 | 未来扩展时可能需改迁移 | 老板 |
| 6 | pending_action 人审流程的具体实现 | 写工具创建草稿后状态为 pending，管理员在后台审批通过后生效 | 审批流程可能影响销售效率 | 老板 |

---

## 附录 A：权限池策略配置（代码草案）

```python
# backend/app/core/permission_pools.py

from enum import StrEnum

class PermissionPool(StrEnum):
    ADMIN = "pool_admin"
    PURCHASER = "pool_purchaser"
    SALES = "pool_sales"
    KNOWLEDGE = "pool_knowledge"
    GOVERNANCE = "pool_governance"

ROLE_POOL_MAP: dict[str, PermissionPool] = {
    "admin": PermissionPool.ADMIN,
    "purchaser": PermissionPool.PURCHASER,
    "sales": PermissionPool.SALES,
    "viewer": PermissionPool.KNOWLEDGE,
}

POOL_AI_PERMISSIONS: dict[PermissionPool, set[str]] = {
    PermissionPool.ADMIN: {"ai:access", "ai:product", "ai:knowledge", "ai:quality", "ai:procurement", "knowledge:manage", "knowledge:debug"},
    PermissionPool.PURCHASER: {"ai:product", "ai:knowledge", "ai:procurement", "ai:quality"},
    PermissionPool.SALES: {"ai:access", "ai:product", "ai:knowledge"},
    PermissionPool.KNOWLEDGE: {"ai:knowledge"},
    PermissionPool.GOVERNANCE: {"knowledge:manage", "knowledge:debug"},
}

POOL_ALLOWED_TOOLS: dict[PermissionPool, set[str]] = {
    PermissionPool.ADMIN: {"product.search", "product.get_many", "product.compare", "quality.summary", "quality.list_issues", "supplier.compare", "proposal.get", "share.create", "knowledge.reindex", "knowledge.feedback"},
    PermissionPool.PURCHASER: {"product.search", "product.get_many", "product.compare", "supplier.compare", "quality.summary", "quality.list_issues"},
    PermissionPool.SALES: {"product.search", "product.get_many", "proposal.get", "share.create"},
    PermissionPool.KNOWLEDGE: {"product.search"},
    PermissionPool.GOVERNANCE: {"product.search", "product.get_many", "product.compare", "quality.summary", "quality.list_issues", "supplier.compare", "proposal.get", "share.create", "knowledge.reindex", "knowledge.feedback"},
}

POOL_HIDDEN_FIELDS: dict[PermissionPool, set[str]] = {
    PermissionPool.ADMIN: set(),
    PermissionPool.PURCHASER: {"customer_name", "quotation_item_unit_price", "proposal_cost_details", "draft_products", "retrieval_scores", "tool_traces"},
    PermissionPool.SALES: {"cost_price", "supplier_id", "supplier_name", "margin", "profit", "quotation_item_cost", "proposal_cost_details", "draft_products", "retrieval_scores", "tool_traces"},
    PermissionPool.KNOWLEDGE: {"cost_price", "supplier_id", "supplier_name", "margin", "profit", "material", "specification", "colors", "data_source", "completeness_status", "quotation_item_cost", "proposal_cost_details", "draft_products", "retrieval_scores", "tool_traces"},
    PermissionPool.GOVERNANCE: set(),
}
```

## 附录 B：与现有代码的对接点

| 文件 | 对接点 | 改动类型 |
|---|---|---|
| `backend/app/core/permission.py` | `PermissionChecker.__call__` 增加权限池查找 | 扩展 |
| `backend/app/core/serializers.py` | `filter_sensitive_fields` 增加 pool 参数 | 扩展 |
| `backend/app/api/v1/ai.py` | 工具调用前检查 `POOL_ALLOWED_TOOLS` | 扩展 |
| `backend/app/services/recommend.py` | `RecommendService.recommend` 按 pool 过滤推荐结果 | 扩展 |
| `backend/app/scripts/seed_data.py` | 新增 7 个 AI 权限码 + purchaser/viewer 映射 | 扩展 |
| `backend/app/api/v1/products.py` | `_product_response` / `_product_list_response` 按 pool 投影 | 扩展 |
