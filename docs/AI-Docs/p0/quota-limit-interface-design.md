# P0 限额与成本治理接口设计方案

> 设计状态：**P0 阶段接口契约设计，不实现代码。** 本文档定义 AI 限额与成本治理的接口协议、Pydantic schema 草图和 Redis 存储策略，Phase 1 接入 Knowledge Gateway 时实现 QuotaCheck 中间件。

---

## 1. 目标与范围

### 1.1 目标

在模型供应商尚未确定、无预算上限的前提下，预埋统一的限额与成本治理接口，确保 AI 能力上线后：

- 系统、角色、用户三级频率限制可配置、可拦截、可观测；
- Token 与美元双维度额度可控，预算分级降级；
- 成本估算可查询、可审计；
- 与既有代码解耦，不修改现有 `_persist_conversation` 审计逻辑。

### 1.2 P0 范围

- **只做接口契约设计**：定义请求/响应 schema、拒绝原因码、Redis key 设计、配置项清单。
- **不写实现代码**：Phase 1 在 Knowledge Gateway 中实现 QuotaCheck 中间件。
- **不启用真实限流**：`AI_QUOTA_CHECK_ENABLED=false` 时只记录用量、不拦截，便于基线测量。

### 1.3 限额维度

| 维度 | 说明 | 存储周期 |
|------|------|----------|
| 频率限制（系统/角色/用户） | QPS、并发流、每分钟/每日次数 | 滑窗计数，秒级过期 |
| Token 额度 | 按 provider/model/capability/direction 统计 | 按日 reset |
| 成本额度（美元） | 按单价表估算累计 | 按日 reset |
| 能力开关 | 非关键能力降级/关闭 | 实时生效 |

---

## 2. 三层频率限制设计

对齐 06-doc §6 第1条"设置系统、角色和用户三级频率限制"。

### 2.1 系统级

| 配置项 | 初始建议值 | 说明 |
|--------|------------|------|
| `AI_LIMIT_TPS` | 10 | 全局 QPS 上限（基于 06-doc §2 峰值 5 RPS × 2 冗余） |
| `AI_LIMIT_CONCURRENT_STREAMS` | 40 | 全局并发流上限（基于正常并发 20 × 2 冗余） |
| `AI_LIMIT_SYSTEM_DAILY_CALLS` | 50000 | 日模型调用总上限（占位值，待供应商定档后校准） |

### 2.2 角色级

| 角色 | 每分钟次数 | 每日次数 | 并发流 | 说明 |
|------|-----------|----------|-------|------|
| `admin` | 60 | 5000 | 10 | 管理员，最高配额 |
| `sales` | 30 | 2000 | 5 | 销售，中等配额 |
| `procurement` | 30 | 2000 | 5 | 采购，中等配额 |
| `guest` | 10 | 500 | 2 | 访客，最低配额 |

> 注：以上为占位值，待供应商定档后根据合同限额校准。

### 2.3 用户级

| 配置项 | 初始建议值 | 说明 |
|--------|------------|------|
| `AI_LIMIT_USER_PER_MIN` | 20 | 单用户每分钟最大调用次数 |
| `AI_LIMIT_USER_PER_DAY` | 500 | 单用户每日最大调用次数 |
| `AI_LIMIT_USER_CONCURRENT_STREAMS` | 3 | 单用户最大并发流 |

### 2.4 限流算法

采用 **滑窗计数器（Sliding Window Counter）** 实现，存储于 Redis，通过 Lua 脚本保证原子性。不采用固定窗口（避免边界突刺）或令牌桶（实现复杂度较高）。

---

## 3. 额度限制设计（Token 与美元双维度）

### 3.1 系统日额度上限

按 06-doc §6 "每日按能力统计：规划/回答/Embedding/重排"：

| 配置项 | 初始建议值 | 说明 |
|--------|------------|------|
| `AI_LIMIT_SYSTEM_DAILY_TOKENS` | 10_000_000 | 系统日 Token 上限（占位值） |
| `AI_LIMIT_SYSTEM_DAILY_COST_USD` | 100.0 | 系统日成本上限（美元，占位值） |

### 3.2 用户日额度上限

| 配置项 | 初始建议值 | 说明 |
|--------|------------|------|
| `AI_LIMIT_USER_DAILY_TOKENS` | 100_000 | 单用户日 Token 上限（占位值） |
| `AI_LIMIT_USER_DAILY_COST_USD` | 5.0 | 单用户日成本上限（美元，占位值） |

