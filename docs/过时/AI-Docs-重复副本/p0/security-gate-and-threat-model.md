# P0 安全门与威胁模型

> 状态：P0 阶段安全基线文档。本文不实现代码，只定义进入 Phase 1 前必须完成的安全控制、威胁建模、数据分级和验收方式。

## 1. 目标

RiChangPIM AI 的安全目标是：服务端授权优先、最小数据出域、最小工具权限、fail-closed、所有来源和动作可追踪。AI 不能成为绕过 PIM 权限、字段过滤、审计和业务确认流程的第二入口。

P0 阶段必须在写 `Knowledge Gateway`、`portal/`、Worker 或 pending action 之前，先完成安全决策门。模型供应商未定、预算未定不影响安全门建设；所有供应商、额度、权限池和存储策略必须可插拔、配置驱动、默认关闭或最小授权。

## 2. 资产清单

| 资产 | 等级 | 说明 | P0 控制 |
| --- | --- | --- | --- |
| 产品公开规格、说明书 | L1 内部一般 | 可用于产品搜索、知识问答 | 仅授权用户可检索 |
| 草稿产品、质量问题、内部培训资料 | L2 内部受限 | 当前 13 条试点产品均为 draft/pending | 必须标注状态，不进入正式销售承诺 |
| 成本价、供应商、报价、客户名、采购条件 | L3 敏感业务 | 销售级别不可见，最高权限池/采购池按策略可见 | 不默认发送外部模型，字段投影过滤 |
| API Key、JWT、私钥、密码 | L4 密钥/认证 | 永不进入 Prompt、日志、Git、文档 | Secret scan + 轮换记录 |
| AI 审计摘要、trace、工具轨迹 | L2/L3 | 不含原文，但可暴露业务行为 | 仅治理/管理员可查 |

## 3. 信任边界

| 边界 | 不可信输入 | 服务端控制 |
| --- | --- | --- |
| Portal -> Gateway | 用户消息、scope、filters、session_id | JWT、权限池、schema 校验、scope 复核 |
| Gateway -> Tool Registry | 模型规划结果、工具名、参数 | 白名单工具、Pydantic schema、字段投影 |
| Gateway -> Retriever | 用户问题、文档内容、产品描述 | ACL、状态过滤、source 校验 |
| Gateway -> Model Gateway | 上下文包、证据文本 | 最小出域、敏感字段剔除、Token 预算 |
| Worker -> DB/MinIO/OCR | 上传文件、解析结果 | MIME/大小/恶意内容检查、失败不发布 |
| Redis/Quota -> Gateway | 限流状态、预算状态 | 可插拔 QuotaChecker，异常 fail-closed |

## 4. 威胁模型

| 威胁 | 触发条件 | 影响 | 现有控制 | P0 需补控制 | 验收方式 |
| --- | --- | --- | --- | --- | --- |
| Prompt 注入 | 文档或用户输入要求忽略规则、输出密钥、执行 SQL | 模型越权回答或诱导工具滥用 | 当前模型只在后端 Adapter 调用 | 对抗样本进入 `eval/p0/evalset.jsonl`；工具名必须白名单 | 安全集 100% 阻断 |
| 越权查询成本/供应商 | sales/viewer 询问成本价、供应商 | L3 泄露 | 现有 serializer 对部分角色过滤 | 权限池矩阵 + 字段投影 + 工具级 RBAC | 角色矩阵测试全绿 |
| 敏感字段外发 | Gateway 把成本、客户名、报价明细拼进 Prompt | 数据出域 | 当前无 Gateway | L3 默认不进外部模型；必要时模板化后端表达 | Mock 模型断言无敏感字段 |
| 原文对话泄露 | 存储用户问题/回答原文 | 隐私和业务泄露 | `ai.py` 实际写 sha256 摘要 | ConversationStore 接口默认 Digest，不启用 Full | 数据库抽样无原文 |
| 工具滥用 | 模型生成任意 SQL/URL/shell | 数据破坏、外联泄露 | 当前无工具执行框架 | 禁止通用 SQL/Shell/URL 工具；只读先行 | 工具名 fuzz 测试拒绝 |
| 供应商泄露 | Key 写入 Git、日志、构建产物 | 账号滥用、成本损失 | `.env.example` 无真实 Key | Secret scan、Git 历史核验、轮换记录 | 轮换记录签字 |
| 成本失控 | 高并发、大 Token、后台重建失控 | 账单失控、服务降级 | Redis 已部署 | QuotaChecker 可插拔，系统/角色/用户三级限额 | 限额接口设计评审通过 |
| DB/Redis/Worker 争抢 | 索引任务与在线查询共用资源 | 核心 PIM 慢 | 当前 Worker 未实现 | Worker 并发限制、独立连接池预算 | 压测报告进入 Phase 2 |
| OCR 恶意文件 | 超大文件、错误 MIME、文件炸弹 | 资源耗尽或安全风险 | OCR 默认关闭 | 文件大小/MIME/临时目录/失败状态 | 恶意文件样本拒绝 |
| 删除传播失败 | 附件替换/删除后旧块仍召回 | 过期信息误导 | 当前 RAG 无删除传播保障 | 查询时源状态过滤，Outbox 删除任务 | 删除/替换一致性测试 |

## 5. 安全门

| 安全门 | 证据 | 通过标准 |
| --- | --- | --- |
| Secret scan | `p0/credential-rotation-record-template.md` 填写后的记录 | Git 历史、日志、构建产物无有效 Key |
| 权限池矩阵 | `p0/permission-pool-matrix.md` | admin/purchaser/sales/viewer 字段策略明确 |
| 数据分级 | 本文第 2 节 | L1-L4 均有字段映射和外部模型策略 |
| 无原文审计 | `backend/app/api/v1/ai.py:137-154` 核验 | 写入 sha256 摘要，不写问题/回答原文 |
| 对抗评测 | `eval/p0/evalset.jsonl` | 含 prompt 注入、越权、SQL、密钥探测 |
| 可插拔限额 | `p0/quota-limit-interface-design.md` | QuotaChecker/Provider 可替换，默认不写死供应商 |
| CORS/TLS/SSE | Phase 1 配置检查单 | 生产 origin 明确、SSE 禁缓冲、模型/MinIO TLS |

## 6. 可插拔安全原则

安全控制不得写死到某个模型供应商、某个角色名称或某个存储实现。P0 只冻结接口：`PermissionPoolResolver`、`QuotaChecker`、`ConversationStore`、`PricingProvider`、`FieldProjectionStrategy`。Phase 1 允许默认实现为角色驱动、Redis 限额、Digest 存储、PostgreSQL 价格表，但 Gateway 只能依赖抽象接口。

## 7. 进入 Phase 1 条件

- Secret scan 与凭据轮换记录完成，且无有效 Key 泄露。
- 200 条评测集覆盖权限、未知数据、拒答和攻击样本。
- 权限池矩阵、限额接口、数据治理清单通过负责人评审。
- 模型供应商可暂未定档，但 Key 注入方式、价格表占位、额度接口已定义。
- 试点数据足以验证销售选型与知识问答；不足则暂停 Gateway/Portal 功能开发。

## 8. 阻塞条件

- 发现有效 Key 已进入 Git/日志/构建产物且未轮换。
- 无法说明销售、采购、viewer 对成本、库存、供应商、报价字段的可见策略。
- 评测集缺少安全对抗或未知数据样本。
- 试点数据仍只能展示 `99999` 占位价且无“待核价”规则。
- 任何设计要求模型自行隐藏敏感字段，而不是服务端先过滤。
