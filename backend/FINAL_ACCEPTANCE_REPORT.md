# AI-PIM Backend 总验收报告（最终）

> 2026-07-22 增量说明：本报告主体是 2026-07-16 的历史验收快照，其中 migration head、
> 权限数量和测试数量不代表当前 V1.2 工作区。近期产品详情 500、版本接口、Compose 登录凭据
> 漂移和 Alembic 长 revision 兼容修复及其当前验证结果见
> `../docs/v1.2-verification.md`。V1.2 完整后端套件尚未恢复全绿，因此不得用本报告主体的
> “105 passed / GO”替代当前 RC 门禁结果。

验收日期：2026-07-16
项目根：`/home/AI-PIM/RiChangPIM/backend`
测试库：`ai_pim_test`（PostgreSQL，专用，仅测试使用）
生产库：`ai_pim`（**全程未被本流程触碰**，见第六章）
最终判定：**GO（针对后端测试套件 + 迁移 + 门禁）**

> 说明：本报告替换此前所有阶段性草稿。此前草稿中关于「环境无 PostgreSQL / 专用库不可达 /
> NO-GO」的描述均已过时——本环境实际已具备可达的专用 PostgreSQL 测试库，全部门禁已在其上
> 连续两次实跑通过。

---

## 一、八项验收阻塞的处置（本轮目标）

| # | 阻塞项 | 处置 | 证据 |
|---|---|---|---|
| 1 | 文件上传真实 DB 测试 | 新增 `tests/test_file_upload_integration.py`（7 项）：PDF/Word 提交、CHECK 约束、超大/不支持类型 422、MinIO `FakeMinio` 隔离、`commit` 失败一致性 | 7 passed |
| 2 | 测试库拆卸状态 | `tests/conftest.py` 移除 `Base.metadata.drop_all`，新增同步 `_drop_schema(url)`（`DROP SCHEMA public CASCADE; CREATE SCHEMA public;`），仅对安全测试库执行；`integration_setup_db` 拆卸调用之 | 全量 105 项实跑后 `ai_pim_test` 表数=0（一致，非「head 无表」） |
| 3 | 0004 admin 降级安全 | `0004_seed_data.py` 用确定性 `ADMIN_MIGRATION_ID = uuid5(NAMESPACE_DNS, "ai_pim.0004_seed_data.admin")` 种 admin；`downgrade` 仅删该 id（`DELETE ... WHERE id=:admin_id AND is_deleted=false`），不再按 username 盲删 | `tests/test_migration_admin_downgrade.py` 4 passed |
| 4 | 冒烟字段权限（真实数据） | `tests/test_smoke_e2e.py`：真实创建 brand/supplier/category/product（含非空 `cost_price`），断言 sales 看不到 `cost_price`、分享 content 隐藏 `cost_price` | 2 passed（暴露并修复了 `cost_price` 泄露 bug，见第三章） |
| 5 | `setup_local_env.sh` 干净 shell | 加默认值（`POSTGRES_DB` 默认 `ai_pim` + `TEST_DATABASE_URL`/`DATABASE_URL` 默认）、掩码打印解析配置、`command -v docker` 缺失时明确报错并 `exit 1` | 干净 `env -i` 下变量展开成功，无 docker 时优雅退出 1 |
| 6 | alembic helper 环境污染 | `tests/_db_probe.py`：`_run_alembic` 在 try/finally 中保存/还原 `ALEMBIC_OVERRIDE_URL`（缺失则删除、存在则还原），覆盖异常路径 | `tests/unit/test_db_probe.py` 4 项 env 还原测试 passed |
| 7 | 0005 partial-unique 兼容 | `0005_fix_partial_unique.py`：`DROP CONSTRAINT IF EXISTS` 移除 `product_product_no_key`/`share_token_token_key` 普通 UNIQUE，仅留 partial；旧库/新库收敛一致、幂等 | `tests/test_migration_schema.py` 4 passed |
| 8 | 本报告 | 本文件 | — |

---

## 二、门禁（全部在专用 PostgreSQL `ai_pim_test` 上实跑两次）