### 3.3 预算分级降级

对齐 06-doc §5 告警"日成本达到日预算 80%"：

| 预算使用率 | 系统行为 |
|-----------|----------|
| < 80% | 正常 |
| ≥ 80% | 发送 P1 告警通知，收紧非关键能力额度 |
| ≥ `AI_BUDGET_DISABLE_RATIO`（默认 100%） | 关闭非关键能力（重排、批量重建、推荐润色），保留核心 Chat/Embedding |

### 3.4 超额行为

- **非关键能力降级优先**：先关闭 reranking、bulk reindex、proposal polish、recommend 等非关键能力。
- **不直接返回 503**：核心 Chat/Embedding 能力在预算耗尽后仍可服务，但返回 `BUDGET_EXHAUSTED` 原因码和降级提示。
- **用户侧额度耗尽**：返回 `QUOTA_EXCEEDED`，不降级。

---

## 4. 成本估算接口

### 4.1 单价表数据结构

供应商未定档时，所有价格字段为 `NULL` 占位：

```python
class ModelPricing:
    provider: str | None           # 供应商标识，如 "openai"、"azure"、"anthropic"
    model: str | None              # 模型标识，如 "gpt-4o-mini"
    capability: str                # "chat" / "embedding" / "reranking" / "planning"
    input_price_per_1k_tokens: float | None   # 输入价格（美元/千 Token）
    output_price_per_1k_tokens: float | None  # 输出价格（美元/千 Token）
    embedding_price_per_1k_tokens: float | None  # Embedding 价格（美元/千 Token）
    effective_date: date | None     # 生效日期
```

单价表存储于 `ai_model_pricing` 数据库表，支持管理员 CRUD。`AI_ESTIMATED_PRICE_TABLE_PATH` 配置项支持从 CSV/JSON 文件批量导入。

### 4.2 成本查询接口

```
GET /api/v1/ai/quota/cost/total?from=2025-01-01&to=2025-01-07&provider=openai
```

响应：

```json
{
  "total_tokens": 123456,
  "total_estimated_cost_usd": 12.34,
  "breakdown": [
    {
      "provider": "openai",
      "model": "gpt-4o-mini",
      "capability": "chat",
      "input_tokens": 100000,
      "output_tokens": 23456,
      "estimated_cost_usd": 10.00
    }
  ]
}
```

对应 06-doc §3.3 的 `pim_ai_estimated_cost_total{provider,model,capability}` 指标聚合查询。

---

## 5. 限额接口 Pydantic Schema 草图

### 5.1 调用前预检：QuotaCheckRequest / QuotaCheckResponse

在 Knowledge Gateway 的 Query Planner 之前调用，判断是否可以发起这次 AI 调用。

```python
class QuotaCheckRequest(BaseModel):
    user_id: UUID
    role_code: str                      # "admin" / "sales" / "procurement" / "guest"
    capability: Literal["chat", "embedding", "reranking", "planning"]
    provider: str | None = None         # 调用前可能未知，允许 NULL
    model: str | None = None            # 调用前可能未知，允许 NULL
    estimated_input_tokens: int | None = None  # 预估输入 Token（可为空）
    estimated_output_tokens: int | None = None  # 预估输出 Token（可为空）
    trace_id: str                       # 贯穿全链路的 trace ID

class QuotaCheckResponse(BaseModel):
    allowed: bool
    remaining_count: int | None = None          # 剩余次数（分钟窗口）
    remaining_amount: float | None = None       # 剩余美元额度（日窗口）
    remaining_tokens: int | None = None         # 剩余 Token（日窗口）
    retry_after_seconds: int | None = None      # 建议重试等待秒数
    reason_code: str | None = None              # 拒绝原因码，允许时为空
    reason_message: str | None = None           # 人类可读的拒绝原因
    degraded_capabilities: list[str] = []       # 当前已降级的能力列表
```

### 5.2 调用后回写：QuotaUsageRecord

在模型调用完成后回写用量，用于累计额度和成本估算。

