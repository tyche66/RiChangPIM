# docs/03 — 数据模型 / ERD（实体关系图）

> 本文档为 **AI-PIM MVP（阶段①~③）已交付** 的权威数据模型说明，依据实际 ORM
> （`backend/app/models/*`）与 Alembic migration（`0001_initial` → `0009_sunon_pilot_product_fields`）
> 逐表核对生成，**仅描述已实现行为，不虚构表/字段**。
>
> 源依据：
> - ORM：`app/models/base.py`、`product.py`、`sales.py`、`audit.py`、`user.py`、`doc_chunk.py`
> - Migration：`alembic/versions/0001_initial.py` → `0009_sunon_pilot_product_fields.py`
> - 通用基类 `CommonBase` 为所有业务表提供：`id`（PK, UUID）、`create_time`、
>   `update_time`（`BEFORE UPDATE` 触发器维护）、`deleted_at`（软删除时间）、
>   `is_deleted`（布尔软删除标记，默认 `false`）。
>   `audit` 模块模型（`share`/`share_token`/`visitor`/`share_log`/`operation_log`/
>   `ai_conversation`）直接继承 `Base` 并显式声明相同列，与 migration 一致。

---

## 一、表清单（共 24 张，全部来自 ORM + migration）

| 表名 | 模块 | 说明 |
|---|---|---|
| role | 权限 | 角色 |
| permission | 权限 | 权限点 |
| role_permission | 权限 | 角色-权限关联 |
| user | 账户 | 用户 |
| category | 产品 | 品类（树） |
| brand | 产品 | 品牌 |
| supplier | 产品 | 供应商 |
| tag | 产品 | 标签 |
| product | 产品 | 产品主表 |
| product_tag | 产品 | 产品-标签关联 |
| product_image | 产品 | 产品图片（引用 attachment） |
| product_manual | 产品 | 产品说明书（引用 attachment） |
| product_manual_chunk | 产品/RAG | 说明书切片 + 向量 |
| attachment | 文件 | 通用附件（MinIO 对象） |
| proposal | 销售 | 方案 |
| proposal_item | 销售 | 方案明细 |
| quotation | 销售 | 报价单 |
| quotation_item | 销售 | 报价单明细 |
| share | 分享 | 分享记录 |
| share_token | 分享 | 分享令牌 |
| share_log | 分享 | 分享访问日志 |
| visitor | 分享 | 访客（对应旧文档命名 `share_visitors`） |
| operation_log | 审计 | 操作审计日志 |
| ai_conversation | AI | AI 会话 |

> 命名映射（旧文档 `03*` 中曾用名 → 实际表名）：
> - `share_visitors` → **`visitor`**（访客表，全系统唯一访客主体）
> - `share_logs` → **`share_log`**（分享访问日志）

---

## 二、逐表字段核对

约定：P=主键；FK=外键；U=唯一约束；IX=普通索引；CHK=CHECK 约束；
SoftDel=软删除（`is_deleted`/`deleted_at`）；`↻`=由 DB 触发器维护 `update_time`。

### 2.1 quotation / quotation_item（销售-报价）

#### quotation
| 字段 | 类型 | nullable | default | 约束 | 说明 |
|---|---|---|---|---|---|
| id | UUID | N | uuid4 | P | |
| quotation_no | String(64) | N | — | U | 报价单号，格式 `QT-{year}-{6位}` |
| proposal_id | UUID | N | — | FK→proposal.id | 关联方案 |
| creator_id | UUID | N | — | FK→user.id | 创建人 |
| valid_until | DateTime(tz) | Y | — | | 有效期至 |
| total_amount | Float | N | 0 | | 总价（后端计算） |
| **subtotal** | Float | N | 0 | | **明细小计 Σ，由 `0003` migration 新增** |
| tax_rate | Float | N | 0.13 | | 税率 |
| discount | Float | N | 1.0 | | 折扣 |
| status | String(20) | N | 'draft' | | draft/confirmed（当前后端约束语义） |
| create_time / update_time | DateTime(tz) | N | now | `↻` | |
| deleted_at | DateTime(tz) | Y | — | SoftDel | |
| is_deleted | Boolean | N | false | SoftDel | |

- **subtotal 与 0003 migration**：初始 `0001` 的 `quotation` 表**不含** `subtotal`；
  `0003_add_quotation_subtotal` 以 `nullable=False, server_default=0` 补列，与 ORM
  `subtotal = Column(Float, default=0)` 一致。
