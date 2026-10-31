# CONTRIBUTING.md
本项目遵循自研工程治理框架，Trunk-Based 开发。

## 分支规范
- `main`：主干分支，随时可发布，保持稳定；禁止直接push到main
- 所有改动走分支 + PR 合并
- 分支命名：`feat/xxx` / `fix/xxx` / `docs/xxx` / `refactor/xxx`

## 提交信息规范
格式：`类型(范围): 简短描述`

类型：
- feat：新增功能
- fix：bug修复
- docs：文档变更（PRD/架构/任务卡/prompt等）
- refactor：重构，无行为变化
- test：测试、评估集变更
- chore：脚本、骨架、CI、依赖调整

示例：
```
docs(prd): 补充用户场景表格
feat(retrieve): 增加向量检索接口
fix(task): 修正任务卡评测判定逻辑
```

## PR 评审规则
1. 文档类变更：PR只包含对应文档文件，不混代码
2. 任务卡变更：同步更新 `tasks/readme.md` 索引表
3. 代码变更：必须关联对应 TASK-XXX 任务卡
4. MAJOR版本升级PR：必须包含 archive 快照目录、新版本文档、新增ADR
5. 评审通过后方可合并进main

## 文件命名规范（强制执行）
- 仓库顶层：首字母大写 `README.md` `AGENTS.md` `CONTRIBUTING.md`
- docs内全部文档：小写 kebab-case `xxx-yyy.md`
- 任务卡：`task-00N-short-name.md`
- 禁止驼峰、中文、空格

## 框架约束
- 先文档、后代码；无确认PRD/架构/接口，不开发业务代码
- ADR只追加，不修改历史ADR
- 任务卡采用一任务一文件，增量拆分，禁止一次性全量拆解
- MAJOR破坏性升级：先归档快照，再迭代新版本文档
- 废弃接口必须标记 deprecated + 迁移指引
