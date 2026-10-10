# 10 - 客户 / 项目 / 驾驶舱 / 新媒体 集成设计与实施规范

- **状态：终稿（v3），本需求的唯一执行依据**（2026-10-10 合并定稿）
- **取代**：v1 草案、两份 v2 评审稿、以及 `临时文档夹/10月新需求集成/` 下全部历史版本。凡历史稿与本文冲突，以本文为准。
- **来源**：v1 审计结论 + 长 v2（DDL/矩阵/阶段计划）+ 短 v2（决策登记/V2 修订清单）全部采纳；两稿互斥处按 §1.3 融合裁决执行（业主授权"接纳并进入下一步"）。
- **读者**：业主看 §1/§2/§16/§18；执行 agent 全文，动工顺序 §16；复核 agent 每阶段退出标准。
- **原则（不变）**：只做增量（新表 + 可空列；允许既有响应追加字段，禁止删除/改名/改类型）；`portal/` 不动；无爬取/无模拟登录；不编造数据。

---

## 1. 决策登记簿（全部已定）

### 1.1 沿用 v1 的 A1–A9
| # | 事项 | 结论 |
|---|---|---|
| A1 | 登录落地页 | 不改；菜单顶部加"驾驶舱"，仅 `dashboard:view` 可见；Dashboard 页提供"设为首页"本地偏好（localStorage） |
| A2 | 角色 | 新增 `designer`、`operator`，**并新增 `manager`**（裁决 R2） |
| A3 | 客户对话录入 | 手工粘贴/逐条录入 + 附件（聊天截图/导出文件） |
| A4 | 曝光录入 | 人工录入 + Excel 导入（逐行隔离失败，§10.4） |
| A5 | 提醒渠道 | 站内（铃铛 + 待办抽屉 + 驾驶舱）；预留 `NotificationChannel` 接口，企微/钉钉本期不实现 |
| A6 | 提醒节奏 | 采纳后 2 天 R1；produced 后 2 天 R1b；发布后 T+1/3/7 R2；跟进 next_follow_at 提醒 R3；均环境变量可配 |
| A7 | pending_action | 本期**零改动**（裁决 R5）；仅 Phase 7 的 AI 需求提取使用 |
| A8 | 平台对接 | 不爬取、不模拟登录；`external_ref` 预留 |
| A9 | 版本 | 本需求集 minor 升级，目标 `v1.10.0`（锚点与位置按《版本控制规范和Git.md》§1.1） |

### 1.2 D1–D10（评审稿待决项，定稿）
| # | 事项 | 定稿 |
|---|---|---|
| D1 | ruff 基线 | **B-lite 已执行清零**（§16 Phase 0.5，commit 3e59f76） |
| D2 | `manager` 角色 | **新增**：数据范围全量、无用户/角色/系统管理权；权限=sales 集 ∪ {customer:export, customer:transfer} |
| D3 | PII 应用层加密 | **本期不加密（D3'）**：明文列 + 服务层脱敏 + `phone_norm` 盲索引 + `/pii` 端点审计限速，已满足隐私红线；加密的密钥管理链（备份/轮换/迁移）风险大于收益。依赖 cryptography 已在（python-jose[cryptography]），日后若启用无需加依赖，密钥缺失 fail-closed |
| D4 | sales 可导出客户？ | **否**。`customer:export`/`customer:transfer` 仅 admin/manager |
| D5 | AI 需求提取 | **移 Phase 7，默认关闭**（不开外部模型发送客户数据的口子）；开启前提：输入脱敏 + 逐次人工确认 + 审计 |
| D6 | designer 看客户 | 仅 `customer_brief`（编号+名称），且仅限被绑定项目内；无 `customer:view` |
| D7 | 客户成交联动 | **自动**：客户任一项目首次进入 `producing` → 客户阶段若在 lead…quoted 则自动置 `won`，写 `entity_stage_logs`（operator=系统） |
| D8 | 客户 Excel 批量导入 | 纳入 Phase 2b 末段，**可砍**（归属=导入者；用 phone_norm 查重） |
| D9 | 提醒阈值配置 | 环境变量（改动需重启 backend/worker） |
| D10 | 极限词表 | 内置基础词表 + 可替换文件（`app/services/data/ad_law_words.txt`，运营可更新） |

### 1.3 融合裁决（两稿互斥处；单项可否决）
| # | 冲突 | 裁决 |
|---|---|---|
| R1 | 执行蓝本 | 长 v2 为骨架，短 v2 的 V2-01…V2-31 全部吸收（已体现于正文各节） |
| R2 | manager 增设与否 | **新增**（原始需求红线"经理看全部"+ 提醒升级需要明确对象） |
| R3 | 权限码集合 | 长 v2 ADR-08 基础（去 content:export/reminder:view、加 project:asset）+ 并入 `customer:transfer` = **16 码**（§6.1） |
| R4 | designer/operator 边界 | 取更严方案：designer=project:view+project:asset（无 edit/member/customer:view）；operator=content:*+dashboard:view+reminder:edit（无 customer:/project: 任何码，批次/条目的客户/项目名由服务端按 id 反查仅回名称字段） |
| R5 | pending_action CHECK | 不追加 content.generate；requirement.extract 随原 0022 迁移整体移 Phase 7。**本期该表零改动** |
| R6 | PII 加密 | 见 D3'（不加密）；`phone_hash` 统一改名 `phone_norm` |
| R7 | 内容状态 | item.status 仅 `draft/adopted/rejected/produced/published`（短 V2-15）；tracking/closed 为**派生展示态**，不落状态列（§5.3） |
| R8 | 迁移序列 | 0018/0019/0020(全部权限+三角色)/0021(内容)/0022(提醒)；原"0022_pending_action_types"取消 |

---

## 2. 范围与验收

### 2.1 范围
需求 1–4：① 客户管理 + 项目管理 + 绑定销售/设计 + 图纸；② 销售数据归集（对话/需求/客资/方案/跟进按客户·项目归集）；③ 驾驶舱；④ 新媒体内容工坊与提醒。

**明确不做**（写入验收防蔓延）：多级客户生命周期、财务对账、多级审批流、工单/排产、平台自动发布/自动抓取曝光、客户自助门户、多租户、企微/钉钉推送（仅留接口）、AI 需求提取（Phase 7 默认关闭）。

### 2.2 验收追溯矩阵（AC）
| 需求 | AC | 可验证陈述 | 落点 | 测试 |
|---|---|---|---|---|
| 1 | AC-1.1 | 创建客户并录入来源/等级/阶段/预算/风格偏好；列表按阶段+负责人+关键词筛选 | §4.1 §8.3 | IT-C01、E2E-01 |
| 1 | AC-1.2 | 客户下建多项目；项目绑定 ≥1 销售与 ≥1 设计师；重复绑定 409 | §4.2/4.3 | IT-P02 |
| 1 | AC-1.3 | 项目上传图纸（dwg/dxf/skp/psd/pdf/png），同名自动升版，可 approved/obsolete | §4.8 §12.4 | IT-P03、E2E-03 |
| 1 | AC-1.4 | 销售 A 看不到销售 B 的客户/项目（读+写+附件全部）；设计师只见绑定项目 | §6.4 | UT-S01、IT-S02、E2E-02 |
| 1 | AC-1.5 | 无 pii 权限见 `138****1234`；有权限走 `/pii` 且每次写 OperationLog | §7 | IT-S03、E2E-04 |
| 2 | AC-2.1 | 方案/报价可关联客户/项目；客户详情"方案"页展示全部方案与已确认报价额 | §4.10 §8.3 | IT-Q01 |
| 2 | AC-2.2 | 历史方案零影响；旧端点响应结构零变化 | §13 | CT-01 契约快照 |
| 3 | AC-3.1 | 驾驶舱 5 卡 3 图 p95<2s（千级客户量级）；无数据=空态非 0 占位 | §11 | PT-01、E2E-05 |
| 3 | AC-3.2 | sales 只见本人口径；designer/operator 无金额卡（后端剔除字段） | §6.4 §11.1 | IT-D01 |
| 4 | AC-4.1 | 选产品+主题一次生成 N(≤5) 条；`verified_payload` 与 Business API 回查一致 | §9 | UT-A01、IT-A02 |
| 4 | AC-4.2 | 采纳→+2 天"是否制成视频"待办；发布→T+1/3/7 催录待办；录快照即完成 | §10 | UT-R01、IT-R02 |
| 4 | AC-4.3 | 曝光人工+Excel 导入；逐行隔离失败并返回错误回执 | §10.4 | IT-M03 |
| 4 | AC-4.4 | `AI_ADAPTER=none` 受控 503，零半成品 content_items | §9.4 | IT-A04 |

---

## 3. 硬约束与门禁

1. 每次开工第一条命令：`bash scripts/where-am-i.sh`。数据库不得指向 `localhost:5432/ai_pim`；迁移前 `scripts/backup.sh`。本机栈数据（用户 7/商品 4026）视同重要数据。
2. 只做增量；不改既有测试迁就代码；portal/ 不动。
3. 迁移 revision id ≤ 32 字符；必带 downgrade（仅限开发/测试）；测试库 `upgrade head → downgrade -1 → upgrade head` 三连验证；种子幂等（`WHERE NOT EXISTS`）；新权限同时进 `seed_data.py` 与迁移。
4. AI 不维护价格/库存/供应商/客户隐私；不向外部模型发送任何客户数据（Phase 7 前无此功能）；产品事实经 Business API 回查。
5. PII 默认脱敏；明文只经 `GET /customers/{id}/pii`；敏感模块请求体审计 `[redacted]`；客户/项目数据不进 pgvector/Knowledge Gateway；日志与异常不得含 PII。
6. 数据范围校验覆盖读、写、子资源、导出、附件；越权一律 404（不暴露存在性）。
7. 不编造数据；无数据显示空态/"待录入"；权限不足前端"不展示/不请求"。
8. 前端：导航三处同步（el-menu index / subMenuMap / routeLabels）；`router.push`（base=/admin/）；store 在 `src/stores/`；沿用 design-system.css 令牌；动效带 prefers-reduced-motion；桌面与 ≤600px 自查。
9. 提交：Conventional Commits、一提交一目的、不提交 .env/密钥/dist、不 `--no-verify`、不 force push；走 `feature/` 分支；文档与代码不含口令。
10. 不做：爬取/模拟登录内容平台；ERP/财务/多级审批；Celery/Airflow；合并外部项目代码。

**门禁**：每阶段结束跑 `bash scripts/gate.sh [backend|frontend|all]`（已落地，§16 各阶段退出标准引用），并把结果追加到本文附录 D。门禁构成：backend ruff(exit 0) + tests/unit + （TEST_DATABASE_URL 已设时）contract/integration —— 集成默认只跑**仅依赖 PG 的安全子集**（GATE_IT_TESTS 可覆盖；宿主无 Redis/MinIO 发布端口，文件/媒体类用例在宿主必挂，全量应进 compose 网络内跑）；frontend vue-tsc + vitest + eslint + vite build。**基线既定**：ruff 与 eslint 已于 Phase 0.5 清零（附录 D），此后任何新增错误即失败；集成/e2e 若出现既有失败，功能提交不得新增失败。

