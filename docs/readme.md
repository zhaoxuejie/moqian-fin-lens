# readme.md
> 本目录为陌阡AI工程治理框架的配套元文档目录

## 目录说明
- `prd.md`：当前活跃版本需求文档，包含目标、范围、场景、功能、里程碑、废弃与迁移指引
- `architecture.md`：当前架构方案 + ADR决策记录；历史ADR只追加、不修改
- `api-contract.md`：接口契约，支持版本标记、deprecated标记、迁移指引
- `prompt.md`：陌阡AI框架启动基座提示词，新开AI会话时复制使用
- `stage-prompts.md`：分阶段指令模板，基座prompt之后追加，切换PRD/架构/接口/任务/开发等阶段
- `archive/`：冻结快照目录，仅存放MAJOR版本归档包，归档后只读，不再修改
- `tasks/`：可执行任务卡目录

## 版本规则
- MAJOR：不兼容破坏性变更，先归档快照再更新文档
- MINOR：兼容新增功能
- PATCH：兼容修复、微调
