# 05 - 业务流程（BPM）

> 本文档基于概念方案第四章"核心业务流程设计"，使用 Mermaid 绘制时序图与流程图，覆盖产品归档、AI 推荐、方案分享等核心链路。

---

## 一、产品上传与知识归档流程

### 1.1 流程说明

管理员上传产品结构化数据与 PDF 附件，系统通过 MinerU OCR 自动解析，双写入库（业务库 + 向量知识库），人工校验后一键上架。

### 1.2 流程图

```mermaid
flowchart TD
    A[管理员上传结构化数据 + PDF] --> B[MinerU OCR 自动化解析]
    B --> C{双写入库}
    C --> D[PostgreSQL 写入业务数据]
    C --> E[AI能力中心 提取标签与向量化]
    D --> F[管理员人工校验]
    E --> F
    F --> G{校验通过?}
    G -->|是| H[一键上架发布 status=active]
    G -->|否| I[修改数据]
    I --> B
```

### 1.3 时序图

```mermaid
sequenceDiagram
    participant Admin as 管理员
    participant API as Business API
    participant OCR as MinerU
    participant DB as PostgreSQL
    participant AI as AI能力中心

    Admin->>API: 上传产品数据 + PDF
    API->>OCR: 转发 PDF 解析请求
    OCR-->>API: 返回结构化文本
    API->>DB: 写入业务数据 Product/Attachment
    API->>AI: 提取标签与向量化
    AI->>DB: 写入 pgvector 向量字段
    AI-->>API: 向量化完成
    API-->>Admin: 返回产品 ID（草稿状态）
    Admin->>API: 校验确认 → 上架
    API->>DB: 更新 status = active
    API-->>Admin: 上架成功
```

### 1.4 库存状态并发控制说明

产品 `stock_status` 字段在多人并发修改时，采用乐观锁机制：

```sql
UPDATE product
SET stock_status = $1, version = version + 1
WHERE id = $2 AND version = $3;
```

- `product` 表补充 `version INT NOT NULL DEFAULT 0` 字段（由 Agent-A 在 ERD 中添加，此处仅说明流程）
- 并发更新时，若返回受影响行数为 0，说明版本号不匹配，需重试
- 适用场景：采购/产品经理批量调整库存状态

---

## 二、AI 智能产品推荐流程

### 2.1 流程说明

客户/销售输入模糊需求，AI 理解意图后转化为标准化筛选条件，调用 Business API 执行多维度条件组合查询，结果经 AI 润色后结构化呈现。

> ⚠ 红线：向量召回只提供候选集，价格/库存等强准确性字段必须由 Business API 回查关系型数据库确认。

### 2.2 流程图

```mermaid
flowchart TD
    A[客户/销售输入模糊需求] --> B[AI能力中心 语义理解与意图拆解]
    B --> C[转换为标准结构化检索参数 JSON]
    C --> D[Business API 执行多维度条件组合查询]
    D --> E{数据来源}
    E -->|向量召回| F[pgvector 提供候选集]
    E -->|业务回查| G[PostgreSQL 确认强准确性字段]
    F --> G
    G --> H[AI能力中心 组织润色话术]
    H --> I[结构化呈现推荐结果]
    I --> J[客户/销售 获取 answer + sources + tool_calls]
```

### 2.3 时序图（含回查闭环）

```mermaid
sequenceDiagram
    participant User as 客户/销售
    participant API as Business API
    participant AI as AI能力中心
    participant DB as PostgreSQL

    User->>API: POST /ai/chat 模糊需求
    API->>AI: 转发对话请求
    AI-->>API: 返回标准化筛选参数 tool_calls
    API->>DB: 向量召回候选集 pgvector
    DB-->>API: 返回候选产品 ID 列表
    API->>DB: 回查强准确性字段 price/stock/supplier
    DB-->>API: 返回确认后的真实数据
    API->>AI: 传入真实数据，请求润色
    AI-->>API: 返回 answer + sources
    API-->>User: 结构化推荐结果
```

---

## 三、销售方案生成与对外分享流程

### 3.1 流程说明

销售勾选产品组合，系统自动生成基础方案，AI 执行商务语境润色与推荐理由生成，分享中心一键导出 PDF/生成 H5 与二维码，客户手机扫码查阅。

### 3.2 流程图