| 命令 | 结果（两次一致） |
|---|---|
| `python -m compileall -q app tests` | PASS，退出码 0 |
| `python -m pytest --collect-only -q` | 收集 **105** 项，0 collection/import error |
| `ruff check app tests`（select `E/F/I/UP/B`，仅 FastAPI API 文件 + `app/core/permission.py` 的 `B008` 按文件忽略） | `All checks passed!` |
| `python -m pytest -W error::DeprecationWarning`（全量） | **105 passed, 0 failed, 0 skipped** |
| `bash -n ../scripts/setup_local_env.sh` / `bash -n ../scripts/create_test_db.sh` | 语法 OK |
| `env -i HOME="$HOME" PATH="$PATH" bash ../scripts/setup_local_env.sh`（无 docker 兜底） | 掩码打印配置后 `exit 1`，无环境泄漏 |

连续两次全量运行均为 `105 passed, 0 failed, 0 skipped`，DB 终态一致（见第六章）。

---

## 三、本轮因「真实数据」暴露并修复的既有缺陷（属 Task 4 验收必要项）

任务 4 要求用真实数据验证字段权限，真实数据触发了此前空跑被掩盖的序列化 bug。这些修复使
相关接口在「存在关联行」时可用，且正是 Task 4 断言验证的对象：

1. **`app/api/v1/products.py` 关系惰性加载 → `MissingGreenlet`**
   - 所有 `select(Product)` 增加 `.options(selectinload(Product.tags))`（list/detail/update/delete/clone/duplicate 校验）。
   - `create_product` 提交后 `await db.refresh(product, ["tags"])`，避免返回新对象时惰性加载 `tags`。
   - 修复前：产品存在时 `GET/POST /products` 序列化抛 `MissingGreenlet`（500）。

2. **`app/api/v1/proposals.py` 关系惰性加载 → `MissingGreenlet`**
   - 所有 `select(Proposal)` 增加 `.options(selectinload(Proposal.items))`。
   - `create_proposal` 改为提交后重新 `select` 带 `selectinload` 返回，避免惰性加载 `items`。

3. **`app/core/serializers.py` `filter_sensitive_fields` 不递归嵌套字典 → 分享 `cost_price` 泄露（安全相关）**
   - 原为「仅过滤顶层 dict 的 key」，嵌套在 `items` 里的 `cost_price` 未被剥离。
   - 修复为「递归处理 dict 的 value」，使 `sales`/`viewer` 角色下分享的 proposal/quotation `content.items` 中的 `cost_price/supplier_*`/`margin/profit` 被正确隐藏。
   - 这正是 `test_share_access_route_writes_log_and_filters_cost_price` 所验证的行为：修复前该用例断言失败（返回体含 `cost_price: 123.45`），修复后通过。

4. **`app/api/v1/brands.py` `create_crud_router` 缺 body 类型注解 → 422**（早前会话修复）
   - `create_item(item_data, ...)` / `update_item(item_id, item_data, ...)` 的 `item_data` 补 `: schema` 注解，否则 FastAPI 将 body 当作 query 参数。

> 上述 1–3 为既有缺陷，非本次八项阻塞的范围，但因 Task 4 需要真实数据而必然暴露，已一并修复并
> 纳入门禁验证。修复后 `ruff` / 全量 pytest 仍全绿。

### 2026-07-22 产品详情增量修复

- 带产品图片时，`ProductResponse.model_validate(product)` 会把 `ProductImage` 直接验证为
  `ProductImageInfo`，但 `file_url/file_name/file_type` 实际位于
  `ProductImage.attachment`，因此触发 Pydantic `ValidationError` 并返回 500。
- 详情响应改为显式展平附件字段，查询明确加载 tags、brand、supplier、category、images 和
  attachment；场景图通过关联表单独查询并过滤软删除记录。
- 移除对未加载 `product.scene_images` relationship 的赋值，避免异步懒加载风险。
- `tests/test_product_detail.py` 与 `tests/test_version.py` 在真实 PostgreSQL 上共 10 项通过。
- 完整根因、前端状态处理和当前非全绿门禁说明见 `../docs/v1.2-verification.md`。

---

