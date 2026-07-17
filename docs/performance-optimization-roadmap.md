# 性能优化路线图

更新日期：2026-07-17

## 当前基线

目标接口：`GET /api/v1/products?page=1&size=20`，200 请求，并发 20。

V1.1 初始冷连接 HTTPS 基线：P50 178.32 ms、P95 479.00 ms、P99 549.73 ms、89.94 req/s。

分层诊断表明：PostgreSQL 两条主查询执行均不足 1 ms；单并发 HTTPS P99 29.46 ms。主要压力来自默认 5 条数据库连接池、关联加载往返、单 worker 并发调度，以及测试工具每请求新建 TLS 连接。

本轮已实施：

- 后端扩为 2 个 Uvicorn worker；每 worker SQLAlchemy pool_size=10、max_overflow=10，总连接上限 40，并允许环境变量覆盖。
- brand/supplier/category 多对一关系由 selectinload 改为 joinedload，减少列表 SQL 往返。
- 列表热路径直接构造响应字典，详情和写接口仍保留 Pydantic schema 校验。
- 关闭重复 Uvicorn access log，保留 AuditMiddleware 请求日志和业务 operation_log。
- 压测增加 warmup，正式统计不混入连接池和 TLS 首次建连成本。

优化后真实 HTTPS、持久连接、warmup 20 的三轮结果：

| 轮次 | P50 | P95 | P99 | 吞吐 |
|---|---:|---:|---:|---:|
| 1 | 66.45 ms | 123.67 ms | 131.56 ms | 279.43 req/s |
| 2 | 51.94 ms | 79.45 ms | 89.23 ms | 356.00 req/s |
| 3 | 57.04 ms | 115.04 ms | 124.79 ms | 307.39 req/s |

发布 SLO 以 warmup 后稳态为准：P99 <= 200 ms、错误率 < 1%。冷启动/冷池结果单独监控，不用稳态数据掩盖冷启动风险。

## 后期方向

### P1：可观测性和基准规范

- 引入 Prometheus/OpenTelemetry，记录路由 P50/P95/P99、SQL 数量、连接池等待和 event-loop lag。
- 将 warmup、keep-alive、冷连接、稳态连接定义为独立场景，结果写入 CI 制品。
- 建立 1x、10x、100x 数据规模基线；当前 15 条产品不能代表生产索引选择。
- 在发布门禁中连续执行至少三轮，以最差稳态 P99 判定。

### P2：查询和分页

- 产品达到 10 万条前改为 keyset pagination，避免大 OFFSET。
- 为高频组合筛选增加基于真实 `EXPLAIN (ANALYZE, BUFFERS)` 的复合/部分索引；禁止凭猜测加索引。
- 标签筛选改为 EXISTS 半连接，避免 DISTINCT 子查询在多标签场景膨胀。
- 将 total 计数改为可选参数或短 TTL 缓存，避免每次列表请求全量 count。
- 列表投影仅返回页面所需字段，详情字段按需加载。

### P3：应用容量

- 继续按 CPU 与真实吞吐调整 Uvicorn worker；每次调整必须明确每 worker 连接池预算，确保总连接数不超过 PostgreSQL max_connections。
- 生产引入 PgBouncer transaction pooling，降低 worker 扩容时的连接成本。
- 对只读主数据和低变更产品页引入 Redis/ETag 缓存，并以写操作主动失效。
- 分析 JSON 序列化、JWT 解码和日志 I/O；仅在 profile 证明有效后引入 orjson 或缓存 token claims。

### P4：前端与网络

- 保持 HTTP/2/keep-alive，生产由受信任 TLS 终止层复用连接。
- 产品筛选增加请求取消和防抖，避免快速输入造成无效并发。
- 对大列表采用虚拟滚动和字段按需请求。
- 将静态资源拆分和压缩纳入 Web Vitals 预算。

## 验收标准

- 产品列表：并发 20、200 请求、warmup 20，最差稳态 P99 <= 200 ms，错误率 < 1%。
- 详情：P99 <= 150 ms。
- 写操作：P99 <= 500 ms，且审计日志完整。
- 冷启动 readiness <= 60 秒；首轮冷池 P99 单独记录并持续下降。
- 任一优化不得关闭 RBAC、字段脱敏、AuditMiddleware、operation_log 或数据库约束。