## 4. 数据模型（可直接实现的 DDL）

### 4.0 公共约定
- 所有新表继承 `CommonBase`：`id uuid PK（应用侧 uuid4）`、`create_time/update_time timestamptz NOT NULL default now()`、`is_deleted boolean NOT NULL default false`、`deleted_at timestamptz NULL`。**下文 DDL 省略这 5 列**。注：现有主键即 uuid4（非 v7，ADR-01 不动）；无 tenant_id（ADR-02）。
- 新表另加 `created_by uuid NULL REFERENCES "user"(id)`、`updated_by uuid NULL REFERENCES "user"(id)`。
- 唯一约束一律 **partial unique `WHERE is_deleted = false`**（对齐 pending_action 既有写法）。
- 外键一律 `ON DELETE RESTRICT`（系统软删，不允许物理级联；例外：可空溯源列用 SET NULL 并标注）。
- 枚举 = `varchar + CHECK`（不用 PG ENUM）。时间一律 `timestamptz` 存 UTC，展示层转北京时间（`utils/beijingTime.ts`）。
- 索引命名 `ix_<t>_<cols>` / `uq_<t>_<cols>` / `ck_<t>_<col>`。

### 4.1 customers
```sql
CREATE TABLE customers (
  name             varchar(128) NOT NULL,
  customer_no      varchar(32)  NULL,              -- C+年+序号，服务层生成，沟通/导入匹配用
  source           varchar(32)  NOT NULL DEFAULT 'other',
  level            varchar(16)  NULL,
  stage            varchar(20)  NOT NULL DEFAULT 'lead',
  owner_sales_id   uuid         NOT NULL REFERENCES "user"(id) ON DELETE RESTRICT,
  phone            varchar(64)  NULL,              -- PII（D3'：明文列，序列化脱敏）
  phone_norm       varchar(32)  NULL,              -- 仅数字；服务层生成；查重/检索用；不出现在任何响应
  wechat           varchar(128) NULL,              -- PII
  address          text         NULL,              -- PII
  budget_min       numeric(12,2) NULL,
  budget_max       numeric(12,2) NULL,
  style_preference text          NULL,
  remark           text          NULL,
  last_activity_at timestamptz  NULL,              -- 冗余列：dialogue/follow_up/project/阶段变更同事务维护（服务层单点函数 touch_customer_activity）
  CONSTRAINT ck_customers_stage  CHECK (stage IN ('lead','contacted','needs','quoted','won','lost')),
  CONSTRAINT ck_customers_level  CHECK (level IS NULL OR level IN ('A','B','C')),
  CONSTRAINT ck_customers_source CHECK (source IN ('new_media','store','referral','exhibition','other')),
  CONSTRAINT ck_customers_budget CHECK (budget_min IS NULL OR budget_max IS NULL OR budget_min <= budget_max)
);
CREATE INDEX ix_customers_owner_stage ON customers(owner_sales_id, stage) WHERE is_deleted = false;
CREATE INDEX ix_customers_create_time ON customers(create_time DESC)      WHERE is_deleted = false;
CREATE INDEX ix_customers_phone_norm  ON customers(phone_norm)            WHERE is_deleted = false AND phone_norm IS NOT NULL;
CREATE INDEX ix_customers_activity    ON customers(last_activity_at)      WHERE is_deleted = false;
CREATE UNIQUE INDEX uq_customers_no   ON customers(customer_no)           WHERE is_deleted = false AND customer_no IS NOT NULL;
-- 名称模糊检索：若 pg_trgm 可用则 gin(name gin_trgm_ops)，否则降级 btree ix_customers_name(name)（本地实测：available 未安装，迁移带 IF 分支）
```
> 查重：POST 时 phone_norm 命中 → `409 {code:40901, data:{candidates:[…]}}`；`?force=true` 放行（写 OperationLog）。不设 DB 唯一约束（一户多人合法）。

### 4.2 projects
```sql
CREATE TABLE projects (
  customer_id   uuid NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
  code          varchar(32)  NULL,                 -- 项目编号（可选）
  name          varchar(255) NOT NULL,
  project_type  varchar(32)  NOT NULL DEFAULT 'other',
  stage         varchar(20)  NOT NULL DEFAULT 'lead',
  status        varchar(20)  NOT NULL DEFAULT 'active',
  budget        numeric(12,2) NULL,
  start_date    date NULL,
  end_date      date NULL,
  last_activity_at timestamptz NULL,
  CONSTRAINT ck_projects_stage  CHECK (stage IN ('lead','measuring','design','quoted','producing','delivered','closed','cancelled')),
  CONSTRAINT ck_projects_status CHECK (status IN ('active','paused','done','cancelled')),
  CONSTRAINT ck_projects_dates  CHECK (start_date IS NULL OR end_date IS NULL OR start_date <= end_date)
);
CREATE INDEX ix_projects_customer ON projects(customer_id)      WHERE is_deleted = false;
CREATE INDEX ix_projects_stage    ON projects(stage, status)    WHERE is_deleted = false;
CREATE INDEX ix_projects_activity ON projects(last_activity_at) WHERE is_deleted = false;
CREATE UNIQUE INDEX uq_projects_code ON projects(code)          WHERE is_deleted = false AND code IS NOT NULL;
```
> `cancelled` 同时是 stage 终态与 status 值，取消操作两者同写（服务层保证一致）。stage=delivered/closed 自动 status=done。

### 4.3 project_members
```sql
CREATE TABLE project_members (
  project_id  uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
  user_id     uuid NOT NULL REFERENCES "user"(id)   ON DELETE RESTRICT,
  member_role varchar(20) NOT NULL,
  is_primary  boolean NOT NULL DEFAULT false,
  CONSTRAINT ck_pm_role CHECK (member_role IN ('sales','designer','pm','other'))
);
CREATE UNIQUE INDEX uq_pm_project_user_role ON project_members(project_id, user_id, member_role) WHERE is_deleted = false;
CREATE UNIQUE INDEX uq_pm_primary           ON project_members(project_id, member_role)          WHERE is_deleted = false AND is_primary = true;
CREATE INDEX ix_pm_user                     ON project_members(user_id)                          WHERE is_deleted = false;  -- designer 数据范围子查询必需
```

### 4.4 customer_dialogues（+ 附件 junction）
```sql
CREATE TABLE customer_dialogues (
  customer_id uuid NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
  project_id  uuid NULL REFERENCES projects(id)      ON DELETE RESTRICT,
  channel     varchar(32) NOT NULL DEFAULT 'wechat',
  direction   varchar(8)  NOT NULL DEFAULT 'in',
  content     text        NOT NULL,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_dlg_channel   CHECK (channel IN ('wechat','phone','visit','sms','other')),
  CONSTRAINT ck_dlg_direction CHECK (direction IN ('in','out')),
  CONSTRAINT ck_dlg_len       CHECK (char_length(content) <= 20000)
);
CREATE INDEX ix_dlg_customer_time ON customer_dialogues(customer_id, occurred_at DESC) WHERE is_deleted = false;

-- 取代 v1 的 attachment_ids JSONB（V-04 实测 Attachment 无通用挂接位）
CREATE TABLE customer_dialogue_attachments (
  dialogue_id   uuid NOT NULL REFERENCES customer_dialogues(id) ON DELETE RESTRICT,
  attachment_id uuid NOT NULL REFERENCES attachment(id)         ON DELETE RESTRICT,
  sort_no       int  NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX uq_dlg_att ON customer_dialogue_attachments(dialogue_id, attachment_id) WHERE is_deleted = false;
```

### 4.5 requirements
```sql
CREATE TABLE requirements (
  customer_id uuid NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
  project_id  uuid NULL REFERENCES projects(id)      ON DELETE RESTRICT,
  content     text NOT NULL,
  structured  jsonb NULL,
  source      varchar(16) NOT NULL DEFAULT 'manual',
  confirmed   boolean NOT NULL DEFAULT true,
  source_action_id uuid NULL REFERENCES pending_action(id) ON DELETE SET NULL,  -- Phase 7 溯源用，本期恒 NULL
  CONSTRAINT ck_req_source CHECK (source IN ('manual','ai_extracted'))
);
CREATE INDEX ix_req_customer ON requirements(customer_id, create_time DESC) WHERE is_deleted = false;
```
`structured` 由服务层 pydantic 校验（space/items/budget_hint/deadline_hint/raw_span），不入库约束。本期所有需求 source='manual'、confirmed=true。

### 4.6 follow_ups
```sql
CREATE TABLE follow_ups (
  customer_id    uuid NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
  project_id     uuid NULL REFERENCES projects(id)      ON DELETE RESTRICT,
  follower_id    uuid NOT NULL REFERENCES "user"(id)    ON DELETE RESTRICT,
  method         varchar(32) NOT NULL DEFAULT 'wechat',
  content        text NOT NULL,
  result         varchar(32) NULL,
  next_follow_at timestamptz NULL,
  done_at        timestamptz NULL,   -- "该条的下次跟进已兑现"（新建后续跟进 / 手动完成 / 客户 won|lost）
  CONSTRAINT ck_fu_result CHECK (result IS NULL OR result IN ('connected','no_answer','interested','rejected','scheduled','other'))
);
CREATE INDEX ix_fu_customer_time ON follow_ups(customer_id, create_time DESC) WHERE is_deleted = false;
CREATE INDEX ix_fu_follower_time ON follow_ups(follower_id, create_time DESC) WHERE is_deleted = false;
CREATE INDEX ix_fu_next_pending  ON follow_ups(next_follow_at) WHERE is_deleted = false AND done_at IS NULL AND next_follow_at IS NOT NULL;
```

### 4.7 project_assets（图纸/设计稿版本）
```sql
CREATE TABLE project_assets (
  project_id    uuid NOT NULL REFERENCES projects(id)  ON DELETE RESTRICT,
  category      varchar(20) NOT NULL DEFAULT 'other',
  name          varchar(255) NOT NULL,
  version       int NOT NULL DEFAULT 1,
  is_current    boolean NOT NULL DEFAULT true,
  status        varchar(20) NOT NULL DEFAULT 'draft',
  attachment_id uuid NOT NULL REFERENCES attachment(id) ON DELETE RESTRICT,
  remark        text NULL,
  CONSTRAINT ck_pa_category CHECK (category IN ('design_drawing','drawing','render','contract','photo','other')),
  CONSTRAINT ck_pa_status   CHECK (status IN ('draft','shared','approved','obsolete')),
  CONSTRAINT ck_pa_version  CHECK (version >= 1)
);
CREATE UNIQUE INDEX uq_pa_pcnv    ON project_assets(project_id, category, name, version) WHERE is_deleted = false;
CREATE UNIQUE INDEX uq_pa_current ON project_assets(project_id, category, name)          WHERE is_deleted = false AND is_current = true;
CREATE INDEX ix_pa_project        ON project_assets(project_id)                           WHERE is_deleted = false;
```
**升版规则**（服务层）：同 `(project, category, name)` 再上传 → version=max+1，旧行 `is_current=false`；旧行 status=approved 保留，否则置 obsolete。