- **计算规则（已实现，后端计算，非 DB 列）**：每条 `QuotationItem.subtotal =
  unit_price * quantity`；`subtotal（报价单）= Σ(item.subtotal)`；
  `total_amount = subtotal * discount * (1 + tax_rate)`（见 `app/api/v1/quotations.py:
  _compute_totals`）。
- `status='confirmed'` 后不允许 PUT 修改（返回 42201）；V1.1 新增独立 `POST /quotations/{id}/confirm`，重复确认幂等。

#### quotation_item
| 字段 | 类型 | nullable | default | 约束 | 说明 |
|---|---|---|---|---|---|
| id | UUID | N | uuid4 | P | |
| quotation_id | UUID | N | — | FK→quotation.id ON DELETE CASCADE | |
| product_id | UUID | N | — | FK→product.id | |
| quantity | Integer | N | 1 | | 数量 |
| unit_price | Float | N | — | | 单价 |
| tax_rate | Float | N | 0.13 | | 行税率 |
| subtotal | Float | N | — | | 行小计（=unit_price*quantity） |
| create_time / update_time | DateTime(tz) | N | now | `↻` | |
| deleted_at / is_deleted | — | — | — | SoftDel | |

---

### 2.2 attachment / product_image / product_manual（文件）

#### attachment
| 字段 | 类型 | nullable | default | 约束 | 说明 |
|---|---|---|---|---|---|
| id | UUID | N | uuid4 | P | |
| file_name | String(255) | N | — | | 原始文件名 |
| file_url | String(512) | N | — | | 访问路径 `/files/{object_key}` |
| **file_type** | String(32) | N | — | **CHK `file_type IN ('image','video','pdf','doc','other')`** | canonical 取值见 §2.2.4 |
| file_size | Integer | N | — | | 字节数 |
| storage_type | String(20) | N | 'minio' | | 存储类型 |
| oss_key | String(512) | N | — | | MinIO 对象键 |
| create_time / update_time | DateTime(tz) | N | now | `↻` | |
| deleted_at / is_deleted | — | — | — | SoftDel | |

#### 2.2.1 attachment.file_type 的 canonical 值（最终）
- 数据库 CHECK 约束（`0001` `check_attachment_file_type`）**仅允许**
  `image` / `video` / `pdf` / `doc` / `other`。
- 上传实现（`app/api/v1/files.py` `ALLOWED_FILE_TYPES = {"image","video","pdf","doc",
  "other"}`）以此为准：PDF→`pdf`，Word(`.doc`/`.docx`)→`doc`。
- **结论：canonical 集合为上述 5 个；不存在 `document` 取值**（旧实现写入
  `"document"` 会违反 CHECK 约束导致 IntegrityError，已修正）。

#### product_image
| 字段 | 类型 | nullable | default | 约束 | 说明 |
|---|---|---|---|---|---|
| id | UUID | N | uuid4 | P | |
| product_id | UUID | N | — | FK→product.id | |
| attachment_id | UUID | N | — | FK→attachment.id | 引用附件 |
| sort | Integer | N | 0 | | 排序 |
| is_cover | Boolean | N | false | | 是否封面 |
| create_time / update_time | DateTime(tz) | N | now | `↻` | |
| deleted_at / is_deleted | — | — | — | SoftDel | |

#### product_manual
| 字段 | 类型 | nullable | default | 约束 | 说明 |
|---|---|---|---|---|---|
| id | UUID | N | uuid4 | P | |
| product_id | UUID | N | — | FK→product.id | |
| attachment_id | UUID | N | — | FK→attachment.id | 引用附件 |
| doc_type | String(32) | N | — | CHK `doc_type IN ('manual','spec','datasheet','certificate','other')` | 文档类型 |
| parsed_content | Text | Y | — | | 解析文本 |
| parse_status | String(20) | N | pending | CHK `pending/processing/parsed/failed/ocr_required` | 解析状态，`ocr_required` 由 `0008` 扩展 |
| parse_error | Text | Y | — | | 解析或 OCR 失败原因 |
| parser_name / parser_version | String | Y | — | | pypdf/python-docx 等 parser 元数据 |
| page_count | Integer | Y | — | | 页数 |
| create_time / update_time | DateTime(tz) | N | now | `↻` | |
| deleted_at / is_deleted | — | — | — | SoftDel | |

