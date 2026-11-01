# tasks
任务卡目录。任务采用增量拆分模式：**禁止一次性拆解整个里程碑全部任务**；完成一批，再基于当前进度拆解下一批。

## 状态枚举（带图标）

| 图标 | 状态 | 含义 |
| ---- | ---- | ---- |
| ⬜ | `todo` | 待启动（依赖未满足或尚未开始） |
| 🚧 | `doing` | 开发中 |
| 👀 | `review` | 待评审 |
| 🧪 | `evaluating` | 评测中（代码已交付，等验收） |
| ✅ | `done` | 已完成（验收与评测通过） |
| ⛔ | `abandoned` | 已废弃（文件保留，编号不回收） |

优先级：`P0`（阻塞）/ `P1`（核心）/ `P2`（可选）

## 任务索引表
| 编号 | 标题 | 里程碑 | 前置依赖 | 优先级 | 状态 | 关联文档 |
| ---- | ---- | ------ | -------- | ------ | ---- | -------- |
| TASK-001 | 工程骨架与运行基线 | v1.0 | 无 | P0 | ✅ done | [task-001-project-skeleton.md](task-001-project-skeleton.md) |
| TASK-002 | 解析器骨架与三表定位 | v1.0 | TASK-001 | P0 | ✅ done | [task-002-parser-and-statement-locating.md](task-002-parser-and-statement-locating.md) |
| TASK-003 | 数值归一（单位 / 符号 / 空值） | v1.0 | TASK-002 | P0 | ✅ done | [task-003-number-normalization.md](task-003-number-normalization.md) |
| TASK-004 | 标准科目 Schema 与别名映射表 | v1.0 | TASK-001 | P0 | ✅ done | [task-004-account-schema-and-alias.md](task-004-account-schema-and-alias.md) |
| TASK-005 | 规则匹配与未对齐显式化 | v1.0 | TASK-003、TASK-004 | P0 | ✅ done | [task-005-rule-matching-and-unaligned.md](task-005-rule-matching-and-unaligned.md) |
| TASK-006 | 表格结构还原 | v1.0 | TASK-005 | P0 | ✅ done | [task-006-table-structure-recovery.md](task-006-table-structure-recovery.md) |
| TASK-007 | 指标计算与三表勾稽 | v1.0 | TASK-006 | P0 | ✅ done | [task-007-metrics-and-checks.md](task-007-metrics-and-checks.md) |
| TASK-008 | 看板与 8 组图表 | v1.0 | TASK-007 | P0 | ✅ done | [task-008-dashboard-and-charts.md](task-008-dashboard-and-charts.md) |
| TASK-009 | 溯源与导出 | v1.0 | TASK-008 | P0 | ✅ done | [task-009-trace-and-export.md](task-009-trace-and-export.md) |
| TASK-010 | 上传与解析入队 | v1.0 | TASK-009 | P0 | ✅ done | [task-010-upload-and-job-queue.md](task-010-upload-and-job-queue.md) |
| TASK-011 | 多期会话与同比 | v1.0 | TASK-010 | P0 | ✅ done | [task-011-multi-period-sessions.md](task-011-multi-period-sessions.md) |
| TASK-012 | 会话落库与原件生命周期 | v1.0 | TASK-010 | P0 | ✅ done | [task-012-session-persistence.md](task-012-session-persistence.md) |
| TASK-013 | 部署与可观测 | v1.0 | TASK-012 | P1 | ✅ done | [task-013-deployment-and-observability.md](task-013-deployment-and-observability.md) |
| TASK-014 | 指标与提取缺口修补（PATCH） | v1.0 | TASK-011 | P1 | ✅ done | [task-014-metric-extraction-gaps.md](task-014-metric-extraction-gaps.md) |
| TASK-015 | 多文件上传与继续上传 | v1.0 | TASK-011 | P1 | ✅ done | [task-015-multi-file-upload-ui.md](task-015-multi-file-upload-ui.md) |
| TASK-016 | 看板对齐高保真原型 | v1.0 | TASK-015 | P1 | ✅ done | [task-016-dashboard-visual-alignment.md](task-016-dashboard-visual-alignment.md) |
| TASK-017 | 品牌视觉与详情页改造 | v1.0 | TASK-016 | P0 | ✅ done | [task-017-brand-and-detail-refresh.md](task-017-brand-and-detail-refresh.md) |
| TASK-018 | 详情页信息分层与对比台可读性 | v1.0 | TASK-017 | P1 | ✅ done | [task-018-detail-hierarchy-and-compare-units.md](task-018-detail-hierarchy-and-compare-units.md) |
| TASK-019 | 报表首行丢失修复 | v1.0 | TASK-018 | P0 | ✅ done | [task-019-first-row-recovery.md](task-019-first-row-recovery.md) |

## 规则
1. 任务存储模式：**一个任务单独一个文件**，不把多个任务混在同一个文件。
   文件命名：`task-00N-short-description.md`，小写 kebab-case。
   本 readme.md 仅做索引看板，**不存放任务详细正文**；执行步骤、验收标准、评测方案全部放在对应任务独立文件内。
2. 必须所有前置依赖状态为 done，才可以启动本任务
3. 每张任务卡必须包含可判定的验收标准与评测方案；评测不通过，不能标记 done
4. 任务编号全局唯一，废弃任务标记 abandoned，不删除文件、不回收编号
5. 新任务草稿必须人工审阅确认后，才正式入库、更新本表
6. 版本归档时，tasks 整体随同 docs 一起快照存入 archive
7. 状态列必须带图标，且与状态枚举一一对应；任务确认后由 AI 自动提交 git（见 `AGENTS.md` 的 Git 提交规则）

## 关联
- 任务来源：prd.md、architecture.md、api-contract.md
- 评测资产：tests/ 评估集、单元测试、契约测试
