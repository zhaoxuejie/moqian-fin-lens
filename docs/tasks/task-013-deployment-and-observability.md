# TASK-013 部署与可观测

- 编号：TASK-013
- 里程碑：v1.0
- 前置依赖：TASK-012
- 优先级：P1
- 状态：⬜ todo
- 来源：`docs/prd.md` 5.5 可观测、5.2 并发；`docs/architecture.md` ADR-007
- 关联文档：`Dockerfile`、`docker-compose.yml`（TASK-001 已写，未实际构建）

## 背景与目标

代码能跑但没真正部署验证过：Docker 镜像从未构建，运行摘要没有落盘，发布脚本也只有一个空壳。本卡把「能上线」补齐。

## 执行步骤

1. Docker 构建：在 Linux 容器内完成 `pip install .`，验证 `docker compose up` 后 `/healthz` 200。
2. 环境变量校验：缺 `DATABASE_PATH` 时容器启动失败并打印字段名。
3. 运行摘要落盘：每次解析输出页数、定位页、未对齐数、耗时、勾稽结论到日志文件。
4. 健康检查与告警口径：`/healthz` 增加数据库可用性检查；解析成功率低于 90% 打印告警日志。
5. 发布脚本：`scripts/release.sh` 支持版本号参数、更新 CHANGELOG、打 tag（不 push）。
6. README 补部署章节与常见故障排查。

## 交付物

- 可构建的 Docker 镜像与 compose 冒烟记录
- 运行摘要落盘与告警日志
- 发布脚本实现与 dry-run 输出
- README 部署章节

## 验收标准（布尔判定）

1. `docker compose up --build` 后 5 秒内 `/healthz` 返回 200（记录构建耗时）。
2. 去掉 `DATABASE_PATH` 后容器启动失败，日志打印字段名，退出码非 0。
3. 解析一份年报后，运行摘要文件新增一条记录，含页数、耗时、勾稽结论。
4. 人为让 2 次解析失败，告警日志出现「解析成功率低于阈值」。
5. `scripts/release.sh 1.0.0 --dry-run` 输出将执行的命令且不修改仓库。
6. README 的部署命令可照着执行成功（人工验收）。

## 评测方案

- 容器冒烟：构建 → 启动 → healthz → 停止，脚本化记录。
- 日志断言：解析后检查摘要文件字段。
- 发布脚本：dry-run 断言、真实执行在测试分支验证。

## 风险与备注

- 本机 Docker 守护进程曾在 TASK-001 时未启动；若仍不可用，需先在宿主机启动 Docker Desktop，评测记录中注明环境限制。
- 单实例部署（ADR-007）不变，多实例扩展不在本卡。
