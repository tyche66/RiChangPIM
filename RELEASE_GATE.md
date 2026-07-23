# RELEASE GATE — AI-PIM V1.2

> 唯一基线：`docs/v1.2-plan.md`
> 版本号：`v1.2.0`
> 适用分支：`release/v1.2.0`（从 `main` 切出）
> 适用阶段：M2 之后所有候选发布，以及最终 RC GO 判定

本文件定义 V1.2 的发布门禁。任一门禁失败即为 NO-GO，不接受“测试通过但运维未验收”的条件式发布。门禁验证脚本见 `scripts/release_gate.sh`。

## 1. 工程质量门禁

| 项 | 命令 | 通过条件 |
|---|---|---|
| Backend lint | `cd backend && ruff check app/` | 退出 0，无 warning |
| Backend 编译 | `python -m compileall app -q` | 退出 0 |
| Backend 单测 | `python -m pytest -q` | 全绿 |
| Frontend 类型 | `cd frontend && npx vue-tsc --noEmit` | 退出 0 |
| Frontend lint | `npx eslint . --max-warnings=0` | 不使用 `--fix` |
| Frontend 单测 | `npx vitest run` | 全绿 |
| Frontend 构建 | `npm run build` | `dist/` 生成且体积非空 |
| Compose 校验 | `docker compose -f docker-compose.yml config -q` 与 `docker-compose.dev.yml` | 退出 0 |
| Migration 升级 | 在全新临时 PG16 中 `alembic upgrade head` | 从 0001 至 head 全成功 |
| 历史迁移只读 | `alembic/versions/` 下 `0001`-`0009` 哈希未变 | 与基线快照一致 |
| 依赖漏洞 | `pip-audit` + `npm audit --omit=dev --audit-level=high` | 无 high/critical |

CI 必须执行以上全部，且 artifact 上传：测试报告、构建产物、审计报告。

## 2. 功能与数据门禁

- 13 条试点产品可继续浏览、筛选、导出
- 数据质量问题可筛选、统计、导出
- 待核价产品不会显示虚假价格（UI/导出显示“待核价”）
- `purchaser` / `sales` / `viewer` 字段权限无回归
- 操作日志筛选、分页、时间范围可用
- 非管理员不能访问审计数据

## 3. 浏览器门禁

| 项 | 视口 | 范围 |
|---|---|---|
| Desktop Chromium | 1280x800 | 登录、产品列表与详情、说明书、方案、分享页、操作日志、数据质量看板 |
| Mobile Chrome | 393x851 | 产品列表与详情、分享页、操作日志（横向滚动或收敛列） |

E2E（Playwright）必须覆盖：`auth`、`ai-features`、`gap-analysis`、`manuals-real`、`proposals`、`sharing`、`audit`、`data-quality`。

## 4. 运行与恢复门禁

- 生产 Compose 全服务健康
- HTTP → HTTPS 跳转，HTTPS readiness 返回 200
- 最近一次备份状态可查询（`backups/last_status.json` 或 `/ops/status`）
- 独立恢复演练通过（PG16 与 MinIO 不挂载生产卷）
- RPO ≤ 24 小时，RTO ≤ 4 小时
- 不删除或修改现有 Docker volume

## 5. 性能门禁

| 接口 | 并发 | warmup | 阈值 | 说明 |
|---|---|---|---|---|
| 产品列表 | 20 / 200 | 20 | 连续三轮最差稳态 P99 ≤ 200ms | 多条件筛选与导出同基线 |
| 产品详情 | 同上 | 同上 | P99 ≤ 150ms | |
| 普通写操作 | 同上 | 同上 | P99 ≤ 500ms | |
| 错误率 | — | — | < 1% | |
| readiness | — | — | ≤ 60 秒 | 冷启动 |

冷连接与稳态结果分别记录。必须形成 1x、10x、100x 三档容量报告，仅当 `EXPLAIN ANALYZE` 有证据时方可加索引或切换 keyset pagination。

## 6. 安全门禁

- `AI_ADAPTER=none`、`OCR_ADAPTER=none` 为最终默认状态
- 外部 AI Key 不出现在 Git、文档、日志、命令参数、测试产物
- 秘密扫描：JWT、数据库密码、MinIO 密码无命中（`scripts/secret_scan.sh`）
- 审计 API 不返回 `request_body`
- 备份调度命令不包含明文密码
- AI / OCR / 备份失败均 fail-closed，不生成伪成功数据

## 7. 生产回归

`scripts/production_regression.py` 必须从 25 项扩展到 35-40 项，新增：

- 备份状态可查询
- 审计页面筛选与分页
- 数据质量看板可达
- migration head 与基线一致
- 容量检查（`/health/ready` 输出 `volume_free_bytes` 与阈值）
- 操作日志非管理员 403

最终 GO 必须达到 35-40/35-40 PASS，且不接受跳过项。

## 8. 部署演练

RC 阶段至少：

- 一次全新环境部署（空 PG16 + Compose，从 0001 升 head）
- 一次基于现有数据的升级部署（挂载当前生产卷并执行迁移）

两轮演练都必须能拉起并完整执行生产回归脚本。

## 9. GO 判定流程

1. CI 全绿并产出 artifact
2. 本地按本文件逐项执行 `scripts/release_gate.sh`
3. 扩展后的生产回归 35-40/35-40 PASS
4. 全新环境 + 现有数据升级两轮部署演练全部通过
5. 秘密扫描无命中
6. 由 V1.2 协调人书面签字 GO
7. 任一门禁失败不得绕过；只能修 P0/P1 缺陷后重新跑全量门禁
