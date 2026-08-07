# 04 门户交互与 API 契约

> 实施状态：**目标态契约，当前尚未实现。** 当前不存在 `portal/`、`/api/v1/knowledge/*`、统一 SSE 客户端和 `pending_action`；现有管理前端仍调用 `/api/v1/ai/chat` 与 `/api/v1/ai/recommend`。

## 1. 门户定位

AI Portal 是面向全体内部员工的“商品发现、知识查询、业务分析和受控动作入口”，不是后台 CRUD 的换皮，也不是公开聊天机器人。

建议在 `RiChangPIM/portal/` 新建独立 Vue 3 + Vite + TypeScript 工程，与现有 `frontend/` 平级：

- `/` 路由到 Portal；
- `/admin/` 路由到现有管理后台；
- `/share/{token}` 首期继续由现有公开分享页承载；
- `/api/` 统一路由到 FastAPI。

独立工程的理由是前台与后台交互范式、发布节奏和包体边界不同。它们共享后端契约和视觉品牌，不直接跨项目引用 `.vue` 页面组件。稳定后再抽取认证、API 类型和纯工具到 `packages/shared`。

## 2. 信息架构

### 2.1 首页

- 居中品牌与主输入框；
- 场景提示词：找产品、问资料、查质量、做采购比较；
- 有权限的最近方案或常用操作，不展示完整对话历史；
- 推荐产品流必须标明数据状态，不展示待核价占位数值。

### 2.2 全屏对话工作区

- 左侧可选会话导航首期只保留当前临时会话，不承诺历史恢复；
- 中间是对话、证据、产品卡片和比较表；
- 右侧或抽屉显示当前 Scope、来源详情、方案草稿篮；
- 底部固定输入，支持停止生成、重试和清空临时会话。

### 2.3 上下文入口

同一 Gateway 支持：

- 全局入口：默认只查用户可见范围；
- 产品详情入口：携带明确 `product_ids`；
- 产品列表入口：携带当前筛选快照和选中产品；
- 方案入口：携带 `proposal_id`，仍由后端重新检查权限和状态。

前端 Scope 只是用户意图提示，不是安全边界，后端不能信任前端传来的 ID 或过滤器。

## 3. 四类回答组件

### 3.1 产品卡片

字段：封面、产品名、编号、品牌/类目、状态、价格展示状态、库存状态、核心证据标签。操作根据权限显示查看详情、加入草稿篮。

禁止：前端直接展示 API 中可能存在的 `99999` 占位价；禁止以颜色暗示未知库存为有货。

### 3.2 比较表

- 行为属性，列为产品；
- 每个单元格可显示结构化来源或文档来源；
- 缺失值显示“资料未提供”；
- 推导结论单独放在表后，不混入原始属性。

### 3.3 来源卡片

- 数据库事实：字段名、值、数据时点、跳转产品；
- 文档证据：标题、版本、章节、页码、短引用、打开原文；
- 来源不可访问或已失效时，前端不能仅凭缓存继续展示正文。

### 3.4 待确认动作

动作卡必须显示：动作类型、目标、影响、使用的产品、创建内容预览、所需权限和过期时间。用户点击确认后再次调用后端确认接口，不能在前端本地把草稿当作已执行。

## 4. 统一查询 API

### 4.1 请求

```http
POST /api/v1/knowledge/query
Authorization: Bearer <access_token>
Content-Type: application/json
Accept: text/event-stream
Idempotency-Key: <uuid>
```

```json
{
  "message": "帮我比较 A100 和 A200，哪个更适合会议室，并加入方案草稿",
  "session_id": "uuid",
  "scope": {
    "type": "product_list",
    "product_ids": ["uuid-1", "uuid-2"],
    "filters": {"category_id": "uuid"},
    "proposal_id": null
  },
  "capabilities": {
    "stream": true,
    "supports_actions": true
  },
  "client_context": {
    "page": "products",
    "locale": "zh-CN",
    "timezone": "Asia/Shanghai"
  }
}
```

约束：

- `message` 1-4000 字；
- 单次显式产品最多 20 个，比较默认最多 5 个；
- `filters` 仅接受后端白名单字段；
- 客户端不传 role、permission 或敏感级别；
- `session_id` 只提供对话关联，不能跨用户读取。

### 4.2 SSE 协议

统一使用具名事件和版本化数据：

```text
event: meta
data: {"schema_version":"1.0","trace_id":"...","session_id":"..."}

event: phase
data: {"name":"retrieving","label":"正在检索产品资料"}

event: answer_delta
data: {"text":"..."}

event: source
data: {"source_id":"src_1","source_type":"document","title":"...","page":12}

event: products
data: {"items":[...],"reason_source_ids":["src_1"]}

event: pending_action
data: {"action_id":"...","type":"proposal.create_draft","expires_at":"...","preview":{...}}

event: done
data: {"status":"completed","confidence":"high","usage":{...}}

event: error
data: {"code":"MODEL_TIMEOUT","retryable":true,"message":"AI 服务响应超时"}
```