## 四、种子数据真实计数（由真实 `upgrade head` + 0004 种子迁移得出）

| 表 | 行数 |
|---|---|
| `role` | **4**（`系统管理员` / `采购员` / `销售员` / `访客`） |
| `permission` | **49** |
| `role_permission` | **95** |
| `"user"` | **1**（`admin`，`is_deleted=false`） |

即文档所述「4 角色 / 49 权限 / 95 映射 / 1 个种子 admin」与真实库一致。
（注：权限码列名为 `perm_code`、角色码列名为 `role_code`；此前报告中 `SELECT code` 为笔误。）

---

## 五、先前已落实且本次复测仍有效的修复（摘记）

- **旧模块 RBAC 缺口（P0）**：users/roles/products/categories/brands/suppliers/tags/proposals/shares/ai
  的敏感路由已挂载与 49 项权限目录一致的 `PermissionChecker`；缺失 Token → 401，缺权限 → 403。
  由 `tests/test_old_route_rbac.py`（10 项，含需 DB 的授权成功用例）静态 + HTTP 自省覆盖。
- **P1.2 UNIQUE 软删除语义**：`0001_initial` 移除 `product_no`/`token` 普通 UNIQUE，仅留
  `WHERE is_deleted=false` partial 唯一；`0005` 负责旧库收敛；ORM 同步为 `__table_args__` 声明。
- **P2 ORM CHECK 对齐**：Supplier/Product/Attachment 等的 `CheckConstraint` 在 ORM 补回，与迁移一致。
- **可移植 / 环境隔离**：`app/core/config.py` 改为相对项目根解析 `backend/.env`；compose 数据卷
  默认绑定到 `./docker/volumes/*`；`create_test_db.sh` / `setup_local_env.sh` 参数全环境变量化。

---

## 六、数据库终态与安全生产约束

- **测试库 `ai_pim_test`**：全量 pytest 运行后由 `conftest` 拆卸执行 `DROP SCHEMA public CASCADE;
  CREATE SCHEMA public;`，故终态为 **0 张表、`alembic_version` 不存在**。这是「一致空库」状态，
  **不是**此前担心的「head 版本已记录但无表」的破损状态；每次运行从全新 schema 起，结果可复现。
- **生产库 `ai_pim`**：全程未被任何 `upgrade`/`downgrade`/`DROP` 触碰，保持 **25 张表** 完好。
  所有测试写入仅指向 `ai_pim_test`（`_db_probe.is_safe_test_database` + `TEST_DB_APPROVED_ENV`
  双重守护，库名含 `test` 或显式批准才允许落库/清库）。
- **`alembic/env.py`**：迁移 URL 强制同步 `psycopg2` 驱动，并支持 `ALEMBIC_OVERRIDE_URL` 指向
  测试库（不污染应用库 `ai_pim`）。

---

## 七、最终判定

**GO**

放行依据（全部已满足且实跑验证）：

1. 静态门禁：`compileall` 0、`ruff E/F/I/UP/B` 全过、无全局 ignore / 无降 select / 无批量 noqa。
2. 动态门禁（专用 PostgreSQL 可达）：全量 `pytest -W error::DeprecationWarning` = **105 passed,
   0 failed, 0 skipped**，连续两次稳定。
3. 迁移与种子：`upgrade head` 在真实库一次成功，产出 4 角色 / 49 权限 / 95 映射 / 1 admin；
   `downgrade` 安全（0004 仅删确定性 admin id；0005 幂等）；旧库与新库经 0005 收敛一致。
4. 测试库状态自洽：运行后回归一致空库，生产库零风险。

已知非阻塞项（保留为后续治理，不影响 GO）：
- `role:assign`、`quotation:delete` 权限已种但对应路由暂未实装（文档化预留，非缺陷）。
- 生产默认凭据 / 通配 CORS 等上线前仍需强制安全配置（启动链会 fail-fast，但属部署侧要求）。
- Docker 不可用，故 `setup_local_env.sh` 的「一键起依赖」步骤在本机走「干净 shell 兜底」分支
  （变量展开已验证，无 docker 时优雅退出）；在有 Docker 的主机可完整跑通。
