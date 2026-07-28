# P0 发布门禁清单

> 状态：Phase 0 退出审查清单。所有项完成前不得进入 Phase 1 的 `Knowledge Gateway`、Tool Registry、Portal 或 Worker 编码。

| 门禁项 | 来源 | 状态 | 证据文件路径 | 验收标准 |
| --- | --- | --- | --- | --- |
| 架构规划冻结 | 07 §3 | 待签字 | `/home/AI-PIM/docs/AI-Docs/README.md`、`08-架构决策记录ADR.md` | 老板、产品、架构、安全、研发确认范围 |
| 200 条评测集 | 07 §3、06 §7 | 已建骨架 | `/home/AI-PIM/RiChangPIM/eval/p0/evalset.jsonl` | 覆盖权限、未知数据、拒答、攻击样本 |
| 既有 AI 基线脚本 | 07 §3 | 已建脚本 | `/home/AI-PIM/RiChangPIM/scripts/p0/ai_baseline.py` | 可测 `/chat`、`/recommend`、`/rag/search` |
| 基线报告 | 07 §3 | 待执行 | `/home/AI-PIM/RiChangPIM/eval/p0/baseline-report.json` | 模型配置后生成延迟与效果基线 |
| 凭据轮换与 Secret scan | 07 §3、05 §6 | 待执行 | `/home/AI-PIM/docs/AI-Docs/p0/credential-rotation-record-template.md` | Git 历史、日志、构建产物无有效 Key |
| 威胁模型与数据分级 | 07 §3、05 §2 | 已建文档 | `/home/AI-PIM/docs/AI-Docs/p0/security-gate-and-threat-model.md` | L1-L4、威胁、控制、验收均明确 |
| 权限池矩阵 | ADR-010、04 §6 | 已建文档 | `/home/AI-PIM/docs/AI-Docs/p0/permission-pool-matrix.md` | admin/purchaser/sales/viewer 字段可见性明确 |
| 限额与成本治理接口 | 06 §6 | 已建文档 | `/home/AI-PIM/docs/AI-Docs/p0/quota-limit-interface-design.md` | 次数/Token/成本/角色/用户/系统三级限制可插拔 |
| 模型供应商与预算 | 07 §13 | 未定，不阻塞接口设计 | 待建供应商评审记录 | 供应商可未定，但价格表、Key 注入、限额接口已预埋 |
| 试点数据治理 | 01 §2.3、07 §3 | 已建文档 | `/home/AI-PIM/docs/AI-Docs/p0/pilot-data-governance.md` | 销售选型和知识问答可验证 |
| 试点数据缺口清单 | 07 §12 | 已建文档 | `/home/AI-PIM/docs/AI-Docs/p0/pilot-data-gap-list.md` | 99999、unknown、draft、pending 等缺口有修复标准 |
| 可插拔原则复核 | ADR-002/012/013 | 已纳入 | 本目录所有 P0 文档 | Adapter/Quota/Permission/Conversation/Retriever 不写死供应商或实现 |

## 阻塞条件

- 有效密钥仍存在于 Git、日志或构建产物。
- 试点数据不能验证销售选型与知识问答。
- 权限池矩阵未确认，特别是成本价、库存、供应商、客户名、报价明细。
- 评测集缺少安全对抗、未知数据或拒答样本。
- 任何 Phase 1 设计要求模型自行隐藏敏感字段。

## 进入 Phase 1 条件

- 本清单所有“已建文档”完成复核。
- 所有“待执行”项完成并有证据文件。
- 未定模型供应商不阻塞，但必须使用可插拔 Adapter、空价格表、环境变量注入和限额接口。
- 项目负责人确认风险处置方式，并在签字区记录。

## 签字区

| 角色 | 姓名 | 日期 | 结论 |
| --- | --- | --- | --- |
| 老板 |  |  |  |
| 产品负责人 |  |  |  |
| 架构负责人 |  |  |  |
| 安全负责人 |  |  |  |
| 研发负责人 |  |  |  |
| Agent / 项目构建者 |  |  |  |
