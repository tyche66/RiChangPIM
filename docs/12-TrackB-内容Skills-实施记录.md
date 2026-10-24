# Track B：内容 Skills 与独立选题 — 实施记录

> 本文记录 Track B 的改造内容、验收方式与遗留事项。

## 1. 数据模型（新增 `0024_content_skills`）

| 表 | 关键列 |
| --- | --- |
| `content_skills` | `code`（唯一，部分索引）、`name`、`skill_type`(topic/content)、`description`、`prompt_template`、`output_schema`(JSONB)、`prompt_version`、`supported_platforms`(JSONB)、`enabled`、`sort_order`、软删+审计 |
| `content_topic_runs` | `skill_id`(RESTRICT)、`skill_code`、`topic`、`platform`、`tone`、`product_ids`(JSONB)、`requested_count`(1–10)、`status`、模型元信息 |
| `content_topic_items` | `run_id`(RESTRICT)、`title`、`angle`、`audience`、`reason`、`suggested_platform`、`related_product_ids`(JSONB)、`source_skill_code`、`status`(draft/adopted/rejected/used)、`content_batch_id`(可空) |

`content_batches.source_skill_code` / `content_items.source_skill_code` 为新增可空列，
用于追溯生成时使用的 Skill（空 = 默认模板），旧数据可读。

迁移同时幂等种子 `content:manage` 权限，并把 admin 角色映射到该权限。

## 2. 权限模型

| 位置 | 改动 |
| --- | --- |
| `backend/app/scripts/seed_data.py` | `PERMISSIONS` 增加 `("content:manage", "内容Skill管理", "content", "manage", "write")` |
| `backend/alembic/versions/0024_content_skills.py` | 幂等写入同一条权限 + admin 角色映射 |
| `frontend/src/types/permissions.ts` | `PERMISSIONS` / `RESOURCE_PERMISSIONS.content` / `PERMISSION_NAMES` 同步（契约测试 73→74） |
| `backend/tests/test_permission_seed_sync.py` | 期望集合同步 |
| `backend/tests/test_permission_contract.py` | content 全部路由（含 Skills 管理与选题）纳入契约自省；`content_router` 登记进 `_ROUTER_PREFIX` |