```python
class QuotaUsageRecord(BaseModel):
    trace_id: str
    user_id: UUID
    role_code: str
    provider: str                       # 实际使用的供应商
    model: str                          # 实际使用的模型
    capability: Literal["chat", "embedding", "reranking", "planning"]
    direction: Literal["input", "output"] | None = None  # Token 方向
    tokens: int                         # 本次消耗 Token 数
    estimated_cost_usd: float | None = None  # 本次估算成本（美元）
    latency_ms: int                     # 本次调用延迟（毫秒）
    status: Literal["ok", "error", "timeout", "rate_limited"]
    timestamp: datetime
```

### 5.3 LimitTier 校验返回

```python
class LimitTierResult(BaseModel):
    """单层（系统/角色/用户之一）的限额校验结果。"""
    layer: Literal["system", "role", "user"]
    allowed: bool
    remaining_count: int | None = None          # 频率限制剩余次数
    remaining_tokens: int | None = None         # Token 额度剩余
    remaining_amount: float | None = None       # 美元额度剩余
    retry_after_seconds: int | None = None
    reason_code: str | None = None
```

### 5.4 拒绝原因码常量表

对齐 06-doc §4 错误分类：

```python
class QuotaReasonCode(str, Enum):
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"           # 用户日额度超限
    RATE_LIMITED = "RATE_LIMITED"               # 频率限制（系统/角色/用户）
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"       # 系统日预算耗尽
    CAPABILITY_DISABLED = "CAPABILITY_DISABLED" # 能力已降级关闭
    AUTH_DENIED = "AUTH_DENIED"                 # 无权限使用该能力
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE" # 限流服务不可用（Redis 故障）
    UNKNOWN = "UNKNOWN"                         # 未知原因
```

---

## 6. Redis 存储 Key 设计

### 6.1 频率限制 Key（滑窗计数器）

```text
# 系统级
ai:quota:system:tps:{unix_second}           -> Counter（原子 INCR）
ai:quota:system:concurrent                  -> Gauge（进入 +1，退出 -1）
ai:quota:system:daily_calls:{YYYY-MM-DD}    -> Counter

# 角色级
ai:quota:role:{role_code}:per_min:{minute_window}  -> Counter
ai:quota:role:{role_code}:per_day:{YYYY-MM-DD}     -> Counter
ai:quota:role:{role_code}:concurrent                 -> Gauge

# 用户级
ai:quota:user:{user_id}:per_min:{minute_window}    -> Counter
ai:quota:user:{user_id}:per_day:{YYYY-MM-DD}       -> Counter
ai:quota:user:{user_id}:concurrent                 -> Gauge
```

滑窗计数器使用 Lua 脚本实现原子操作：

```lua
-- KEYS[1]: 当前窗口 key, KEYS[2]: 上一窗口 key
-- ARGV[1]: limit, ARGV[2]: current_timestamp, ARGV[3]: window_size_seconds
local current_window = math.floor(ARGV[2] / ARGV[3])
local prev_window = current_window - 1
local current_count = tonumber(redis.call('GET', KEYS[1]) or "0")
local prev_count = tonumber(redis.call('GET', KEYS[2]) or "0")
local weighted = prev_count * (1 - (ARGV[2] % ARGV[3]) / ARGV[3]) + current_count
if weighted + 1 > tonumber(ARGV[1]) then
    return 0  -- 超限
end
redis.call('INCR', KEYS[1])
redis.call('EXPIRE', KEYS[1], ARGV[3] * 2)
return 1  -- 允许
```

### 6.2 额度限制 Key（按日 reset）

```text
# Token 额度
ai:quota:user:{user_id}:tokens:{YYYY-MM-DD}       -> Counter
ai:quota:system:tokens:{YYYY-MM-DD}               -> Counter

# 美元成本额度
ai:quota:user:{user_id}:cost:{YYYY-MM-DD}         -> Gauge（float 用字符串存储）
ai:quota:system:cost:{YYYY-MM-DD}                 -> Gauge
```

### 6.3 存储原则

- **不存储 Prompt/原文**：对齐 05-doc §7 "不保存问题和回答原文"。
- **所有 key 设置 TTL**：频率限制 key TTL = 窗口大小 × 2；额度 key TTL = 48 小时（保留一天缓冲）。
- **原子操作**：频率限制必须用 Lua 脚本，避免竞态条件。

---

## 7. 配置项清单（补到 .env.example 的提议项）

当前 `.env.example` 无任何 quota 相关配置项，P0 阶段建议补充以下配置（`config.py` 中对应增加字段）：

