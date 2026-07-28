# P0 模型凭据轮换记录模板

> 用途：记录当前开发/演示环境中 AI 模型、OCR、对象存储、JWT 等凭据的核验与轮换。本文档模板不得填写真实密钥，只记录 Key 类型、命中摘要和处置结论。

## 1. 基本信息

| 字段 | 内容 |
| --- | --- |
| 记录编号 | P0-CRED-YYYYMMDD-001 |
| 执行时间 |  |
| 执行人 |  |
| 复核人 |  |
| 环境 | dev / demo / staging / production |
| 仓库路径 | `/home/AI-PIM/RiChangPIM` |
| 文档路径 | `/home/AI-PIM/docs/AI-Docs` |

## 2. 扫描范围

| 范围 | 命令或工具 | 结果摘要 |
| --- | --- | --- |
| 当前工作区 | `git status --short` 后全仓 Secret scan |  |
| Git 历史 | `git log -p --all` + secret scanner |  |
| 环境文件 | `.env`, `.env.example`, docker env |  |
| 日志目录 | `logs/`, backend logs, nginx logs |  |
| 构建产物 | `frontend/dist`, docker image layer, CI artifact |  |
| 文档目录 | `/home/AI-PIM/docs/AI-Docs` |  |

## 3. 命中摘要

| 序号 | Key 类型 | 命中文件/位置 | 是否有效 | 处置方式 | 责任人 | 复核结论 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | AI_API_KEY / OCR / MinIO / JWT / 其他 |  | 是/否/疑似 | 吊销/轮换/误报 |  |  |

## 4. 轮换记录

| Key 类型 | 旧 Key 处置 | 新 Key 注入方式 | 是否写入 Git | 生效时间 | 验证方式 |
| --- | --- | --- | --- | --- | --- |
| AI_API_KEY | 已吊销/无命中 | 环境变量/Secret Manager/宿主机受限 env | 否 |  |  |
| OCR_API_KEY |  |  | 否 |  |  |
| MINIO_SECRET_KEY |  |  | 否 |  |  |
| JWT_SECRET |  |  | 否 |  |  |

## 5. 核验结论

| 核验项 | 结果 | 证据路径 |
| --- | --- | --- |
| Git 历史无有效 Key | 通过/未通过 |  |
| 日志无有效 Key | 通过/未通过 |  |
| 构建产物无有效 Key | 通过/未通过 |  |
| `.env.example` 仅含占位值 | 通过/未通过 | `backend/.env.example` |
| 生产 Key 不通过命令参数传递 | 通过/未通过 |  |

## 6. 签字

| 角色 | 姓名 | 日期 | 结论 |
| --- | --- | --- | --- |
| 执行人 |  |  |  |
| 安全复核 |  |  |  |
| 项目负责人 | Agent / 项目构建者 |  |  |

最终结论：通过 / 阻塞 / 需复核。
