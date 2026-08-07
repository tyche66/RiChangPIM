# AI-PIM 项目文档审查报告（项目总经理 + 产品经理视角）

> **审查范围**：`AI-PIM概念方案.md` + `docs/` 下 10 份主文档 + 3 份附录，共 14 份文档
> **审查角色**：项目总经理 + 产品经理
> **审查目的**：发现跨文档一致性漏洞、关键缺失项、技术风险，输出最终执行版修改意见
> **审查日期**：2026-07-12
> **执行方式**：多 Agent 并行协作（Agent-A/B/C/D），主控整合校验

---

## 一、总体评价

### 1.1 优点

- **架构思路清晰**：四层架构 + Business API 为核心 + AI 适配器解耦，方向正确
- **数据解耦红线明确**：AI 不碰强准确性数据，回查闭环设计到位
- **文档体系完整**：从概念到工程的 10+3 结构覆盖面广
- **MVP 收敛原则正确**：聚焦"产品录入 → 方案生成 → H5 分享"核心链路

### 1.2 主要问题

经审查共发现 **5 类 27 项** 需修改问题，其中：

| 严重等级 | 数量 | 说明 |
| --- | --- | --- |
| P0 阻断 | 5 | 跨文档矛盾，会导致开发歧义 |
| P1 重要 | 12 | 关键缺失或设计漏洞 |
| P2 优化 | 10 | 增强可维护性与工程严谨度 |

---

## 二、P0 阻断级问题（必须修复）

### P0-1：表数量口径严重矛盾

| 文档 | 表述 |
| --- | --- |
| `AI-PIM概念方案.md` 第六章 | "30~40 张表" |
| `docs/02-HLD` 第五章 | "30~40 张表" |
| `docs/03-ERD` 第二章 | "22 张核心表" |
| `docs/appendix/数据字典` | 实际定义 23 张 |

**实际统计**：DDL 中建表 23 张（用户域4 + 产品域6 + 资产域3 + 销售域4 + 审计域6，含 visitor）。

**修改意见**：统一为 **"23 张核心表"**，修改 `概念方案.md`、`02-HLD`、`03-ERD`、`00-概述` 中所有相关表述。

---

### P0-2：软删除规范与实际建表矛盾

`数据字典.md` 第一章"通用字段"声明：

> 所有表共有：id / create_time / update_time / deleted_at / is_deleted

但实际 DDL 中以下 4 张表**没有**软删除字段（追加写表）：

- `share_log`
- `operation_log`
- `ai_conversation`
- `visitor`

**修改意见**：将"通用字段"改为"业务表通用字段"，新增"追加写表（日志/访客）字段规约"小节，明确这 4 张表不含 deleted_at/is_deleted，并说明原因。

---

### P0-3：权限矩阵引用了不存在的字段

`appendix/权限矩阵.md` 第三章"报价字段级权限矩阵"列出：

- `cost_subtotal`（成本小计）
- `profit_margin`（利润率）

但 `03-ERD` 的 `quotation` 和 `quotation_item` 表中**均无这两个字段**。

**修改意见**：二选一：
- **方案A（推荐）**：从权限矩阵移除这两个字段，避免过度设计
- **方案B**：在 ERD 中补充字段（quotation 增加 cost_subtotal DECIMAL(14,2)，profit_margin DECIMAL(5,4)）

建议方案A，V1 不做利润分析，V2 数据驾驶舱再补。

---

### P0-4：单角色设计与"多角色"描述矛盾

| 文档 | 表述 |
| --- | --- |
| `概念方案.md` 5.1 | "多角色权限控制" |
| `01-PRD` 第一章 | 角色定义（隐含多角色） |
| `03-ERD` user 表 | `role_id UUID NOT NULL`（单角色，外键） |

**矛盾**：user.role_id 为单值 NOT NULL，一个用户只能一个角色，与"多角色"描述不符。

**修改意见**：
- MVP 阶段明确为**单角色**（user.role_id）
- V2 多租户阶段演进为多角色（新增 user_role 关联表）
- 在 `01-PRD`、`02-HLD`、`03-ERD`、`权限矩阵` 中统一说明此演进路线

---

### P0-5：文件类型白名单不一致

| 文档 | 允许类型 |
| --- | --- |
| `03-ERD` attachment.file_type CHECK | image / video / pdf / doc / other |
| `04-OpenAPI` 14.1 文件上传 | image/jpeg, image/png, image/webp, video/mp4, application/pdf |

**矛盾**：ERD 支持 `doc` 类型，但 OpenAPI 上传白名单不含 doc/docx。

**修改意见**：统一为支持 doc/docx（业务场景需要上传产品手册 Word 版本），在 OpenAPI 白名单补充 `application/msword` 和 `application/vnd.openxmlformats-officedocument.wordprocessingml.document`。