SSE 规则：

- 事件数据都必须是单行 JSON；
- `schema_version` 向后兼容一个 Portal 版本；
- 心跳用注释帧 `: keep-alive`，建议 15 秒；
- 客户端用 `fetch + ReadableStream + AbortController`，因为原生 EventSource 不支持 POST 请求体和标准 Authorization Header；
- 用户停止生成时中止上游模型连接并记录 `cancelled`；
- 断线后首期不自动续写答案，提供显式重试，避免重复动作。

### 4.3 非流式响应

调试和自动化测试可使用 `stream=false`：

```json
{
  "code": 200,
  "data": {
    "trace_id": "...",
    "session_id": "...",
    "answer": "...",
    "facts": [],
    "sources": [],
    "products": [],
    "pending_actions": [],
    "confidence": "medium",
    "insufficient_sources": false,
    "usage": {"model": "...", "input_tokens": 0, "output_tokens": 0}
  },
  "msg": "success"
}
```

## 5. 辅助 API

| API | 用途 | 权限 |
| --- | --- | --- |
| `POST /api/v1/knowledge/search` | 只检索不生成，供调试与管理后台 | `knowledge:debug` |
| `POST /api/v1/knowledge/actions/{id}/confirm` | 确认待执行动作 | 动作对应业务权限 |
| `POST /api/v1/knowledge/actions/{id}/cancel` | 取消动作 | 动作创建人或管理员 |
| `POST /api/v1/knowledge/feedback` | 有用/无用、错误类型、引用反馈 | `ai:access` |
| `GET /api/v1/knowledge/sources/{id}` | 权限复核后返回来源定位 | 来源对应查看权限 |
| `GET /api/v1/knowledge/jobs/{id}` | 索引任务状态 | `knowledge:manage` |
| `POST /api/v1/knowledge/documents/{id}/reindex` | 单文档重建 | `knowledge:manage` |
| `POST /api/v1/knowledge/reindex` | 批量重建 | 管理员 + 二次确认 |

首期不提供对话历史查询 API，但契约预留：

```text
GET    /api/v1/knowledge/sessions
GET    /api/v1/knowledge/sessions/{id}
DELETE /api/v1/knowledge/sessions/{id}
```

这些接口在 `DigestConversationStore` 模式返回功能未启用，而不是伪造空历史。

## 6. 权限拆分

废弃“一个 `ai:use` 决定全部 AI 能力”的长期设计。建议新增：

| 权限 | 说明 |
| --- | --- |
| `ai:access` | 进入 AI Portal 和基础对话 |
| `ai:product` | 产品搜索、比较 |
| `ai:knowledge` | 文档问答 |
| `ai:quality` | 数据治理助手 |
| `ai:procurement` | 采购辅助，仍需供应商/产品权限 |
| `knowledge:manage` | 索引任务和文档治理 |
| `knowledge:debug` | 查看检索分数、工具轨迹等调试信息 |

兼容期内 `ai:use` 可映射到前三项，但在一个发布周期后迁移至细粒度权限。采购工具必须同时满足 `ai:procurement` 与 `supplier:view`；成本字段按既有字段策略继续隐藏。

## 7. 人审动作状态机

```text
proposed -> confirmed -> executing -> succeeded
    |           |            |
    v           v            v
 cancelled    expired       failed
```

- `proposed` 只保存经过字段过滤的结构化动作，不保存完整 Prompt；
- 默认 15 分钟过期；
- 确认时重新鉴权、重新验证业务对象状态，不沿用查询时结论；
- 使用 `action_id + user_id` 作为幂等保护；
- 业务执行调用领域 Service，不通过内部 HTTP 绕过事务；
- 审计同时记录“AI 建议”和“用户确认执行”。

## 8. 兼容与迁移

现有 `/api/v1/ai/chat`、`/recommend`、`/rag/search` 和 `/rag/index` 在迁移期保留：

- 管理后台旧页面可继续使用；
- Portal 不直接依赖这些底层接口；
- Gateway 初期可封装既有 Recommend/RAG 服务，但返回统一协议；
- 当统一检索和工具链达标后，将旧端点标为 internal/deprecated；
- 不采用 Portal 并发 `/chat` + `/recommend` 作为正式方案，因为两次模型调用可能形成互相冲突的文字与产品卡片。

## 9. 可访问性与移动端

- Desktop 1280x800 与 Mobile 393x851 纳入发布门禁；
- 所有流式状态具备屏幕阅读器可理解的状态文本；
- 动画遵循 `prefers-reduced-motion`；
- 键盘可发送、停止、打开来源和确认动作；
- 颜色不是库存、错误和置信度的唯一表达；
- 产品比较在移动端使用横向可滚动表格或逐产品分段，不缩小到不可读。