## 3. 后端 API（`backend/app/api/v1/content_skills.py`）

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/v1/content/skills` | `content:view` | 选用列表，**默认只返回 enabled** |
| GET | `/api/v1/content/skills/manage` | `content:manage` | 管理中心列表（含停用） |
| POST | `/api/v1/content/skills/manage` | `content:manage` | 新增 |
| PUT | `/api/v1/content/skills/manage/{id}` | `content:manage` | 编辑 |
| POST | `/api/v1/content/skills/manage/{id}/toggle` | `content:manage` | 启用/停用 |
| DELETE | `/api/v1/content/skills/manage/{id}` | `content:manage` | 软删除 |
| POST | `/api/v1/content/topics/runs` | `content:generate` | 创建选题运行 |
| GET | `/api/v1/content/topics/runs` | `content:view` | 选题运行列表 |
| GET | `/api/v1/content/topics/runs/{id}` | `content:view` | 选题运行详情（含 items） |
| POST | `/api/v1/content/topics/items/{id}/adopt` | `content:adopt` | 采纳选题 |
| POST | `/api/v1/content/topics/items/{id}/reject` | `content:adopt` | 不采纳 |

**关键安全设计**：管理端点有五层防护——

1. `PermissionChecker("content:manage")`（FastAPI 依赖，401/403 契约）；
2. **`_require_admin(request.state.role_code)` 显式角色校验**——因为
   `PermissionChecker` 对 `role_code == "admin"` 会整体跳过权限码检查，
   若只依赖它，任何拿到 admin 令牌的人都能通过；而非 admin 即使 JWT 里
   恰好带有 `content:manage`（例如角色映射变更后的旧令牌）也一律 403；
3. 生成/选题端点**不信任前端开关**：`_get_enabled_skill(skill_code)` 每次重新
   查库校验 `enabled=true` 且未软删，停用 Skill 直接 400；
4. `skill_type` 强校验：选题只能选 `topic` Skill，内容生成只能选 `content` Skill；
5. 所有写操作挂 `@audit_action(..., module="content")` 审计。

## 4. 默认 Skill 与既有行为不回归

`backend/app/scripts/seed_default_skills.py`（幂等）写入两个默认 Skill：

* `content-default`（`skill_type=content`）：`prompt_template` 与
  `content_service._build_generation_prompt` 内置提示词**逐字等价**，
  `output_schema` 直接引用 `content_service.OUTPUT_SCHEMA`，
  `prompt_version` 引用 `content_service.PROMPT_VERSION`——
  不选 Skill 时走内置路径，选它时走同一条提示词，行为一致。
* `topic-basic`（`skill_type=topic`）：选题 Skill，配 `TOPIC_OUTPUT_SCHEMA`。

`OUTPUT_SCHEMA`、合规检查（`_check_compliance`）、产品事实回查
（`_verify_mentioned_products`）、模型 fail-closed（超时/非 JSON/无有效条目 →
batch failed）全部保持原状，未做任何放宽。

## 5. 前端

| 文件 | 改动 |
| --- | --- |
| `src/api/content.ts` | 新增 `ContentSkill` / `ContentTopicItem` / `ContentTopicRun` 类型与 11 个 API 方法 |
| `src/router.ts` | 新增 `content/topics`（`content:view`）与 `content/skills`（`content:manage` + **`adminOnly: true`**）；`beforeEach` 增加 adminOnly 角色门 |
| `src/views/ContentTopics.vue` | 独立选题页：Skill 下拉（仅 enabled + topic）、主题/平台/语气/产品/数量、生成、采纳/驳回、带去内容工坊 |
| `src/views/ContentSkills.vue` | Skills 管理中心：列表、新增/编辑对话框、启停、软删除、排序 |
| `src/layouts/MainLayout.vue` | 「客户与项目」分组新增「独立选题」（`content:view`）与「Skills 管理」（`isAdmin`）；面包屑补齐 |

Skills 管理中心的**后端** `_require_admin` 与**前端** `adminOnly` + `isAdmin`
是同源双门：前端隐藏入口只是体验，非管理员直接访问 `/content/skills/manage`
会拿到 403。

## 6. 验收

```
backend/tests/unit/test_content_skills_admin.py      21 passed
  ├─ 非 admin 一律 403（含持有 content:manage 权限码但角色非 admin） 5 cases
  ├─ 停用 Skill 不出现在任何选用列表                               4 cases
  ├─ topic/content 类型不可混用                                    3 cases
  └─ 默认 Skill 与内置提示词/OUTPUT_SCHEMA 等价                     4 cases
frontend/tests/components/MainLayoutSkillsMenu.spec.ts   10 passed
  ├─ Skills 菜单项由 isAdmin 控制
  ├─ 独立选题菜单项由 content:view 控制（非 admin 也可见）
  ├─ showCrmMenu 包含 isAdmin
  ├─ 路由 adminOnly 与 beforeEach 角色门
  └─ content:manage 契约（PERMISSIONS/RESOURCE_PERMISSIONS/NAMES）
backend tests/unit（全量）                               372 passed
frontend vitest（全量）                                 194 passed
frontend build / portal build                           均通过
ruff check app/                                         All checks passed
```

迁移验证（一次性容器 + 独立 scratch 库）：

```
全新库 ai_pim_mig:  upgrade head → 0024_content_skills (head)
                    downgrade 0017 → 0017
                    upgrade head  → 0024 (head)                       ✅
本地 ai_pim:       upgrade head → 0024 (head)，权限与默认 Skill 已种子  ✅
                   重复执行 seed_default_skills → created=0（幂等）    ✅
```

`content:manage` 已写入本地库 `permission` 表，admin 角色持有 1 条映射。

## 7. 未完成 / 待业务确认

1. **选题生成尚未接入 LLM**：`POST /content/topics/runs` 目前创建 run 记录并返回
   空 `items` 列表。接入方式应复用 `content_service` 的 adapter 调用与
   `_check_compliance`/fail-closed 流程，但需要业务方确认选题的提示词与
   输出 Schema（默认模板已就绪，位于 `seed_default_skills.py`）。
2. **选题带入内容工坊**：前端已跳转 `/content/workshop?topic_id=...`，
   但 ContentWorkshop 尚未读取该 query 预填 topic（属展示联调，不影响安全边界）。
3. **待业务确认**：默认 `content-default` Skill 是否应随 `content_service` 提示词
   变更而同步更新（当前是种子时快照，需在改内置提示词时重跑种子）。
4. **生产数据操作**：见文末清单。**本任务未对生产执行任何命令。**