---

## 三、P1 重要级问题

### P1-1：缺失健康检查接口

`06-部署方案` 4.1 步骤7 调用 `curl https://localhost/api/v1/health`，但 `04-OpenAPI` 未定义此接口。

**修改**：在 OpenAPI 补充 `GET /api/v1/health`（无需鉴权，返回 `{status, version, db, redis}` 状态）。

---

### P1-2：缺失关键索引

以下高频查询字段未建索引：

| 表 | 字段 | 查询场景 |
| --- | --- | --- |
| proposal_item | product_id | "哪些方案包含此产品" |
| quotation_item | product_id | "哪些报价单包含此产品" |
| share_token | share_id | 撤销分享时级联失效 token |
| product_image | attachment_id | 文件删除时检查引用 |
| product_manual | attachment_id | 文件删除时检查引用 |

**修改**：在 `03-ERD` 补充这 5 个索引。

---

### P1-3：ShareToken 级联失效机制未明确

`04-OpenAPI` 13.4 撤销分享：

> 将 share.status 置为 disabled，所有关联 token 立即失效

但未说明 token 如何"立即失效"——是查询时联表检查 share.status，还是 UPDATE share_token SET status='disabled'？

**修改**：在 `03-ERD` 第八章 ShareToken 凭证治理中补充级联失效策略：撤销分享时批量 UPDATE share_token SET status='disabled' WHERE share_id=$1，并建议应用层同时使 Redis 中缓存失效。

---

### P1-4：双写事务边界未定义

`05-BPM` 1.3 时序图中产品入库为"双写"（PostgreSQL + pgvector），但未定义：

- 向量化失败时是否回滚业务数据？
- 是同步双写还是异步补偿？

**修改**：在 `02-HLD` 第三章数据流补充事务边界说明：
- MVP：同步双写，向量化失败则整体回滚（数据完整性优先）
- V1+：可演进为异步补偿（业务数据先入库，向量化走消息队列重试）

---

### P1-5：pgvector 维度硬编码

`03-ERD` product.vector 为 `vector(1536)`，硬绑定 OpenAI ada-002 维度。但技术选型含 DeepSeek/Qwen，其 Embedding 维度可能为 768/1024。

**修改**：
- 在 ERD 注释说明"1536 为 OpenAI text-embedding-ada-002 维度，切换 Embedding 模型时需 ALTER"
- 在 `06-部署` .env 补充 `EMBEDDING_MODEL` 与 `EMBEDDING_DIM` 配置项

---

### P1-6：PRD 缺失页面清单

`01-PRD` 第七章有交互流程但无页面清单，前端无法评估工作量。

**修改**：在 PRD 补充"页面清单"小节，列出 MVP 全部页面（登录、产品列表、产品详情/编辑、分类管理、方案列表、方案详情、分享管理等约 15-20 个页面）。

---

### P1-7：缺失密码复杂度与 JWT 安全策略

`07-开发规范` 第六章安全规范只说"bcrypt 加密"，未定义：
- 密码复杂度（最小长度、大小写/数字/符号要求）
- JWT refresh token 轮换机制
- 登录失败锁定策略

**修改**：在 `07-开发规范` 补充安全策略小节。

---

### P1-8：缺失数据保留策略

`share_log`、`operation_log`、`ai_conversation` 为追加写，无保留策略会无限增长。

**修改**：在 `06-部署方案` 第七章备份恢复补充数据保留策略表（如日志保留 180 天，AI 对话保留 90 天）。

---

### P1-9：缺失审计日志覆盖范围

`operation_log` 表存在但未定义哪些动作必须记录。

**修改**：在 `07-开发规范` 或 `09-测试计划` 补充审计动作清单（登录、权限变更、产品删除、方案确认、报价确认、分享撤销等）。

---

### P1-10：缺失本地开发环境指南

`06-部署方案` 只有 Docker Compose 生产部署，无本地开发环境（前端热更新、后端 debug、数据库 GUI 连接）指南。

**修改**：在 `06-部署方案` 新增"本地开发环境"章节。

---

### P1-11：缺失文件下载/预览接口

`04-OpenAPI` 14 章只有上传和删除，无下载/预览。分享中心 PDF 导出、产品图片展示均需要。

**修改**：补充 `GET /api/v1/files/{attachment_id}/download` 和 `GET /api/v1/files/{attachment_id}/preview`（MinIO 预签名 URL）。

---

### P1-12：Mermaid 时序图参与者冗余

`05-BPM` 3.3 时序图中 `Share as 分享中心` 既有自调用又作为参与者，语法不清晰，应拆为 API 与 Share Service 或合并到 API。