### 4.8 attachment 受控增量（V2-01 附件越权修复）
```sql
ALTER TABLE attachment ADD COLUMN biz_domain   varchar(32) NULL;  -- 'product'|'customer'|'project'|'content'|NULL(历史)
ALTER TABLE attachment ADD COLUMN biz_scope_id uuid        NULL;  -- 归属对象 id（客户/项目/批次）
CREATE INDEX ix_attachment_biz ON attachment(biz_domain, biz_scope_id) WHERE biz_domain IS NOT NULL;
```
- 新增叶子模块 `backend/app/core/attachment_access.py`（不 import app.main/database）：`can_access_attachment(user, att) -> bool`。规则：biz_domain IS NULL 或 'product' → 现行文件中心/媒体库行为**零变化**；'content' → content:view 即可；'customer'/'project' → 必须过该客户/项目的数据范围 + 对应 view 权限。
- `files.py` 的 download/preview/content 与缩略图路径全部先过 `can_access_attachment`；媒体库列表查询追加 `biz_domain IS NULL OR biz_domain IN ('product','content')`。客户/项目附件只经各自范围内的嵌套端点暴露。
- 上传时由调用端点写入 biz_domain/biz_scope_id（files 通用上传默认 product 语义不变；项目图纸/对话附件经 CRM 端点挂接时回填）。

### 4.9 entity_stage_logs（状态留痕，V2-10/P0-2）
```sql
CREATE TABLE entity_stage_logs (
  entity_type varchar(24) NOT NULL,   -- customer | project | content_item
  entity_id   uuid        NOT NULL,
  field       varchar(24) NOT NULL DEFAULT 'stage',   -- stage | status
  from_value  varchar(32) NULL,
  to_value    varchar(32) NOT NULL,
  reason      varchar(255) NULL,
  operator_id uuid NULL REFERENCES "user"(id) ON DELETE SET NULL,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_esl_entity CHECK (entity_type IN ('customer','project','content_item'))
);
CREATE INDEX ix_esl_entity ON entity_stage_logs(entity_type, entity_id, occurred_at DESC);
```
不加多态 FK，服务层保证；**写入与状态变更同事务**。本期只存不算（转化率/停留时长后续基于此表）。

### 4.10 既有表增量（仅可空列）
```sql
ALTER TABLE proposal ADD COLUMN project_id  uuid NULL REFERENCES projects(id)  ON DELETE SET NULL;
ALTER TABLE proposal ADD COLUMN customer_id uuid NULL REFERENCES customers(id) ON DELETE SET NULL;
CREATE INDEX ix_proposal_customer ON proposal(customer_id) WHERE customer_id IS NOT NULL;
CREATE INDEX ix_proposal_project  ON proposal(project_id)  WHERE project_id  IS NOT NULL;
```
**不回填历史**；旧 API 响应不新增字段（CT-01 契约快照守护）。新字段只经新增的 `/customers/{id}/proposals`、`/projects/{id}/proposals` 暴露。

### 4.11 content_batches / content_items
```sql
CREATE TABLE content_batches (
  title           varchar(255) NOT NULL,
  customer_id     uuid NULL REFERENCES customers(id) ON DELETE SET NULL,
  project_id      uuid NULL REFERENCES projects(id)  ON DELETE SET NULL,
  product_ids     jsonb NOT NULL DEFAULT '[]'::jsonb,
  topic           text NOT NULL,
  platform        varchar(32) NOT NULL,
  tone            varchar(32) NULL,                 -- 种草/测评/干货/故事
  requested_count int NOT NULL DEFAULT 3,
  status          varchar(16) NOT NULL DEFAULT 'running',
  error_msg       text NULL,
  model_provider  varchar(32) NULL,
  model_name      varchar(64) NULL,
  prompt_version  varchar(16) NOT NULL DEFAULT 'v1',
  latency_ms      int NULL,
  CONSTRAINT ck_cb_platform CHECK (platform IN ('xhs','douyin','moments','seo','other')),
  CONSTRAINT ck_cb_status   CHECK (status IN ('pending','running','done','failed')),
  CONSTRAINT ck_cb_count    CHECK (requested_count BETWEEN 1 AND 5)
);
CREATE INDEX ix_cb_created ON content_batches(create_time DESC) WHERE is_deleted = false;

CREATE TABLE content_items (
  batch_id   uuid NOT NULL REFERENCES content_batches(id) ON DELETE RESTRICT,
  item_type  varchar(16) NOT NULL DEFAULT 'copy',
  platform   varchar(32) NOT NULL,
  title      varchar(255) NULL,
  body       text NOT NULL,
  hashtags   jsonb NOT NULL DEFAULT '[]'::jsonb,
  status     varchar(16) NOT NULL DEFAULT 'draft',
  adopted_by uuid NULL REFERENCES "user"(id) ON DELETE SET NULL,
  adopted_at timestamptz NULL,
  rejected_reason varchar(255) NULL,
  produced_at  timestamptz NULL,
  published_at timestamptz NULL,
  closed_at    timestamptz NULL,        -- 派生 close 条件首次满足时由服务写一次（展示缓存，非状态）
  edited       boolean NOT NULL DEFAULT false,   -- 人工改过正文（评估 AI 可用率）
  verified_payload jsonb NULL,
  warnings         jsonb NOT NULL DEFAULT '[]'::jsonb,  -- 合规/事实守卫命中项（§9.3）
  external_ref     varchar(128) NULL,
  model_provider   varchar(32) NULL,
  model_name       varchar(64) NULL,
  generation_version varchar(16) NOT NULL DEFAULT 'v1',
  CONSTRAINT ck_ci_type   CHECK (item_type IN ('copy','video_script')),
  CONSTRAINT ck_ci_status CHECK (status IN ('draft','adopted','rejected','produced','published')),  -- 裁决 R7：无 tracking/closed
  CONSTRAINT ck_ci_len    CHECK (char_length(body) <= 20000)
);
CREATE INDEX ix_ci_batch  ON content_items(batch_id)                WHERE is_deleted = false;
CREATE INDEX ix_ci_status ON content_items(status, create_time DESC) WHERE is_deleted = false;
```

### 4.12 content_publications / content_metric_snapshots
```sql
CREATE TABLE content_publications (
  content_item_id     uuid NOT NULL REFERENCES content_items(id) ON DELETE RESTRICT,
  platform            varchar(32) NOT NULL,
  account_name        varchar(128) NULL,
  publish_url         varchar(1024) NOT NULL,
  published_at        timestamptz NOT NULL,
  video_attachment_id uuid NULL REFERENCES attachment(id) ON DELETE SET NULL,
  external_ref        varchar(128) NULL
);
CREATE UNIQUE INDEX uq_pub_item_url ON content_publications(content_item_id, publish_url) WHERE is_deleted = false;
CREATE INDEX ix_pub_published      ON content_publications(published_at DESC)             WHERE is_deleted = false;

CREATE TABLE content_metric_snapshots (
  publication_id uuid NOT NULL REFERENCES content_publications(id) ON DELETE RESTRICT,
  views int NULL, likes int NULL, comments int NULL, shares int NULL, favorites int NULL, leads int NULL,
  captured_at   timestamptz NOT NULL DEFAULT now(),
  captured_date date NOT NULL,             -- 服务层按 Asia/Shanghai 取日期
  source        varchar(8) NOT NULL DEFAULT 'manual',
  CONSTRAINT ck_cms_source CHECK (source IN ('manual','import')),
  CONSTRAINT ck_cms_nonneg CHECK (coalesce(views,0)>=0 AND coalesce(likes,0)>=0 AND coalesce(comments,0)>=0
                                  AND coalesce(shares,0)>=0 AND coalesce(favorites,0)>=0 AND coalesce(leads,0)>=0)
);
CREATE UNIQUE INDEX uq_cms_pub_date ON content_metric_snapshots(publication_id, captured_date) WHERE is_deleted = false;
CREATE INDEX ix_cms_pub_time        ON content_metric_snapshots(publication_id, captured_at DESC) WHERE is_deleted = false;
```
> 快照为**累计值**；同日重复录入按 uq_cms_pub_date **upsert**（回执标 updated，V2-08/P1-5 双计修复）。驾驶舱"累计曝光"= 每条发布**最新**快照之和：
> `SELECT DISTINCT ON (publication_id) * FROM content_metric_snapshots WHERE is_deleted=false ORDER BY publication_id, captured_at DESC`

### 4.13 reminders / notifications（Phase 5）
```sql
CREATE TABLE reminders (
  rule_code     varchar(32) NOT NULL,
  target_type   varchar(24) NOT NULL,     -- content_item | publication | follow_up
  target_id     uuid NOT NULL,
  assignee_id   uuid NOT NULL REFERENCES "user"(id) ON DELETE RESTRICT,
  title         varchar(255) NOT NULL,
  body          text NULL,
  due_at        timestamptz NOT NULL,
  status        varchar(16) NOT NULL DEFAULT 'pending',
  dedupe_key    varchar(160) NOT NULL,
  snoozed_until timestamptz NULL,
  fired_at      timestamptz NULL,
  done_at       timestamptz NULL,
  attempts      int NOT NULL DEFAULT 0,
  escalated     boolean NOT NULL DEFAULT false,
  payload       jsonb NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT ck_rm_status CHECK (status IN ('pending','sent','done','snoozed','cancelled','overdue'))
);
CREATE UNIQUE INDEX uq_rm_dedupe ON reminders(dedupe_key) WHERE is_deleted = false;
CREATE INDEX ix_rm_due   ON reminders(due_at)                           WHERE is_deleted = false AND status IN ('pending','snoozed');
CREATE INDEX ix_rm_inbox ON reminders(assignee_id, status, due_at)      WHERE is_deleted = false;

CREATE TABLE notifications (
  user_id uuid NOT NULL REFERENCES "user"(id) ON DELETE RESTRICT,
  title   varchar(255) NOT NULL,
  body    text NULL,
  kind    varchar(16) NOT NULL DEFAULT 'reminder',
  link    varchar(512) NULL,
  reminder_id uuid NULL REFERENCES reminders(id) ON DELETE SET NULL,
  read_at timestamptz NULL,
  CONSTRAINT ck_nt_kind CHECK (kind IN ('reminder','escalation','system'))
);
CREATE INDEX ix_nt_inbox ON notifications(user_id, read_at, create_time DESC) WHERE is_deleted = false;
```

