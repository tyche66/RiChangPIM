# V1-AI Pilot 验收记录

验收日期：2026-07-17

## 结论

工程质量门禁、真实说明书链路、受控 OpenAI-compatible 集成矩阵、桌面端/移动端 E2E、生产回归和安全收口均已通过。

当前运行态保持 `AI_ADAPTER=none`，AI 路由按设计 fail-closed 返回 503。启用外部 AI 供应商属于部署配置变更，必须通过秘密管理系统注入凭据，不得提交到仓库。

## 数据与基础设施

- PostgreSQL：16.x，镜像 `pgvector/pgvector:pg16`
- PostgreSQL 固定卷：`richangpim_go_postgres_pg16_data_20260716`
- Alembic head：`0007_add_manual_parse_metadata`
- 圣奥导入：1 个供应商、11 个一级分类、53 个二级分类、173 个系列标签
- 运行服务：PostgreSQL、Redis、MinIO、Gotenberg、backend、nginx 均正常
- 最终 AI 配置：`AI_ADAPTER=none`，`AI_API_KEY` 为空

禁止执行 `docker compose down -v` 或删除固定卷。

## 后端门禁

Python 3.11 容器内执行：

```bash
python -m pytest -p no:cacheprovider -W error::DeprecationWarning -q
```

结果：`321 passed, 0 failed, 0 skipped, 0 warnings`。

补充门禁：

- Ruff：通过
- `compileall`：通过
- 真实 Parser：PDF 使用 pypdf，DOCX 使用 python-docx
- 空白或扫描 PDF：返回 `ocr_required`，不伪造正文
- pgvector：真实 1536 维写入和余弦检索通过

## 前端门禁

```bash
npx vue-tsc --noEmit
npx eslint . --ext .vue,.js,.jsx,.cjs,.mjs,.ts,.tsx
npm run test
npm run build
```

结果：

- Vitest：`96 passed, 0 failed`
- TypeScript：通过
- ESLint：通过
- Production build：通过

## 浏览器验收

Playwright 连接真实 PostgreSQL、Redis、MinIO、backend；说明书核心 API 未使用 `page.route` 拦截。

- Desktop Chromium：`29 passed, 0 failed, 0 skipped`
- Mobile Chrome：`29 passed, 0 failed, 0 skipped`
- 真实链路：登录、PDF 上传、说明书创建、解析、索引、RAG answer、sources 和 score

## AI 集成矩阵

使用本地受控 OpenAI-compatible provider 完成，验收后已删除 provider 容器及临时文件。

- RAG index：通过
- RAG sources：通过
- 推荐结果 Business API 回查与 `_verified` 标记：通过
- 润色成功与失败持久化：通过
- Embedding 维度 1536：通过
- Timeout、4xx、5xx、非法 JSON 映射：通过
- 第 11 次成本型 AI 请求返回 429：通过
- `AIConversation` 仅存 length/hash 摘要，并记录 model、usage、status：通过
- AI OperationLog 请求体统一 `[redacted]`：通过
- `ai_rag_answer` 审计动作：通过

## 生产回归

25 项编号回归结果：`25/25 PASS`。

覆盖范围：

1. Health、liveness、readiness、nginx
2. 匿名 401、错误登录 401、管理员登录与身份
3. 临时 viewer 登录、敏感字段过滤、用户列表和导入 403
4. 已解析说明书、pypdf metadata、MinIO 预签名 URL、真实 PDF bytes
5. viewer 解析 403
6. AI none 下 index、answer、chat 均 503
7. PostgreSQL 16、Alembic 0007、固定卷

临时 viewer 已软删除，活跃测试账号数为 0。

## 安全收口

- 源码秘密扫描未发现外部 AI Key、provider URL 或连接对象
- 外部 AI 凭据未写入项目文件、命令参数或验收文档
- 受控 AI mock 容器已删除
- 最终 readiness：DB/Redis/MinIO 为 `ok`，AI 为 `none`

## 发布判断

V1-AI Pilot 工程基线：GO。

AI 功能默认关闭的生产部署：GO。若要启用真实外部 AI 服务，须先完成供应商凭据轮换、秘密管理注入、网络与数据合规审批；该运营配置不改变本记录中的工程验收结果。