**修改**：重绘时序图，将"分享中心"作为 API 内部模块，参与者简化为 销售/API/AI/客户。

---

## 四、P2 优化级问题

| 编号 | 问题 | 修改意见 |
| --- | --- | --- |
| P2-1 | `03-ERD` 第十节子标题用 9.1-9.4 | 改为 10.1-10.4 |
| P2-2 | `02-HLD` 文件名 `02-系统架构与设计(HLD)` 与概念方案引用的 `02-系统架构(HLD)` 不一致 | 以实际文件名为准，更新概念方案引用 |
| P2-3 | `appendix/` 缺失 `原型图/` 目录（下一步.txt 提及） | 创建占位 README 说明 V1 补充 |
| P2-4 | 产品表缺失常见属性（重量/尺寸/颜色/保修期） | V1 评估是否扩展，当前 material 字段够 MVP |
| P2-5 | quotation 表缺失 creator_id 与 valid_until（报价有效期） | 补充 creator_id UUID + valid_until TIMESTAMPTZ |
| P2-6 | proposal 表缺失 total_face_value（面价合计）便于方案列表展示 | 补充 total_face_value DECIMAL(14,2) |
| P2-7 | 缺失产品全文检索方案（当前仅 ILIKE） | V1 评估 pg_trgm 或 tsvector |
| P2-8 | 缺失缓存策略（Redis 用途未细化） | 在 02-HLD 补充缓存策略小节 |
| P2-9 | `名词解释.md` 缺失：Visitor/ShareLog/FingerprintJS/预签名URL | 补充术语 |
| P2-10 | 缺失 API Mock / Postman Collection 交付物 | 在 08-路线图 M1 交付物补充 |

---

## 五、多 Agent 协作任务分配

基于上述问题，拆分为 4 个并行 Agent 工作流 + 1 个整合校验：

### Agent-A：架构与数据层（02-HLD / 03-ERD / 数据字典）

**P0 修复**：P0-1（表数量统一23）、P0-2（软删除规约）、P0-3（权限矩阵字段-与Agent-C协同）、P0-5（file_type对齐）
**P1 修复**：P1-2（补5个索引）、P1-3（ShareToken级联）、P1-4（事务边界）、P1-5（pgvector维度）
**P2 修复**：P2-1（章节编号）、P2-5/P2-6（补字段）、P2-8（缓存策略）

### Agent-B：接口与流程层（04-OpenAPI / 05-BPM）

**P0 修复**：P0-5（文件类型白名单对齐）
**P1 修复**：P1-1（health接口）、P1-3（级联失效流程图）、P1-11（文件下载接口）、P1-12（Mermaid重绘）
**P2 修复**：P2-2（文件名引用）

### Agent-C：产品需求与权限（00-概述 / 01-PRD / 权限矩阵）

**P0 修复**：P0-3（移除不存在字段）、P0-4（单/多角色演进说明）
**P1 修复**：P1-6（页面清单）
**P2 修复**：P2-4（产品属性评估说明）

### Agent-D：工程与交付层（06-部署 / 07-规范 / 08-路线图 / 09-测试 / 名词解释）

**P1 修复**：P1-7（密码/JWT策略）、P1-8（数据保留）、P1-9（审计覆盖）、P1-10（本地开发环境）
**P2 修复**：P2-3（原型图占位）、P2-9（术语补充）、P2-10（Mock交付物）

### 主控整合（任务6）

- 交叉引用一致性校验（表数量/字段名/API路径/阶段标记）
- Mermaid 语法验证
- 文档导航链接验证
- 输出最终修订说明

---

## 六、执行原则

1. **不破坏现有正确内容**：修改遵循最小侵入原则，只动需要改的
2. **保持文档风格一致**：表格优先、Mermaid 图、代码块、⚠️ 提示框风格延续
3. **跨文档协同**：P0-3（字段）、P0-5（文件类型）需 Agent-A 与 Agent-C/B 协同，以 ERD 为基准
4. **阶段标记清晰**：所有新增字段/接口必须标注 MVP/V1/V2 阶段
5. **修订记录**：每份文档末尾追加"修订记录"小节，记录本次修改项

---

## 七、验收标准

- [ ] 5 个 P0 问题全部修复，跨文档口径一致
- [ ] 12 个 P1 问题全部修复或显式标注"V1 处理"
- [ ] 10 个 P2 问题至少修复 7 个，其余标注后续处理
- [ ] 所有 Mermaid 图可通过语法校验
- [ ] 所有文档导航链接可达
- [ ] 每份文档末尾有修订记录

---

*本报告作为多 Agent 协作的统一指令源，各 Agent 须严格按分配范围执行。*