### 4.14 软删除语义（P1-13）
| 操作 | 规则 |
|---|---|
| 删除客户 | 存在未删 project/dialogue/follow_up/requirement → `409 {code:40902}`；`?cascade=true`（仅 admin/manager）级联软删全部子记录并写 OperationLog（记录级联数量） |
| 删除项目 | 同上（子资源：members/assets 级联软删；dialogues/follow_ups/requirements 的 project_id 置空而非删除） |
| 删除 content_item | 已 published → `409`；只能等派生 closed；draft/adopted/produced 可删 |
| 恢复 | 本期不提供 UI；DBA 手工 is_deleted=false（运维手册） |
| 查询 | 所有 Repository 查询默认 `is_deleted=false`，基类统一处理 |

## 5. 状态机（完整迁移矩阵）

### 5.1 客户漏斗 `customers.stage`
`lead → contacted → needs → quoted → won`（won 终态不可逆，防业绩口径被改）；`→ lost`；`lost → contacted`（reopen，必须 reason）。

| from \ to | lead | contacted | needs | quoted | won | lost |
|---|---|---|---|---|---|---|
| lead | – | ✅ | ✅ | ✅ | ❌ | ✅ |
| contacted | ↩* | – | ✅ | ✅ | ❌ | ✅ |
| needs | ↩* | ↩* | – | ✅ | ✅ | ✅ |
| quoted | ↩* | ↩* | ↩* | – | ✅ | ✅ |
| won | ❌ | ❌ | ❌ | ❌ | – | ❌ |
| lost | ❌ | ✅(reopen) | ❌ | ❌ | ❌ | – |

`↩*`=允许回退，**必须带 reason**（否则 400 {code:40011}），并写 entity_stage_logs。非法迁移 → `400 {code:40010}`。D7 自动 won 也走同一校验与留痕（operator=系统）。

### 5.2 项目阶段 `projects.stage`
`lead → measuring → design → quoted → producing → delivered → closed`；允许跳跃前进；允许**回退一格**（带 reason）；closed/cancelled 不可迁出（admin 可强制，记日志）。任意非终态 → cancelled（带 reason，同时 status=cancelled）。delivered/closed 自动 status=done。全部迁移写 entity_stage_logs。

### 5.3 内容条目（状态 + 派生展示态）
持久状态迁移矩阵（实现在 `services/content_state.py`，**纯函数 + 字典表**，tests/unit 可直接导入）：

| from | to | 端点 | 权限 | 前置守卫 | 副作用（同事务） |
|---|---|---|---|---|---|
| draft | adopted | POST /items/{id}/adopt | content:adopt | warnings 非空时需 `?confirm=true` 二次确认 | stage log；创建 R1 |
| draft | rejected | POST /items/{id}/reject | content:adopt | reason 必填 | stage log（终态） |
| adopted | produced | POST /items/{id}/produce | content:adopt | — | stage log；关闭 R1；创建 R1b |
| adopted/produced | published | POST /items/{id}/publish | content:publish | 同事务创建 publication（可直接图文发布，无需视频环节） | stage log；关闭 R1b；创建 R2×3 |
| published | （终态） | — | — | 补录快照/追加发布允许，不改状态 | item.published 后编辑锁 body（title/hashtags 可改） |
| rejected | （终态） | POST /items/{id}/duplicate | content:generate | 复制为新 draft | 不改原记录 |

**派生展示态**（不落状态列，服务层纯函数 `derive_display_state(item, publications, snapshots, reminders)`）：
- `tracking`：published 且其任一 publication 已有快照；
- `closed`：published 且（全部 publication 的 T+7 提醒 done **或** 最晚 published_at ≥ 14 天）。首次判定时写一次 `closed_at` 缓存。
closed 后补录快照只加数据不改判定。

---

## 6. 权限、数据范围与 PII

### 6.1 权限码（16 个，全量新建）
```
customer:view  customer:edit  customer:pii  customer:export  customer:transfer
project:view   project:edit   project:member project:asset
dashboard:view
content:view   content:generate  content:adopt  content:publish  content:metric
reminder:edit
```
> follow_ups/dialogues/requirements 随 `customer:edit` 归并；成员管理随 `project:member`；导出/移交独立设码（D4）。**相对两份 v2 稿的净变化**：+customer:transfer（V2-17）；总数 16（长稿自称 16 实列 15 的自洽问题就此修复）。

### 6.2 角色 × 权限矩阵（迁移 0020 + seed_data.py 双写，必须一致）
| 权限码 | admin | manager | sales | designer | operator | purchaser | viewer |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| customer:view | ✅ | ✅ | ✅ | ❌(brief) | ❌ | – | – |
| customer:edit | ✅ | ✅ | ✅ | ❌ | ❌ | – | – |
| customer:pii | ✅ | ✅ | ✅ | ❌ | ❌ | – | – |
| customer:export | ✅ | ✅ | ❌(D4) | ❌ | ❌ | – | – |
| customer:transfer | ✅ | ✅ | ❌ | ❌ | ❌ | – | – |
| project:view | ✅ | ✅ | ✅ | ✅(绑定内) | ❌ | – | – |
| project:edit | ✅ | ✅ | ✅ | ❌ | ❌ | – | – |
| project:member | ✅ | ✅ | ✅ | ❌ | ❌ | – | – |
| project:asset | ✅ | ✅ | ✅ | ✅(绑定内) | ❌ | – | – |
| dashboard:view | ✅ | ✅ | ✅ | ✅ | ✅ | – | – |
| content:view | ✅ | ✅ | ✅ | ❌ | ✅ | – | – |
| content:generate | ✅ | ✅ | ❌ | ❌ | ✅ | – | – |
| content:adopt | ✅ | ✅ | ❌ | ❌ | ✅ | – | – |
| content:publish | ✅ | ✅ | ❌ | ❌ | ✅ | – | – |
| content:metric | ✅ | ✅ | ❌ | ❌ | ✅ | – | – |
| reminder:edit | ✅ | ✅ | ✅ | ✅ | ✅ | – | – |

- admin 在 PermissionChecker 直通，但**种子写全**便于收紧。manager=数据范围全量、无 user/role/系统码；升级对象=全体 manager（无则 admin，V2-13）。
- designer：无 customer:view，项目详情返回 `customer_brief={customer_no, name}`；`manager` 的 sales 数据范围旁路见 §6.4。
- operator：无任何 customer:/project: 码；批次/条目上的 customer_id/project_id 保留，**展示名由服务端按 id 反查仅回名称字段**（不落 PII、不经权限）。
- sales 持 `customer:pii`（V2-02：能看到自己客户的号码才能工作）；每次明文查看写审计。

### 6.3 权限码同步检查单（六处，漏一处即 403/菜单消失）
1. `backend/app/scripts/seed_data.py`：PERMISSIONS（65→81）+ ROLES（4→7：+manager/designer/operator）+ ROLE_PERMISSIONS；同时**补录 scene_image:\* 4 码**（G0-4.8 漂移修复）
2. 迁移 `0020_crm_perms` 幂等种子（`INSERT … WHERE NOT EXISTS`，对齐 0011 写法）
3. `frontend/src/types/permissions.ts`：PERMISSIONS 数组（仅 UI 门控子集）+ RESOURCE_PERMISSIONS 映射
4. `frontend/src/router.ts` 各路由 `meta.permission`
5. `backend/tests/test_permission_contract.py`：确认新路由被静态自省扫到
6. **新增** `backend/tests/test_permission_seed_sync.py`：断言「迁移种子并集 == seed_data.PERMISSIONS == 路由自省码 ∪ 纯前端门控码」

**生效时机**：perms 在登录时装进 JWT，存量 token 不含新码 → **发版流程固化"强制全员重登"**（发版说明+系统公告；Phase 6 checklist 一项）。JWT perm_ver 方案记 §18 R-12，本期不做。

### 6.4 数据范围
**读路径**：`backend/app/core/data_scope.py`（叶子模块：只 import sqlalchemy + models，满足 tests/unit 硬约定）
```python
def apply_data_scope(query, *, user_id, role_code, model):
    if role_code in ("admin", "manager"):
        return query                       # 全量
    if model is Customer:
        if role_code == "sales":
            return query.where(Customer.owner_sales_id == user_id)
        return query.where(sa.false())     # designer/operator：无 customer:view，路由层已挡；防御性空集
    if model is Project:
        if role_code == "sales":
            own = select(Customer.id).where(Customer.owner_sales_id == user_id)
            mem = select(ProjectMember.project_id).where(ProjectMember.user_id == user_id, ...)
            return query.where(or_(Project.customer_id.in_(own), Project.id.in_(mem)))
        if role_code == "designer":
            return query.where(Project.id.in_(select(ProjectMember.project_id).where(...)))
        return query.where(sa.false())
    if model in (CustomerDialogue, Requirement, FollowUp):
        return query.where(model.customer_id.in_(_visible_customer_ids(user_id, role_code)))
    if model in (ProjectAsset, ProjectMember):
        return query.where(model.project_id.in_(_visible_project_ids(user_id, role_code)))
    if model in (ContentBatch, ContentItem, ContentPublication, ContentMetricSnapshot):
        return query                       # content 系全量（权限码已限 operator/manager/admin，sales 仅 content:view 读）
    if model in (Reminder, Notification):
        return query.where(model.assignee_id == user_id) if hasattr(model, "assignee_id") else query.where(model.user_id == user_id)
    raise ScopeNotDefined(model)           # 关键：未定义 model 抛异常，禁止默认放行
```
**写路径（P0-3）**：`assert_object_scope(obj, *, user_id, role_code, action)` 在所有 PUT/DELETE/POST 子资源取到对象后、改动前调用；越权与不存在统一 `404 {code:40401}`（V2-05，不暴露存在性）。规则表纯数据可单测：
```python
WRITE_SCOPE = {
  ("sales", Customer):      lambda o, uid: o.owner_sales_id == uid,
  ("sales", Project):       lambda o, uid: o.owner_sales_id_owner == uid or _is_member(o, uid),  # 经 customer
  ("sales", ProjectAsset):  lambda o, uid: _can_edit_project(o.project, uid),
  ("designer", ProjectAsset): lambda o, uid: _is_member(o.project, uid),
  ("sales|designer", FollowUp): lambda o, uid: _can_view_customer(o.customer, uid),
  ("operator", ContentItem): lambda o, uid: True,
}
```
子资源一律**嵌套路由**（`/customers/{id}/…`、`/projects/{id}/…`），父对象范围校验是路径的一部分。
**所有权转移**：`owner_sales_id` 变更需 `customer:transfer`（admin/manager）；sales 不能甩客户/抢客户。转移同事务：重指派该客户 pending/sent 跟进提醒的 assignee（V2-17）。停用用户（status≠active）时前端提示"存在 N 个待移交客户"（V-01 实测：JWT 不查库，停用不能阻止存量 token，见 §18 R-11）。
**驾驶舱**：全部聚合过 apply_data_scope；sales 仅本人行；金额卡对 designer/operator 后端直接剔除字段。