#### product_manual_chunk（RAG，0002 新增）
| 字段 | 类型 | nullable | default | 约束 | 说明 |
|---|---|---|---|---|---|
| id | UUID | N | uuid4 | P | |
| product_manual_id | UUID | N | — | FK→product_manual.id ON DELETE CASCADE | |
| product_id | UUID | N | — | FK→product.id ON DELETE CASCADE | |
| chunk_index | Integer | N | — | | 切片序号 |
| chunk_text | Text | N | — | | 切片文本 |
| chunk_tokens | Integer | Y | 0 | | token 数 |
| embedding | Vector(1536) | Y | — | HNSW 索引 | 向量（依赖 pgvector；未安装时 ORM 退化但字段仍存在） |
| create_time / update_time | DateTime(tz) | N | now | `↻` | |
| deleted_at / is_deleted | — | — | — | SoftDel | |

---

### 2.3 share / share_token / share_log / visitor（分享）

#### share
| 字段 | 类型 | nullable | default | 约束 | 说明 |
|---|---|---|---|---|---|
| id | UUID | N | uuid4 | P | |
| share_type | String(20) | N | — | | proposal / quotation |
| target_id | UUID | N | — | | 指向 proposal.id 或 quotation.id |
| creator_id | UUID | N | — | FK→user.id | 创建人 |
| status | String(20) | N | 'active' | | active/disabled/expired |
| create_time / update_time | DateTime(tz) | N | now | `↻` | |
| deleted_at / is_deleted | — | — | — | SoftDel | |

#### share_token
| 字段 | 类型 | nullable | default | 约束 | 说明 |
|---|---|---|---|---|---|
| id | UUID | N | uuid4 | P | |
| share_id | UUID | N | — | FK→share.id | |
| token | String(64) | N | — | **U**（partial idx：`is_deleted=false` 唯一） | 分享令牌串 |
| password | String(255) | Y | — | | 访问密码（可选） |
| expire_time | DateTime(tz) | Y | — | | 过期时间 |
| max_access_count | Integer | Y | — | | 访问次数上限（NULL=不限） |
| current_access_count | Integer | N | 0 | | 已访问次数（原子自增） |
| status | String(20) | N | 'active' | | active/disabled/expired |
| create_time / update_time | DateTime(tz) | N | now | `↻` | |
| deleted_at / is_deleted | — | — | — | SoftDel | |

#### share_log
| 字段 | 类型 | nullable | default | 约束 | 说明 |
|---|---|---|---|---|---|
| id | UUID | N | uuid4 | P | |
| share_token_id | UUID | N | — | FK→share_token.id | |
| visitor_id | UUID | Y | — | FK→visitor.id | |
| visitor_ip | String(64) | Y | — | | |
| visitor_ua | String(512) | Y | — | | User-Agent |
| device_fingerprint | String(128) | Y | — | | 设备指纹 |
| openid | String(64) | Y | — | | 微信 openid |
| access_time | DateTime(tz) | N | now | | 访问时间 |
| access_result | String(20) | N | — | | success/denied_* |
| （无 update_time/is_deleted — 追加型日志） | | | | | |

#### visitor（旧命名 `share_visitors`）
| 字段 | 类型 | nullable | default | 约束 | 说明 |
|---|---|---|---|---|---|
| id | UUID | N | uuid4 | P | |
| fingerprint | String(128) | Y | — | | 设备指纹 |
| openid | String(64) | Y | — | **U** | 微信 openid 唯一 |
| unionid | String(64) | Y | — | | |
| nickname | String(128) | Y | — | | |
| avatar_url | String(512) | Y | — | | |
| first_seen_time / last_seen_time | DateTime(tz) | N | now | `↻` | |
| create_time / update_time | DateTime(tz) | N | now | `↻` | |

---

### 2.4 product（产品主表，阶段①②③实际字段）