```mermaid
flowchart TD
    A[销售勾选产品 A/B/C] --> B[方案中心 一键生成基础方案]
    B --> C[自动拉取多媒体物料]
    C --> D{是否 AI 润色?}
    D -->|是| E[AI能力中心 商务语境润色 + 推荐理由]
    D -->|否| F[保持基础方案]
    E --> F
    F --> G[分享中心 一键导出 PDF/生成 H5]
    G --> H[生成唯一安全 URL + 二维码]
    H --> I[配置访问控制]
    I --> J[写入 ShareToken 表]
    J --> K[客户手机扫码查阅]
    K --> L{权限校验}
    L -->|通过| M[展示方案内容]
    L -->|失败| N[拒绝访问]
    M --> O[记录 ShareLog 访问审计]
```

### 3.3 时序图

```mermaid
sequenceDiagram
    participant Sales as 销售
    participant API as Business API
    participant AI as AI能力中心
    participant Customer as 客户

    Sales->>API: 勾选产品，生成方案
    API->>API: 组装 Proposal + ProposalItem
    API->>API: 拉取多媒体物料
    opt AI 润色
        API->>AI: 请求润色 + 推荐理由
        AI-->>API: 返回润色结果
    end
    API-->>Sales: 方案生成成功
    Sales->>API: 点击分享
    API->>API: 生成 URL + 二维码
    API->>API: 写入 ShareToken 密码/到期/次数
    API-->>Sales: 返回分享链接
    Customer->>API: 扫码访问 token + password
    API->>API: 校验 ShareToken 状态
    API->>API: 记录 ShareLog
    API-->>Customer: 返回 H5 方案内容
```

### 3.4 撤销分享与级联失效流程

#### 流程图

```mermaid
flowchart TD
    A[管理员/销售 撤销分享] --> B[Business API 接收请求]
    B --> C[UPDATE share SET status=disabled]
    C --> D[批量 UPDATE share_token SET status=disabled WHERE share_id]
    D --> E[删除 Redis 中 token 校验缓存]
    E --> F[后续访问被拒绝 记录 denied_expired]
```

#### 时序图

```mermaid
sequenceDiagram
    participant User as 管理员/销售
    participant API as Business API
    participant DB as PostgreSQL
    participant Redis as Redis

    User->>API: DELETE /shares/{id}
    API->>DB: UPDATE share SET status='disabled' WHERE id
    API->>DB: UPDATE share_token SET status='disabled' WHERE share_id
    DB-->>API: 返回受影响行数
    API->>Redis: DEL share_token:{token} (遍历该 share 下所有 token)
    Redis-->>API: 删除成功
    API-->>User: 撤销成功
    Note over API,Redis: 后续访问该 share 下任意 token 均被拒绝
```

---

## 四、用户登录与鉴权流程

```mermaid
sequenceDiagram
    participant User as 用户
    participant API as Business API
    participant Redis as Redis
    participant DB as PostgreSQL

    User->>API: POST /auth/login (username, password)
    API->>DB: 查询 User 表验证
    DB-->>API: 返回用户信息 + role_id
    API->>DB: 查询 RolePermission 获取权限码
    DB-->>API: 返回权限列表
    API->>API: 生成 JWT (含 user_id + role + perms)
    API->>Redis: 缓存用户会话
    API-->>User: 返回 JWT Token

    Note over User,DB: 后续请求携带 Authorization: Bearer <token>
    User->>API: GET /products (带 Token)
    API->>Redis: 验证 Token 有效性
    API->>API: 校验接口权限 + 字段级权限
    API->>DB: 查询产品（响应序列化层过滤敏感字段）
    DB-->>User: 返回过滤后的产品数据
```

---

## 五、报价单生成流程

```mermaid
flowchart TD
    A[销售基于方案生成报价] --> B[报价中心 拉取方案明细]
    B --> C[逐项填入数量/税率/折扣]
    C --> D[动态计算总价]
    D --> E{导出方式?}
    E -->|PDF| F[HTML 模板动态渲染]
    F --> G[Gotenberg 转换高保真 PDF]
    E -->|H5| H[生成在线报价页面]
    G --> I[下载/分享]
    H --> I
```

---

*本文档随业务流程迭代持续更新。当前阶段：概念完善。*

---

## 修订记录

| 日期 | 修订内容 | 修订人 |
| --- | --- | --- |
| 2026-07-12 | 按总经理审查报告 P0/P1/P2 项修订 | Agent-B |