### 6.5 审计
`backend/app/middleware/audit.py` 硬编码 `{"ai","auth","users"}` 改为模块常量：
```python
SENSITIVE_MODULES = {"ai","auth","users","customers","customer_dialogues","follow_ups","requirements","content","reminders","dashboard"}
```
新模块的 audit 装饰器 module 名取自该集合（请求体 `[redacted]`）；`customer_pii_view`、`customer_export`、`content_export` 等动作必写 OperationLog（含行数/目标）。日志不得打印 PII（logger 统一走 masking）。

---

## 7. PII 规范（D3' 明文列 + 全链路脱敏）

| 场景 | 行为 |
|---|---|
| 列表 `GET /customers` | **完全不返回** phone/wechat/address，只返回 `has_phone: bool` |
| 详情 `GET /customers/{id}` | 掩码：`138****1234` / `ab***` / `浙江省杭州市***`（保留到市） |
| 明文 `GET /customers/{id}/pii` | 需 `customer:pii`；每次写 OperationLog(action=customer_pii_view, module=customers)；Redis 限速 30 次/时/用户（超限 429 {code:42901}） |
| 编辑（PUT） | **字段缺省=不改**；提交值带掩码特征（`****`/`***`）→ `422 {code:40001}`（V2-03 防覆盖）；前端只提交变更字段 |
| 搜索 | `?q=` 匹配 name(trgm/btree)；**仅持 customer:pii 者**启用 phone_norm 分支（精确+后 4 位），否则搜索即旁路泄露 |
| 导出 | `customer:export`；文件内 PII 默认脱敏；`?with_pii=true` 需同时持 `customer:pii`，OperationLog 记行数 |
| 知识库 | 新表无 KnowledgeSource 映射即隔离；`test_knowledge_isolation.py` 固化（检索 source 不含 customer/project + doc_chunk 写入点 AST 检查） |
| 日志 | 任何 logger 不得打印原文；`backend/app/core/masking.py`：`mask_phone/mask_wechat/mask_address`，单测边界（空、短号、国际号、无省市中文地址） |

掩码规范（与长稿一致）：
```python
mask_phone("13812341234") == "138****1234"
mask_phone("0571-88889999") == "0571****9999"   # 位数<7 → "****"
mask_wechat("abcdefg") == "ab***"               # 长度<=2 → "*" 全掩
mask_address("浙江省杭州市余杭区文一西路969号") == "浙江省杭州市***"
```

---

## 8. API 契约

### 8.1 通用约定（以 V-02/V-03 实测为准，不照抄评审稿假设）
- 成功响应 = `{"code": 200, "data": …}`（**无 msg 字段**，与既有端点一致）；错误 = HTTPException `detail={"code","msg"}`。
- 列表分页：入参 `page`(1-based)/`size`(默认 20 上限 100)；出参 `data = {"list": […], "total", "page", "size"}`（**键名 list**，对齐 proposals.py 实际）。排序默认服务端固定 `-create_time`；白名单字段可 `sort=-last_activity_at`。
- 时间：入出参 ISO8601 带时区。批量取：`?ids=a,b,c`（≤50）。
- 幂等：`POST /content/items/{id}/publish`、`POST /content/metrics/import` 支持请求头 `Idempotency-Key`（Redis 10min，重复返回首次结果）。
- 子资源嵌套路由；越权一律 404。