| 字段 | 类型 | nullable | default | 约束 | 说明 |
|---|---|---|---|---|---|
| id | UUID | N | uuid4 | P | |
| product_no | String(64) | N | — | **U**（partial idx `is_deleted=false`） | 产品编号 |
| product_name | String(255) | N | — | | 名称 |
| brand_id | UUID | N | — | FK→brand.id | 品牌 |
| supplier_id | UUID | N | — | FK→supplier.id | 供应商 |
| category_id | UUID | N | — | FK→category.id | 品类 |
| face_price | Float | N | — | CHK 占位值 99999 仅允许 completeness_status=pending | 面价；待核价使用内部占位值 99999，UI/导出显示“待核价” |
| cost_price | Float | Y | — | | 成本价（敏感字段，sales/viewer 不可见） |
| material | String(128) | Y | — | | 材质 |
| stock_status | String(20) | N | 'in_stock' | CHK `IN ('in_stock','out_of_stock','preorder','unknown')` | 库存状态 |
| status | String(20) | N | 'draft' | CHK `IN ('active','inactive','draft')` | 上下架状态 |
| description | Text | Y | — | | 描述 |
| specification | String(255) | Y | — | | 规格（0009） |
| colors | Text | Y | — | | 颜色（0009） |
| data_source | String(512) | Y | — | | 数据来源（0009） |
| completeness_status | String(20) | N | 'complete' | CHK complete/pending/unknown | 字段完整性（0009） |
| vector | Vector(1536) | Y | — | HNSW 索引 | 产品向量（pgvector；未装则字段退化） |
| create_time / update_time | DateTime(tz) | N | now | `↻` | |
| deleted_at / is_deleted | — | — | — | SoftDel | |

> 关联表：`product_tag(product_id, tag_id)`、`product_image`、`product_manual`、
> `proposal_item`、`quotation_item` 均通过外键指向 `product`。

**阶段①②③索引（migration 实际建立）**：
- `idx_product_no_active`（unique partial）、`idx_product_category`、`idx_product_brand`、
  `idx_product_status`、`idx_product_stock_status`、`idx_product_vector`(HNSW)。

---

## 三、API 派生字段（**不是数据库列**，勿误写入 DB 模型）

以下字段由 serializer / service 在响应时拼装，**不存在于任何表**：
- `QuotationResponse.items`：来自 `quotation_item` 关联，序列化结果。
- `ProductResponse.brand_name` / `category_name` / `tags`：来自 `brand`/`category`/`tag`
  关联 JOIN，非 `product` 列。
- `stats/shares` 的 `proposal_name`、`access_count`、`top_accessed`：统计派生。
- `stats/products/hot` 的 `product_name`、`ref_count`：统计派生。
- `GET /api/v1/share/{token}` 的 `content`、`access_count`：运行时组装。
- 导出 Excel 的 `tags` 列：由 `product_tag` 关联拼接。

---

## 四、ORM 与 Alembic 一致性核对结论

| 项 | 结论 |
|---|---|
| `quotation.subtotal` | ORM 有；`0003` migration 补列（`nullable=False, default 0`）；**一致** |
| `product_manual_chunk` | ORM（`doc_chunk.py`）有；`0002` migration 建表 + 索引 + 触发器；**一致** |
| `product.vector` | ORM `Vector(1536)`；`0001` `Vector(1536)` + HNSW 索引；**一致**（运行期 pgvector 未装会 WARN，但字段定义一致） |
| `proposal.ai_polish_*` | ORM 有；`0002` migration 补 3 列；**一致** |
| `attachment.file_type` | ORM 无 CHECK（仅类型声明）；migration 有 `check_attachment_file_type`；**canonical = image/video/pdf/doc/other** |
| `share_visitors` / `share_logs` | 旧名不存在；实际表为 `visitor` / `share_log`；**以实际表名为准** |
| 软删除 | `share_log`/`operation_log`/`ai_conversation` 无 `is_deleted`（追加型日志），ORM 与 migration 均一致 |
| 触发器 `update_time` | `share_log`/`operation_log`/`ai_conversation` 无 `update_time` 且不在触发器列表，其余表一致 |

**结论：ORM 与 Alembic 全部 schema 一致；各 ORM 新字段/新表均有对应 migration。**

## 五、无法确认的业务规则（需产品/交付确认）
1. `quotation.status` / `proposal.status` 的完整枚举与状态机（已实现 `draft` 默认、独立 confirm 与 `confirmed` 不可改；其余取值与流转待产品确认）。
2. `share_type` 当前仅 `proposal` / `quotation` 两种被 `_build_content` 处理，是否还有其他类型未定义。
3. `visitor.openid` 唯一约束与「同一 openid 多设备」场景的去重策略（当前按 openid 优先、指纹次之解析）。
4. `product_manual.doc_type` 各枚举对应的解析/切片行为（仅约束值，处理规则未在路由暴露）。
5. pgvector 生产环境是否启用（影响 `vector` / `embedding` 列实际生效与 HNSW 索引）。
