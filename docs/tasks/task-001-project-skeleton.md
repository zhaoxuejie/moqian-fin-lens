# TASK-001 工程骨架与运行基线

- 编号：TASK-001
- 里程碑：v1.0
- 前置依赖：无
- 优先级：P0
- 状态：🧪 evaluating（代码已交付，待人工评测）
- 来源：`docs/architecture.md` §9 代码组织；`docs/api-contract.md` 通用约定
- 关联文档：`docs/prd.md` 5.2 / 5.5；`docs/architecture.md` ADR-001 / ADR-003 / ADR-007

## 背景与目标

先把「能启动、能建库、能记日志、能跑测试、能部署」的地基打好。后续所有任务卡都跑在这套骨架上，因此本卡不实现任何业务逻辑，只交付可验证的运行基线。

## 执行步骤

1. 按架构 §9 建立 `src/` 目录骨架：`app`、`core`、`store`、`parse`、`schema`、`align`、`metrics`、`anomaly`、`dashboard`、`trace`、`export`、`jobs`、`ops`，每个包只放 `__init__.py` 与占位说明。
2. 实现 FastAPI 应用入口与 `GET /healthz`；配置 Jinja2 模板目录与静态资源目录。
3. 实现 `core/config.py`：`pydantic-settings` 读取 `.env`，必填项缺失时启动即失败并指明字段；密钥只从环境变量读取。
4. 实现 `store` 建库与迁移：schema 版本表 + 架构 §5 的 9 张表；启动时自动迁移且幂等。
5. 实现统一响应体（`code / msg / data / request_id`）与统一错误码枚举（对应 api-contract 错误码表）。
6. 实现结构化 JSON 日志：单行 JSON、含 `request_id`、`level`、`event`；请求级中间件注入 request_id。
7. 增加 `pytest` 测试目录与 `tests/eval/` 占位；CI 增加 Python 测试步骤。
8. 增加 `Dockerfile` 与 `docker-compose.yml`（uvicorn + 数据卷挂载 `data/`），更新 `.env.example`。

## 交付物

- `src/` 目录骨架与启动入口
- SQLite 建库与迁移脚本（幂等）
- 配置加载、统一响应体、错误码枚举
- 结构化日志中间件
- pytest 测试骨架、CI 测试步骤、Dockerfile / compose
- 更新后的 `.env.example`

## 验收标准（布尔判定）

1. `uvicorn src.app.main:app` 启动后，`GET /healthz` 返回 HTTP 200 且响应体 `{"status":"ok"}`。
2. 首次启动自动建库；删除 `data/app.db` 后再次启动可重建；重复启动不重复建表、不报错。
3. 把 `.env` 中必填项删掉后启动，进程以非 0 退出并打印缺失字段名，不静默使用默认值。
4. `pytest` 全部通过，`src/core`、`src/store`、`src/app` 行覆盖率 ≥ 80%。
5. 每条日志为单行合法 JSON，含 `request_id` 与 `level` 字段；并发两次请求的 `request_id` 不同。
6. 空库状态下 `GET /` 返回 200 且返回 HTML 页面（可为占位页）。
7. 密钥类配置不出现在代码、模板、前端静态资源与日志中（用仓库内搜索验证）。

## 评测方案

- 单元测试：配置加载（缺项失败、正常加载）、建库幂等、响应体封装、request_id 注入。
- 冒烟脚本：启动服务 → 请求 `/healthz` → 请求 `/` → 停止服务，三步全部返回预期状态码。
- 幂等验证：删除数据库后重启，执行两次建库迁移，第二次不产生变更。
- CI 准入：markdownlint + pytest 全绿才算通过。

## 风险与备注

- SQLite 迁移脚本一旦上线不可随意改历史版本，只能追加新迁移；本卡即确立此规则。
- 单进程单实例是 v1.0 的既定取舍（ADR-007），本卡不实现多实例支持。