### 8.2 错误码（沿用既有 5 位段位；50301 已被 PDF 服务占用，AI 域用 50302）
| code | HTTP | 含义 |
|---|---|---|
| 40001 | 422 | 参数校验失败（字段级 details；含掩码值提交） |
| 40010 | 400 | 非法状态迁移 |
| 40011 | 400 | 回退/reopen 缺 reason |
| 40012 | 400 | 生成输入含禁用字段（客户/项目/成本，§9.2） |
| 40301 | 403 | 缺少权限（既有 PermissionChecker） |
| 40302 | 403 | 缺少 PII 权限 |
| 40401 | 404 | 资源不存在/已删除/**或越权**（不暴露存在性） |
| 40901 | 409 | 客户手机号疑似重复（data.candidates） |
| 40902 | 409 | 存在未处理子记录，拒绝删除 |
| 40903 | 409 | 唯一冲突（成员重复绑定/同 URL 重复发布） |
| 42901 | 429 | AI 限流 / PII 查看限速 |
| 50302 | 503 | AI 适配器不可用（AI_ADAPTER=none 或上游失败） |

### 8.3 客户 / 项目（节选；全部挂 PermissionChecker + apply_data_scope + assert_object_scope）
```http
GET    /api/v1/customers?stage=needs&level=A&owner_sales_id=&q=张&page=1&size=20&sort=-last_activity_at
  → data.list[]: {id, customer_no, name, source, level, stage, owner_sales:{id,name}, has_phone,
                  budget_min, budget_max, project_count, last_activity_at, create_time}
POST   /api/v1/customers                      # customer:edit；owner_sales_id 省略=本人；409 查重(force=true 放行)
GET    /api/v1/customers/{id}                 # PII 掩码版
PUT    /api/v1/customers/{id}                 # 缺省=不改；掩码特征 422
PATCH  /api/v1/customers/{id}/stage           # {to_stage, reason?}；非法 40010；回退缺 reason 40011
DELETE /api/v1/customers/{id}[?cascade=true]  # 40902 / admin|manager 级联
GET    /api/v1/customers/{id}/pii             # customer:pii；限速；审计
PUT    /api/v1/customers/{id}/owner           # customer:transfer；提醒重指派
GET    /api/v1/customers/{id}/summary         # 归集计数（金额字段按角色白名单剔除）
GET    /api/v1/customers/{id}/timeline        # 对话/跟进/需求/方案/阶段变更合并分页（V2-23）
GET|POST /api/v1/customers/{id}/dialogues /requirements /follow-ups     # 列表分页+写范围校验
GET|POST /api/v1/customers/{id}/proposals     # 关联方案（AC-2.1）
PUT|DELETE /api/v1/dialogues/{id}  /follow-ups/{id} …                   # 经父范围校验

GET|POST /api/v1/projects                      # 筛选 stage,status,customer_id,q
GET|PUT|DELETE /api/v1/projects/{id}           # designer 见 customer_brief
GET|POST|DELETE /api/v1/projects/{id}/members  # project:member；40903
GET|POST /api/v1/projects/{id}/assets          # project:asset；两步：先 /files 上传拿 attachment_id
  POST body {attachment_id, category, name, remark} → {id, version, is_current:true}
PATCH  /api/v1/projects/{id}/assets/{assetId}  # {status: approved|obsolete}
GET    /api/v1/projects/{id}/proposals
```
（dialogue 附件：`POST /api/v1/dialogues/{id}/attachments {attachment_ids:[…]}` 写 junction 表 + 回填 attachment biz_domain='customer'。）

### 8.4 驾驶舱（新文件 `api/v1/dashboard.py`，挂 `/api/v1/stats/dashboard/*` 不碰 stats.py 两端点；audit module=dashboard；权限 dashboard:view）
```http
GET /stats/dashboard/overview?range=30d
 → data: {range:{from,to}, new_customers:{value,prev,trend}, active_projects:{…},
          overdue_follow_ups:{…}, stalled_projects:{value,threshold_days},
          confirmed_amount:{value,currency,visible}|{visible:false},   # 金额：不可见角色直接剔除
          generated_at, cached}
GET /stats/dashboard/funnel     → {customer_funnel:[{stage,count 补齐0}], project_stages:[…]}
GET /stats/dashboard/sales?range=30d → {ranking:[…top10], my_row:{…}}   # sales 仅 my_row
GET /stats/dashboard/todos?limit=20  → {reminders:[…], follow_ups:[…], total_pending}
GET /stats/dashboard/content?range=30d → Phase 3 返回 {empty:true, empty_reason:"module_disabled"}
```
- 任何指标无数据 → `{"value":null,"empty_reason":"no_data"}`，前端渲染"待录入"，**禁止 0 占位**。

### 8.5 内容与提醒
```http
POST /api/v1/content/batches        # content:generate + ai:use + 限流（Phase 4 同步：N≤5、60s 硬超时、只落 done/failed）
 → data:{batch_id, status:"done", items:[{id,title,body,hashtags,verified,warnings}]}
 → 503 {code:50302}（AI 不可用：batch 不创建，零脏数据）
GET  /api/v1/content/batches /items/{id}   # customer/project 名服务端反查（operator 无 customer:view）
POST /api/v1/content/items/{id}/adopt [?confirm=true]  /reject {reason}  /produce  /duplicate
POST /api/v1/content/items/{id}/publish  # content:publish + Idempotency-Key；同事务 publication + R2×3
POST /api/v1/content/metrics             # {publication_id, views, likes, …, captured_at?}；同日 upsert
POST /api/v1/content/metrics/import      # multipart xlsx；Idempotency-Key；回执 §10.4
GET  /api/v1/reminders?status=pending    # 本人；admin/manager 可 ?assignee_id=
POST /api/v1/reminders/{id}/done /snooze {until} /cancel     # reminder:edit
GET  /api/v1/notifications?unread=true   POST /api/v1/notifications/read {ids|[all]}
```

## 9. AI 边界（红线 4）

### 9.1 输出 JSON Schema（严格，一次 N 条）
```json
{
  "type":"object","required":["items"],"additionalProperties":false,
  "properties":{"items":{"type":"array","minItems":1,"maxItems":5,"items":{
    "type":"object","required":["title","body","hashtags"],"additionalProperties":false,
    "properties":{
      "title":{"type":"string","maxLength":60},
      "body":{"type":"string","minLength":30,"maxLength":2000},
      "hashtags":{"type":"array","maxItems":10,"items":{"type":"string","maxLength":20}},
      "mentioned_products":{"type":"array","items":{"type":"string","maxLength":120}}
    }}}}
}
```

### 9.2 输入白名单（V2-09）
生成输入**只允许**：产品公开事实（products 服务回查的 name/specs/series，**不取价格/成本/供应商**）+ 操作者输入的 topic/tone/platform。**禁止**任何客户/项目/对话字段进入 prompt；请求体出现 customer_id 仅作关联标注不进 prompt，出现其他禁用字段 → 前置 `400 {code:40012}`。

### 9.3 事实回查与合规守卫
1. 请求前按 product_ids 回查 `{id,name,specs,series}` 作为"唯一可引用事实"。
2. 生成后对每条 `mentioned_products` 归一化匹配；未命中 → 该条 `verified=false`，body 不删改，UI 高亮警告（不误杀通用描述）。
3. 落库：`verified_payload={"_verified_by":"products_api","_verified_at":…,"products":[…],"unmatched":[…]}`。
4. 后处理兜底：正则拦截承诺性措辞（`\d+\s*元|￥\d+|最低|保证\d+天`）+ 广告法极限词表（D10，`app/services/data/ad_law_words.txt`）→ 命中写 `warnings[]`，不阻断生成；**adopt 带 warnings 必须 ?confirm=true 二次确认**（V2-16）。
5. prompt 明确禁止输出价格/折扣/交期/库存承诺。

### 9.4 失败与限流
| 情况 | 行为 |
|---|---|
| `AI_ADAPTER=none` | `503 {code:50302}`，**batch 不创建**（连 failed 都不写，零噪音） |
| 上游超时(>CONTENT_GEN_TIMEOUT_S=60)/5xx | batch `failed`+error_msg，0 item，503 |
| Schema 校验失败 | 重试 1 次（temperature -0.2）；再失败 → batch failed，`422 {code:40001, "AI 输出不符合约定结构"}` |
| 限流 | 沿用 rate_limiter（Redis 滑窗 10/min/用户）；key 加场景前缀 `ai_rate:content_generate:{uid}:{w}`（V-09：默认不分场景会互相挤占，加前缀参数默认值保持现行为）；超限 429 {code:42901} |
| 成本护栏 | N≤5、事实集≤10 产品、body≤2000 字，超出前置 400 |
| 记录 | 每条 model_provider/model_name/generation_version/prompt_version/latency_ms；指标 `content_generate_total{status}` |

### 9.5 需求提取 → Phase 7（默认关闭）
`POST /requirements/extract` → 只写 `pending_action(action_type='requirement.extract')` → 确认链路复用 `/ai/actions/{id}/confirm` → 落 requirements(source='ai_extracted')。前置：迁移扩 CHECK（原 0022 写法，约束名实测=`check_pending_action_type`）+ 输入脱敏 + 逐次确认 + 审计。取消/过期永不污染业务表。**本期 0020 之后该表零改动。**

---

## 10. 提醒与通知引擎（系统内 agent）

### 10.1 架构：事务内创建 + 轮询派发（不引入 Celery/outbox）
- **创建**：业务事件（adopt/produce/publish/follow_up 保存）在**同一 DB 事务**内 INSERT reminders（dedupe_key 冲突忽略）。"业务成功 ⇒ 提醒必存在"。
- **派发**：worker 每 60s 扫 `status IN ('pending','snoozed') AND due_at<=now()`，`FOR UPDATE SKIP LOCKED LIMIT 100` → 生成 notifications，置 sent/fired_at/attempts+1。
- **完成**：`close_reminders(dedupe_prefix, reason)` 由业务事件调用（produce/录快照/新建跟进）。
- **兜底扫描**（每 10 分钟）：R3 一致性校正（next_follow_at 被改 → 更新 due_at）；sent 超 `REMINDER_ESCALATE_HOURS=24` 未 done → overdue + 升级。
- 引擎为**纯函数 + `run_tick(session, now)`**（时钟可注入，V2-29）；Redis 心跳 `/tmp/worker_heartbeat`。

### 10.2 规则表
| 规则 | 触发 | due_at | assignee | dedupe_key | 完成条件 | 取消条件 |
|---|---|---|---|---|---|---|
| R1 content_video_check | item→adopted | adopted_at+2d @09:00 | adopted_by | `content_video_check:{item_id}` | →produced/published 或手动 done | rejected/删除 |
| R1b content_publish_check | item→produced | produced_at+2d @09:00 | produced 操作人 | `content_publish_check:{item_id}` | →published | rejected/删除 |
| R2 content_metric_t1/t3/t7 | publication 创建 | published_at+1/3/7d @09:00 | 发布创建者 | `content_metric:{pub_id}:t{n}` | 该 publication 存在 `captured_at ≥ due_at−12h` 的快照（**三条一起 done**，V2-08） | publication 删除 |
| R3 customer_follow_up | follow_up.next_follow_at 保存 | = next_follow_at | follower_id | `follow_up:{fu_id}` | 新建 follow_up / done_at 置位 / 客户 won|lost | follow_up 软删 |
| E1 升级 | 任一 reminder sent 后超 24h | 立即 | 全体 manager（无则 admin） | `{orig}:escalated` | 原提醒 done | 原提醒 cancelled |

客户移交（customer:transfer）→ 该客户 pending/sent 的 R3 提醒 assignee 重指派（改 dedupe_key 保留列 attempts，重指派写日志）。

### 10.3 due_at 算法（北京时间锚定，存 UTC）
```python
BIZ_TZ = ZoneInfo("Asia/Shanghai")
def due_at_for(base_utc, days, hour=settings.REMINDER_HOUR):          # 默认 09:00
    local = base_utc.astimezone(BIZ_TZ) + timedelta(days=days)
    local = local.replace(hour=hour, minute=0, second=0, microsecond=0)
    if settings.REMINDER_SKIP_WEEKEND and local.weekday() >= 5:       # 默认 false（运营周末也发内容）
        local += timedelta(days=7 - local.weekday())
    return local.astimezone(UTC)
```
提醒文案：模板优先（确定性）；LLM 仅 `REMINDER_LLM_POLISH=true` 时润色，失败/超时 1.5s 降级模板。**"何时提醒"完全由确定性规则决定。**

### 10.4 Excel 导入曝光（P1-14；模板 `scripts/templates/metrics_import_template.xlsx` 随 Phase 4 提交）
| 发布链接* | 采集日期* | 播放/浏览 | 点赞 | 评论 | 收藏 | 分享 | 留资 |
|---|---|---|---|---|---|---|---|
- 匹配 publish_url 精确 → 找不到该行失败 PUB_NOT_FOUND；`(publication_id, captured_date)` 已存在 → **upsert** 回执标 updated。
- ≤2MB、≤2000 行、仅 .xlsx；逐行隔离（参考产品导入做法，单行单事务）。
- 回执：`{total, created, updated, failed, errors:[{row, code, msg, raw}], error_file_url}`（失败行导出 xlsx 可改后重传）。

### 10.5 Worker 部署
与 backend 同镜像、command 覆盖；`docker-compose.yml` + `docker-compose.dev.yml` 双清单：
```yaml
  worker:
    build: ./backend            # 与 backend 同镜像配置
    command: ["python","-m","app.scripts.worker"]
    env_file: .env
    environment: ["WORKER_ROLE=reminder"]
    depends_on: {postgres: {condition: service_healthy}, redis: {condition: service_healthy}}
    healthcheck:
      test: ["CMD","python","-c","import pathlib,time,sys; p=pathlib.Path('/tmp/worker_heartbeat'); sys.exit(0 if p.exists() and time.time()-p.stat().st_mtime<180 else 1)"]
      interval: 60s
      timeout: 5s
      retries: 3
    restart: unless-stopped
```
主循环：`redis_lock("reminder_tick", ttl=50)` 内 `dispatch_due_reminders(100)` + 每 10 tick `reconcile_rules()`/`escalate_overdue()`；心跳+sleep(60)。多实例安全=SKIP LOCKED 主 + Redis 锁兜底；全部写入按 dedupe_key 幂等。README-OPS 增 worker 运维段（Phase 5/6 同步）。

---

## 11. 驾驶舱

### 11.1 指标公式（口径定死；字段名按 V-06 实测 `quotation.total_amount`/`status='confirmed'`）
| 卡/图 | 公式 | 索引依赖 | 可见角色 |
|---|---|---|---|
| 新增客户数 | count(customers.create_time ∈ range) + 环比上一等长区间 | ix_customers_create_time | 全（sales 本人） |
| 客户漏斗 | group by stage（0 计数补齐） | ix_customers_owner_stage | 同上 |
| 项目阶段分布 | group by stage WHERE status='active' | ix_projects_stage | 同上（designer 绑定内） |
| 停滞项目 | status='active' AND coalesce(last_activity_at, create_time) < now() − N days（N=DASHBOARD_STALL_DAYS=7） | ix_projects_activity | 同上 |
| 逾期跟进 | follow_ups done_at IS NULL AND next_follow_at < now() | ix_fu_next_pending | 同上 |
| 销售跟进排行 | group by follower_id count(*) over range top10 | ix_fu_follower_time | admin/manager 全量；sales 仅 my_row |
| 方案/报价/已确认额 | count(proposal)；count(quotation)；sum(quotation.total_amount WHERE status='confirmed') | ix_proposal_customer/project | admin/manager/sales(本人)；designer/operator **后端剔除字段** |
| 我的待办 | reminders(pending,sent,overdue, assignee=me) ∪ follow_ups(next_follow_at ≤ today+1, done_at IS NULL, follower=me) | ix_rm_inbox, ix_fu_next_pending | 本人 |
| 内容链路 | 生成数/采纳率(adopted+/生成数)/制成数/发布数/累计曝光(§4.12 最新快照和)/Top 内容/待录入曝光数 | ix_ci_status, ix_cms_pub_time | operator/manager/admin |
| 趋势分桶 | 日/周/月按 **Asia/Shanghai** 分桶（边界单测：23:59/00:01、跨月、周一起始） | — | — |

### 11.2 性能与缓存
- 预算：单端点 p95<800ms；整页 8 请求并发 p95<2s（AC-3.1）。
- 缓存 key `dash:{endpoint}:{user_id}:{role}:{sha1(params+scope)}`，TTL 45s±10s 抖动；**任何金额字段不进缓存**：overview 把 confirmed_amount 拆独立函数，缓存整体响应时排除金额键，返回前直查合并。
- Redis 不可用 → 直查（cached:false）不报错；同 key 重建 SETNX 短锁防击穿。
- 指标：`dashboard_query_seconds{endpoint}`、`pii_view_total`、reminder 系列（`reminders_due_total/sent/overdue`、`reminder_dispatch_seconds`、`worker_tick_total`）。

### 11.3 空态
`value:null + empty_reason ∈ {no_data, no_permission, module_disabled}`；前端统一 `<EmptyMetric>` 渲染"待录入/无权限/未启用"。Phase 3 上线时 content 卡返回 module_disabled，Phase 4 开启。

---

## 12. 前端

### 12.1 页面与路由（router.ts meta.permission）
| 路由 | 组件 | meta.permission |
|---|---|---|
| /dashboard | views/Dashboard.vue（指标卡+漏斗/趋势图+待办列表；时间范围与人员筛选） | dashboard:view |
| /customers | views/Customers.vue | customer:view |
| /customers/:id | views/CustomerDetail.vue（Tabs：概览/对话/需求/客资/方案/跟进/时间线） | customer:view |
| /projects | views/Projects.vue | project:view |
| /projects/:id | views/ProjectDetail.vue（Tabs：概览/成员/图纸/方案/跟进） | project:view |
| /content/workshop | views/ContentWorkshop.vue（生成/列表/采纳/不采纳/编辑/复制） | content:view |
| /content/publications | views/ContentPublications.vue（发布登记+曝光录入+Excel 导入） | content:view |
| 抽屉/铃铛 | components/TodoDrawer.vue + NotificationBell.vue | 登录即可 |

导航三处同步（MainLayout el-menu index / subMenuMap / routeLabels）；跳转一律 router.push；无权限菜单不渲染且请求不发出（router.beforeEach + axios 拦截双层）。登录落地页不改（A1），Dashboard 提供"设为首页"本地偏好。

### 12.2 图表与构建预算（P1-11）
- **不**把 echarts 塞进常驻 chunk：`const VChart = defineAsyncComponent(() => import('vue-echarts'))`，`echarts/core` + 按需注册（Bar/Line/Pie + Grid/Tooltip/Legend/CanvasRenderer），目标 gzip ≈180–250KB。
- vite manualChunks 增 `echarts: ['echarts/core','echarts/charts','echarts/components','echarts/renderers','vue-echarts']` 独立懒加载 chunk。
- 预算门禁：Phase 3 起记录 dist 总大小（基线 2.3M）与首屏 chunk；新增不得使首屏 chunk 增长 >10%（写进 Phase 3 退出标准）。

### 12.3 其他
- 状态/枚举中文映射集中在 `frontend/src/constants/crm.ts`，禁止散落字符串。
- PII 掩码**由后端返回**，前端不做二次掩码；"查看明文"按钮调 `/pii` 并提示"此操作将被记录"。
- 样式沿用 design-system.css 令牌；动效 prefers-reduced-motion 降级；≤600px 自查（客户列表转卡片、驾驶舱单列）。
- 用户管理角色下拉为动态拉取（V-07 实测），新角色自动出现，无需改 Users.vue。

### 12.4 文件上传扩展（图纸，V2-21/V-08）
```python
_ALLOWED_EXT_DRAWING = {".dwg", ".dxf", ".skp", ".psd"}   # 上限 95MB（nginx client_max_body_size=100M，留余量）
# 校验顺序：① 原 content-type 白名单命中 → 放行（行为不变）
#          ② 否则 末段扩展名 ∈ _ALLOWED_EXT_DRAWING 且 size ≤ 95MB → 放行，
#             强制 content_type='application/octet-stream'，file_type='other'（满足既有 CHECK），
#             魔数校验（DWG: AC10…; PSD: 8BPS; DXF: ASCII '  0 SECTION'头 宽松匹配；失败 422）
#          ③ 否则拒绝（原行为）
```
契约测试：原类型行为不变（回归）、dwg 放行、`.exe` 拒绝、96MB 拒绝、`a.dwg.exe` 拒绝（取最后一段扩展名）、下载响应 `Content-Disposition: attachment` + `X-Content-Type-Options: nosniff`。

---

## 13. 迁移计划（revision id ≤32 字符；全部带 downgrade）

| rev id | 内容 | 回退破坏性 | 回退前置 |
|---|---|---|---|
| `0018_crm_core` | customers, projects, project_members, entity_stage_logs；attachment +biz_domain/biz_scope_id(+idx)；（pg_trgm 分支） | **高**（drop 丢客资） | backup.sh + 确认表空 |
| `0019_crm_detail` | customer_dialogues(+junction), requirements, follow_ups, project_assets；proposal +2 可空 FK+idx | **高** | 同上 |
| `0020_crm_perms` | 16 权限码 + manager/designer/operator 三角色 + 映射（幂等 upsert）+ scene_image 双通道对齐 | 低 | 检查无用户绑定新角色 |
| `0021_content_tables` | content_batches/items/publications/metric_snapshots | **高** | backup |
| `0022_reminders` | reminders, notifications + 索引 | 中 | backup |

- **无 pending_action CHECK 迁移**（裁决 R5，原 0022 取消；Phase 7 若启用再引入，约束名用附录 D V-05 实测值）。
- 每个 revision 一个阶段内完成；禁止混 DDL 与大数据回填；种子 `WHERE NOT EXISTS` 幂等。
- **验证三连（每个 revision 必做，结果贴附录 D）**：
```bash
bash scripts/backup.sh
bash scripts/test_pg_up.sh          # 一次性 pgvector/pg16 @127.0.0.1:5432/ai_pim_test
cd backend && TEST_DATABASE_URL=... alembic upgrade head
                     && alembic downgrade -1 && alembic upgrade head
alembic current                      # == 目标 rev
psql: \d+ customers                  # 抽查约束/索引落地
```
- **downgrade 仅用于开发/测试**；生产回滚 = 镜像回退 + 备份恢复（迁移均为增量，旧代码兼容新 schema）。

---

## 14. 配置（pydantic-settings，缺失 fail-closed 的写法沿用 config.py 现状）
| 变量 | 默认 | 说明 |
|---|---|---|
| DASHBOARD_STALL_DAYS | 7 | 停滞判定天数 |
| DASHBOARD_CACHE_TTL | 45 | 秒；0=关缓存 |
| REMINDER_HOUR | 9 | 北京时间提醒时点 |
| REMINDER_SKIP_WEEKEND | false | 周末顺延 |
| REMINDER_ADOPT_DAYS / REMINDER_PUBLISH_DAYS | 2 / 2 | R1 / R1b |
| REMINDER_METRIC_DAYS | 1,3,7 | R2 节奏 |
| REMINDER_ESCALATE_HOURS | 24 | 升级阈值 |
| REMINDER_LLM_POLISH | false | 文案润色开关 |
| CONTENT_MAX_ITEMS / CONTENT_GEN_TIMEOUT_S | 5 / 60 | 生成护栏 |
| PII_VIEW_RATE_PER_HOUR | 30 | 明文查看限速 |
| FEATURE_CRM / FEATURE_CONTENT / FEATURE_REMINDER | true/true/true | 见下 |

**特性开关只控制**：① 前端菜单与路由注册；② worker 对应规则是否启用；③ 驾驶舱对应卡返回 module_disabled。**不控制后端路由注册**（否则权限契约测试的路由自省会随环境抖动）。关闭时后端仍可访问但前端无入口（权限码仍生效）。`.env.example` 同步全部新变量（不写任何真实口令）。

---

## 15. 可观测性与运维
1. **指标**：§11.2 全集 + `content_generate_total{status}` + `pii_view_total`；新增模块 logger（`crm.customers` 等），禁打 PII；AI 调用记录 model/latency/batch_id。
2. **审计日志量**：扩入敏感模块后 OperationLog ≈1.5–2×。保留策略：`scripts/purge_operation_log.sh`（常规 180 天；`customer_pii_view`/`*_export` 730 天），Phase 6 挂定时或写运维手册。
3. **备份**：每个迁移前 `scripts/backup.sh`；Phase 6 发版前全量+恢复演练记录；（若 D3' 改回加密）PII 密钥独立备份要求写入 README-OPS。
4. **容量**：客户/项目千级、对话万级、快照<5 万行/年——无分区需求。
5. **nginx**：client_max_body_size 100M 已够（图纸 95MB 上限留余量）；proxy_read_timeout 300s > 60s 同步生成。

---

## 16. 分阶段执行计划（每阶段一个可独立评审/回滚的提交组；结束跑 `scripts/gate.sh` 并记附录 D）

### Phase 0.5 — 基线清洁 ✅ 已完成（本文附录 D）
ruff 59→0（3e59f76）、eslint 10→0（4194b68）、gate.sh（079e6c8）、V-01…V-12 全部核验、测试库容器（scripts/test_pg_up.sh）、e2e 三轮基线全绿。

### Phase 1 — 地基（1.5 天）
`0018`+`0020` 迁移；`core/data_scope.py`、`core/masking.py`、`core/attachment_access.py`、audit `SENSITIVE_MODULES`；seed_data.py 同步（含 scene_image 补录）+ `test_permission_seed_sync.py`；permissions.ts/router meta。
**退出**：gate.sh 全绿；迁移三连通过；新增单测 ≥12（data_scope 角色×模型、掩码边界、attachment 闸）；admin 能给用户设 manager/designer/operator。**回滚**：downgrade 0017（先 backup）。

### Phase 2a — 客户域（1.5 天）
`0019`；models/schemas/services + `/customers` 全家（dialogues/requirements/follow_ups/timeline/summary/pii/transfer/查重/状态机 `customer_state.py`）；assert_object_scope；PII 序列化；前端 Customers/CustomerDetail。**退出**：AC-1.1/1.5、AC-2.2；IT-S02/S03、E2E-01/02/04；旧 API 契约快照零变化。**回滚**：0019 downgrade。

### Phase 2b — 项目域 + 图纸（1.5 天）
projects/members/assets API + `project_state.py` + D7 联动 + 时间线归集；files.py 扩展名分支 + 契约测试；attachment biz 回填；前端 Projects/ProjectDetail。D8 客户 Excel 导入（可砍）。**退出**：AC-1.2/1.3/1.4、AC-2.1；IT-P02/P03、IT-Q01、E2E-03。

### Phase 3 — 驾驶舱（2 天）
`api/v1/dashboard.py` 5 端点 + 缓存层（金额直查合并）+ Dashboard.vue（echarts 懒加载 + EmptyMetric）；content 卡 module_disabled。**退出**：AC-3.1/3.2；p95 实测记录（20 并发）；首屏 chunk 增长 ≤10%。

### Phase 4 — 新媒体工坊（3 天）
`0021`；AI 同步生成 + Schema 校验 + 事实回查 + 合规守卫；`content_state.py`；发布登记；曝光录入 + Excel 导入 + 模板；ContentWorkshop/ContentPublications；驾驶舱 content 卡开启。**退出**：AC-4.1/4.3/4.4；none 适配器 503 零脏数据；2000 行导入回执正确；同日重复导入不双计。

### Phase 5 — 提醒与 worker（2 天）
`0022`；`services/reminder_rules.py`（纯函数）+ `close_reminders`；`scripts/worker.py` + compose 双清单 + healthcheck；TodoDrawer/NotificationBell；metrics；purge_operation_log.sh 挂期。**退出**：AC-4.2；`docker compose up --scale worker=2` 跑 10 分钟无重复通知；杀 worker 重启不漏发不重发；overdue 指标可见；跨日时区单测（UTC/北京、周末）。

### Phase 6 — 文档、版本与全量回归（1 天）
HLD §七 定稿文本（§17）写入 docs/02；同步 docs/00–05（ERD/API/BPM）+ README-OPS（worker 段）+ RELEASE_GATE（worker 健康项）；CHANGELOG + `v1.10.0` 版本锚点；全量回归（unit/contract/integration/e2e×2 project/build_frontends.sh/portal build）；`scripts/build_frontends.sh` 构建 + 重建 nginx/backend 镜像注入 APP_VERSION/BUILD_ID/GIT_COMMIT/BUILD_TIME；验收演练附录 C 跑通；备份恢复演练记录。**退出**：RELEASE_GATE 全绿 + annotated tag。

### Phase 7（可选，默认关闭）— AI 需求提取（§9.5）+ NotificationChannel 企微/钉钉 Adapter。

**总计约 13.5 人日**（不含评审等待）。

---

## 17. HLD §七 定稿文本（Phase 6 写入 docs/02）
> **原文**：「系统不属于 CRM，不处理多级客户生命周期。」
> **改为**：「系统在 PIM 核心定位之外，提供面向定制家居销售场景的**轻量客户/项目协同模块**：客户漏斗与项目阶段均为**单层线性状态机**（允许带原因的回退，全部留痕），不包含多级客户生命周期、财务对账、多级审批流、营销自动化与客户自助门户。客户联系方式属受控隐私数据，按字段级权限（`customer:pii`）与强制审计管理。本模块不改变系统的 PIM 核心定位，亦不引入第二套主数据。」
> **决策记录**：2026-10-09 提出（10 月需求集），2026-10-10 定稿（本 v3 合并稿 §1）；约束见 §5/§6/§9。

---

## 18. 风险登记册
| ID | 风险 | 等级 | 缓解 |
|---|---|---|---|
| R-1 | 权限码同步漏改 → 菜单/接口不一致 | 高 | §6.3 六处检查单 + test_permission_seed_sync 自动断言 |
| R-2 | 数据范围遗漏某子表 → 越权读 | 高 | apply_data_scope 未定义 model **抛异常**；集成测试覆盖全部新端点 × 5 角色 |
| R-3 | PII 泄露（日志/导出/搜索旁路/掩码回写） | 高 | §7 五处封堵 + 掩码单测 + 422 拦截 |
| R-4 | 附件越权 | 高 | attachment biz 列 + can_access_attachment 全路径过闸 + 媒体库过滤（§4.8） |
| R-5 | downgrade 丢数据 | 中 | §13 破坏性分级 + 迁移前 backup 强制 + 生产回滚走镜像+备份 |
| R-6 | echarts 撑爆首屏 | 中 | 按需注册 + 懒加载 + 10% 预算门禁 |
| R-7 | 同步 AI 生成阻塞（60s）；worker 漏发/重发 | 中 | N≤5 硬超时+前端可取消；提醒持久化 DB，SKIP LOCKED+dedupe，healthcheck+restart |
| R-8 | 审计日志膨胀 | 低 | §15 保留策略 |
| R-9 | 云端 PG 与本地差异（pg_trgm 缺失等） | 中 | trgm 索引降级分支；Phase 1 在云端同版本 PG（16.14）验证迁移 |
| R-10 | 业务口径变更（停滞/曝光定义） | 低 | 全部环境变量化 |
| R-11 | 停用用户存量 JWT 仍有效（JWT 不查库） | 中 | 停用即触发客户移交/提醒重指派；敏感端点加 status 复查（Phase 2）；记运维手册 |
| R-12 | 新权限生效依赖强制重登 | 低 | 发版 checklist 固化；perm_ver 方案留作后续 |
| R-13 | scene_image 种子漂移复发 | 中 | seed 补录 + seed_sync 测试钉死 |

---

## 附录 A — 命令速查
```bash
# 红线首条（永远先跑）
wsl.exe -d RiChangPIM bash -lc "cd /home/AI-PIM/RiChangPIM && bash scripts/where-am-i.sh"
# 阶段门禁
bash scripts/gate.sh [backend|frontend|all]
# 测试库（一次性 pgvector/pg16，不碰生产卷）+ 迁移三连
bash scripts/test_pg_up.sh
cd backend && TEST_DATABASE_URL='postgresql+asyncpg://pim:<本地口令>@localhost:5432/ai_pim_test' \
  alembic upgrade head && alembic downgrade -1 && alembic upgrade head
# 集成 / e2e
TEST_DATABASE_URL=… python -m pytest tests -q --ignore=tests/unit
cd frontend && E2E_PORT=5199 npx playwright test --project=chromium --project="Mobile Chrome"
```
> 宿主 PowerShell 直传含管道/npx 命令会被引号吞掉（已踩坑）：一律「写 bash 脚本 → `wsl bash <路径>`」。

## 附录 B — 预期文件改动清单
**后端新增**：models/{customer,project,content,reminder}.py、schemas/ 同名、services/{customer,project,content,reminder,dashboard}_service.py、services/{customer,project,content}_state.py + reminder_rules.py（纯函数）、services/data/ad_law_words.txt、core/{data_scope,masking,attachment_access}.py、api/v1/{customers,projects,content,reminders,notifications,dashboard}.py、scripts/worker.py、迁移 0018–0022、tests/unit/{data_scope,masking,states,reminder_rules}、tests/test_permission_seed_sync.py、tests/test_knowledge_isolation.py、scripts/templates/metrics_import_template.xlsx、scripts/purge_operation_log.sh。
**后端修改（受控）**：middleware/audit.py（SENSITIVE_MODULES）、scripts/seed_data.py（+scene_image 补录）、api/v1/files.py（扩展名分支+biz 回填+can_access 闸）、models/product.py(Attachment +2 列)、models/sales.py(+2 列)、api/v1/__init__.py 路由注册、observability/metrics.py、docker-compose.yml/.dev.yml（worker）、.env.example。
**后端禁止**：stats.py 现有两端点、现有响应 schema、pending_action（本期）、portal/。
**前端新增**：7 个 view + TodoDrawer/NotificationBell/EmptyMetric + api/{customer,project,content,reminder,dashboard}.ts + constants/crm.ts + tests（vitest 组件 + Playwright 新 spec）。
**前端修改**：router.ts、MainLayout.vue（三处）、types/permissions.ts、vite.config.ts（echarts chunk）、package.json（echarts/vue-echarts）。

## 附录 C — 验收演练（Phase 6 必跑，可固化为 scripts/acceptance_demo.sh）
1. admin 建 manager/designer/operator 各 1 → 重登菜单正确。
2. sales A 建客户（手机 138…）→ 同手机再建 → 409 candidates；force 放行并留审计。
3. sales A 建项目绑 designer D；sales B 列表不见 + `PUT /customers/{A的}` → 404；`GET 附件` → 404。
4. designer D：只见绑定项目、customer_brief 无 PII；传 .dwg 成功 → 同名重传 version=2 旧版 is_current=false；改阶段 → 403；下载强制 attachment+nosniff。
5. 无 pii 账号详情见 `138****1234`；sales A 查看明文 → operation_log 新增 customer_pii_view；编辑提交掩码串 → 422。
6. 方案关联项目 → summary proposal_count/confirmed_amount 正确（operator 无金额卡=字段剔除）；旧方案列表响应字段零变化。
7. operator 生成 3 条 xhs 文案 → verified_payload 含产品事实；含"全网最低"那条 warnings 命中；采纳带 warnings 条目不带 confirm → 400/422，带 confirm → 成功；adopted 后 reminders +1（due=+2d@09:00 北京时间）；due 改过去 → worker 60s 内站内通知+铃铛。
8. produce → R1 关、R1b 开；登记发布 → R2×3、R1b 关；录 1 条快照 → R2×3 全 done、派生态 tracking。
9. Excel 导入 10 行（2 行坏链接）→ created 8/failed 2 + 错误文件下载；同文件重导 → updated 8 数字不翻倍。
10. 驾驶舱：admin 全量+金额；sales 仅本人；designer/operator 无金额字段；断 Redis → cached:false 正常返回；趋势分桶跨日边界正确。
11. AI_ADAPTER=none 重启 → 生成 503{50302}，content_batches 零新增。
12. `customer:transfer` 移交客户 → owner 变更 + pending R3 assignee 跟随。
13. `alembic downgrade 0017 → upgrade head`（测试库）无报错。

## 附录 D — 基线与 Phase 0 / 0.5 记录（实测）
### D.1 初始基线（2026-10-09，改动前）
backend `pytest tests/unit` **148 passed**；frontend vue-tsc exit 0、vitest **23 files/184 passed**、eslint 10 errors（全在测试文件）、portal build ok；backend `ruff check app` **59 errors**（51×E501 等，项目自带 venv 与新版双跑一致 → main 基线本就红）；compose 栈 healthy、head=0017、本机 PG18 down。

### D.2 源码核验 V 表（结论摘要；全文见 git 历史 a1dde8c 版《基线记录.md》附录 C）
V-01 JWT={sub,role_code,perms} 无版本位→发版强制重登｜V-02 响应 `{code:200,data}` 无 msg、列表键 `list`｜V-03 page/size｜V-04 Attachment 无 biz 位→junction+biz 列｜V-05 约束名 `check_pending_action_type/status`（本期不用）｜V-06 `quotation.total_amount`/status='confirmed'｜V-07 角色下拉动态无需改｜V-08 _ALLOWED content-type 字典 50/100MB｜V-09 限流 key `ai_rate:{uid}:{w}` 不分场景→内容生成加前缀｜V-10 manualChunks 三组、dist=2.3M｜V-11 检索按 source_type 作用域、隔离靠"不入库"｜V-12 容器方案替代 create_test_db.sh｜G0-4.6 nginx 100M｜G0-4.7 停用不清 token（R-11）｜G0-4.8 scene_image 漂移（R-13）｜G0-4.9 仅 token 持久化 localStorage｜G0-4.10 version_num varchar(64)≥32｜G0-4.11 产品导入行级隔离可复用｜G0-4.12 pydantic-settings fail-closed、cryptography 已在｜PG 16.14；vector 已装；pg_trgm available 未装（迁移带降级）。

### D.3 Phase 0.5 门禁执行
ruff 59→**0**（`chore(lint)` 3e59f76：--fix 4 项、F841×2 删死变量保留调用侧效应、B904 `from None`、UP028 yield from、E501×51 纯折行/拆函数；前后 148 passed + compileall）；eslint 10→**0**（4194b68，3 个 spec 文件）；gate.sh=079e6c8；测试库容器 `scripts/test_pg_up.sh`（pgvector/pg16、127.0.0.1:5432、库名 ai_pim_test、无生产卷）；集成冒烟 **19 passed/18.4s**（seed/权限契约/迁移 schema——证明 upgrade head 全链+种子幂等）；全量集成基线：⏳ 记录见 D.5；e2e **74 passed/2 skipped × 3 轮全绿**（282s/31.8s/35.5s；2 skip=spec 自带条件跳过；product-proposal 竞态未复现）。

### D.4 提交与分支
分支 `feature/crm-dashboard-content`：7a239a9(docs) → 3e59f76(ruff) → 4194b68(eslint) → 079e6c8(gate+裁决) → a1dde8c(附录C) → （本合并稿）。历史文档已移仓外，由本文取代。

### D.5 待追记
- 全量集成 passed/skipped/failed 数字（完成后追记；既有失败按"不新增"原则处理）。