```ini
# ---- AI 限额与成本治理 ----
# 频率限制
AI_LIMIT_TPS=10                           # 系统全局 QPS 上限
AI_LIMIT_CONCURRENT_STREAMS=40            # 系统全局并发流上限
AI_LIMIT_USER_PER_MIN=20                  # 单用户每分钟最大调用次数
AI_LIMIT_USER_PER_DAY=500                 # 单用户每日最大调用次数
AI_LIMIT_USER_CONCURRENT_STREAMS=3        # 单用户最大并发流

# 额度限制
AI_LIMIT_USER_DAILY_TOKENS=100000         # 单用户日 Token 上限
AI_LIMIT_USER_DAILY_COST_USD=5.0          # 单用户日成本上限（美元）
AI_LIMIT_SYSTEM_DAILY_COST_USD=100.0      # 系统日成本上限（美元）
AI_LIMIT_SYSTEM_DAILY_TOKENS=10000000     # 系统日 Token 上限

# 限额开关与降级
AI_QUOTA_CHECK_ENABLED=false              # false=只记录不拦截（基线测量模式）
AI_BUDGET_NOTIFY_RATIO=0.8                # 预算通知阈值（80%）
AI_BUDGET_DISABLE_RATIO=1.0               # 预算关闭非关键能力阈值（100%）

# 成本估算
AI_ESTIMATED_PRICE_TABLE_PATH=            # 单价表文件路径（CSV/JSON），空表示不加载
```

> 说明：`AI_QUOTA_CHECK_ENABLED=false` 时，QuotaCheck 中间件只记录 `QuotaUsageRecord`，不拦截请求，便于在供应商定档前积累基线用量数据。

---

## 8. 与既有代码的关系

### 8.1 当前状态

- `backend/app/api/v1/ai.py` 的 `_persist_conversation`（121行）已有 SHA-256 摘要审计，但**无限额检查**。
- 当前 `.env.example` 无任何 quota 配置。
- 当前有基础 per-user 限流（`app/core/rate_limiter.py`），但只针对单用户、无系统/角色三级、无 Token/成本维度。

### 8.2 P0 阶段工作

- **只产出本文档和 schema 草图**，不修改任何代码文件。
- 确认 QuotaCheck 中间件在 Phase 1 的 Knowledge Gateway（`backend/app/knowledge/gateway.py`）中实现，作为请求生命周期的第一道关卡（鉴权之后、Query Planner 之前）。

### 8.3 Phase 1 实现要点

1. 在 `backend/app/knowledge/` 下新增 `quota.py` 模块，实现：
   - `QuotaChecker` 类：封装三层频率限制和额度检查逻辑。
   - `QuotaRecorder` 类：异步回写 `QuotaUsageRecord` 到 Redis 和 Prometheus 指标。
   - `get_quota_checker()` 依赖注入函数。
2. 在 `backend/app/knowledge/gateway.py` 的 `handle_query()` 方法开头调用 `QuotaChecker.check()`。
3. 新增 `backend/app/api/v1/ai_quota.py` 路由，提供成本查询和管理员配置接口。
4. 新增 `ai_model_pricing` 数据库表（PostgreSQL），支持管理员 CRUD 单价。

---

## 8.1 可插拔原则（Pluggability）

限额与成本治理接口遵循 ADR-002/ADR-010/ADR-013 既定的可插拔边界，确保模型供应商未定档时系统能运行、定档后能热配置、切换供应商能不重写业务代码：

| 可插拔维度 | 设计约束 | P0 退出标准 |
| --- | --- | --- |
| QuotaChecker 实现可替换 | `QuotaChecker` 定义为 `typing.Protocol`，默认实现 `NoOpQuotaChecker`；其他实现（`RedisQuotaChecker`、`SqlQuotaChecker`）通过 `AI_QUOTA_CHECKER_BACKEND` 注入，不写死在 Gateway 内 | Gateway 仅依赖 Protocol，不 import 具体 Redis 实现 |
| 价格表后端可替换 | 单价表读取抽象为 `PricingProvider`；默认从 `ai_model_pricing` 表读，也可由 `AI_PRICING_BACKEND=csv/json` 改读文件，便于离线评测脚本无库复现 | 价格读取不直接拼 SQL，走 Provider 接口 |
| 供应商未定档状态可运行 | `ai_model_pricing` 表允许 provider/model/capability 三元组 price 为 NULL；`QuotaChecker` 在价格 NULL 时只记次数/Token、不计成本、不阻断（`AI_QUOTA_CHECK_ENABLED=false`）；保障 P0 阶段基线度量可跑 | AI_ADAPTER=none 时脚本不报错 |
| 限流算法可替换 | 频率限制策略抽象为 `RateLimitPolicy`（滑窗/令牌桶/固定窗），具体在 Phase 1 选定；P0 默认滑窗，但接口不暴露具体算法 | `QuotaCheckResponse` 只返回 allowed/remaining/retry_after，不暴露算法 |
| 降级开关可热切换 | 预算分级降级（80% 通知/100% 关闭非关键能力）通过 `AI_BUDGET_NOTIFY_RATIO`/`AI_BUDGET_DISABLE_RATIO` 控制，不重启即可改，关闭后只记不限不阻 | 限流可在运行时整组关闭而不重启应用 |
| 与既有 fail-closed 一致 | `AI_QUOTA_CHECK_ENABLED=true` 但 QuotaChecker 后端不可用时按 fail-closed 拒绝（对齐 05-doc §1）；`false` 时只记录不阻拦，对齐既有 `AI_ADAPTER=none` 行为 | 配置项既有作用域不变 |

实施要点：

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class QuotaChecker(Protocol):
    async def check(self, request: QuotaCheckRequest) -> QuotaCheckResponse: ...
    async def record(self, record: QuotaUsageRecord) -> None: ...

class NoOpQuotaChecker:
    """默认实现，记账不阻拦，AI_QUOTA_CHECK_ENABLED=false 时使用。"""
    async def check(self, request): return QuotaCheckResponse(allowed=True, remaining_count=None, ...)
    async def record(self, record): ...  # 仅写 Redis 计数, 不写价格库
```

切流路径：`AI_QUOTA_CHECK_ENABLED=false` → `NoOpQuotaChecker`（P0/基线度量期）→ `AI_QUOTA_CHECK_ENABLED=true` + `AI_QUOTA_CHECKER_BACKEND=redis` → `RedisQuotaChecker`（Phase 1 上线）→ 切供应商不改业务。

---

## 9. P0 退出条件对照

本设计满足 07-doc §3 退出条件与交付要求如下：

| P0 退出条件 / 交付项 | 本设计覆盖情况 |
|----------------------|----------------|
| §3 退出条件第3条：供应商可用 + Key 不入代码 | 本设计预埋限额接口，供应商未定档时所有价格字段为 NULL 占位，Key 通过环境变量注入（`AI_API_KEY`），不写死代码 |
| §3 交付第5条：确认主 Chat/Embedding 供应商、数据处理条款和预算 | 本设计定义单价表结构和成本查询接口，支持供应商定档后填入价格数据；预算分级降级策略与 06-doc §5 告警对齐 |
| §3 交付第1条：Gateway 基本查询可用 | 本设计定义 QuotaCheck 中间件在 Gateway 中的集成点 |
| §3 交付第3条：检索质量达标 | 本设计不直接影响检索质量，但通过限额保护检索服务不被滥用 |
| §3 交付第4条：权限与敏感字段测试通过 | 本设计通过角色级限额区分 admin/sales/procurement/guest，与 05-doc §3 授权模型配合 |

---

## 附录 A：接口调用时序

```text
用户请求
  → AuthZ（既有 PermissionChecker）
  → QuotaChecker.check(QuotaCheckRequest)
       → 若 allowed=false → 返回 429/403 + reason_code
       → 若 allowed=true → 继续
  → Query Planner
  → Tools + Retrieval
  → Model Gateway（调用外部模型）
  → QuotaRecorder.record(QuotaUsageRecord)  # 异步，不阻塞响应
  → 返回 SSE 响应
```

## 附录 B：Prometheus 指标注册

QuotaChecker 需注册以下指标（对齐 06-doc §3.3）：

```text
pim_ai_rate_limit_total{layer="system|role|user"}    # 限流触发次数
pim_ai_quota_tokens_total{provider,model,direction}  # Token 用量
pim_ai_estimated_cost_total{provider,model,capability}  # 成本估算
pim_ai_budget_remaining{type="system|user"}          # 剩余预算（美元）
pim_ai_capability_degraded{capability}               # 降级能力状态（1=降级）
```

---

*文档版本：P0-draft-v1*
*最后更新：2025-07-25*
*责任人：AI 工程师*
